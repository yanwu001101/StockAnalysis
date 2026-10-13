import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, type EffectScope } from 'vue'
import type { WarmupRun } from '../src/api/admin'
import { useWarmupRuns } from '../src/composables/useWarmupRuns'

type Job = 'postmarket' | 'weekend' | 'premarket' | 'intraday'
type StatusResponse = WarmupRun | { items: WarmupRun[] }

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

function run(id: string, job: Job = 'postmarket', status: WarmupRun['status'] = 'running'): WarmupRun {
  return {
    id, job, status, started_at: '2026-10-12T08:00:00+08:00',
    ...(status === 'running' ? {} : { finished_at: '2026-10-12T08:01:00+08:00' }),
  }
}

const scopes: EffectScope[] = []

function fixture() {
  const api = {
    start: vi.fn<(job: Job) => Promise<WarmupRun>>(),
    status: vi.fn<(id?: string) => Promise<StatusResponse>>().mockResolvedValue({ items: [] }),
  }
  const onStarted = vi.fn<(item: WarmupRun) => void>()
  const onRunsFinished = vi.fn<(items: WarmupRun[]) => void>()
  const onPollError = vi.fn<(error: Error) => void>()
  const onStartError = vi.fn<(error: Error) => void>()
  const scope = effectScope()
  scopes.push(scope)
  const state = scope.run(() => useWarmupRuns({
    api, pollMs: 1000, maxConcurrent: 2,
    onStarted, onRunsFinished, onPollError, onStartError,
  }))!
  return { api, state, scope, onStarted, onRunsFinished, onPollError, onStartError }
}

async function flushMicrotasks() {
  for (let i = 0; i < 10; i += 1) await Promise.resolve()
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-12T00:00:00Z'))
})

afterEach(() => {
  for (const scope of scopes.splice(0)) scope.stop()
  vi.clearAllTimers()
  vi.useRealTimers()
})

describe('useWarmupRuns lifecycle and concurrent maintenance jobs', () => {
  it('loads terminal history without replaying notifications or starting a polling loop', async () => {
    const f = fixture()
    const history = [run('a', 'postmarket', 'success'), run('b', 'weekend', 'partial')]
    f.api.status.mockResolvedValue({ items: history })

    expect(await f.state.refresh()).toBe(true)
    expect(f.state.recentRuns.value).toEqual(history)
    expect(f.state.activeCount.value).toBe(0)
    expect(f.state.canStart('postmarket')).toBe(true)
    expect(f.onRunsFinished).not.toHaveBeenCalled()
    expect(f.onStarted).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(f.api.status).toHaveBeenCalledTimes(1)
  })

  it('restores all running jobs and keeps polling the second after the first finishes', async () => {
    const f = fixture()
    let server = [run('a'), run('b', 'weekend')]
    f.api.status.mockImplementation(async id => id ? server.find(item => item.id === id)! : { items: server })

    await f.state.refresh()
    expect(f.state.activeCount.value).toBe(2)
    expect(f.state.busyByJob.value.postmarket).toBe(true)
    expect(f.state.busyByJob.value.weekend).toBe(true)
    expect(f.state.canStart('premarket')).toBe(false)
    expect(f.onRunsFinished).not.toHaveBeenCalled()

    server = [run('a', 'postmarket', 'success'), run('b', 'weekend')]
    await vi.advanceTimersByTimeAsync(1000)
    expect(f.state.activeCount.value).toBe(1)
    expect(f.state.busyByJob.value.postmarket).toBeFalsy()
    expect(f.state.busyByJob.value.weekend).toBe(true)
    expect(f.state.canStart('premarket')).toBe(true)
    expect(f.onRunsFinished).toHaveBeenCalledTimes(1)
    expect(f.onRunsFinished).toHaveBeenLastCalledWith([server[0]])
    const requestCount = f.api.status.mock.calls.length

    server = [run('a', 'postmarket', 'success'), run('b', 'weekend', 'partial')]
    await vi.advanceTimersByTimeAsync(1000)
    expect(f.api.status.mock.calls.length).toBeGreaterThan(requestCount)
    expect(f.state.activeCount.value).toBe(0)
    expect(f.state.busyByJob.value.weekend).toBeFalsy()
    expect(f.onRunsFinished).toHaveBeenCalledTimes(2)
    expect(f.onRunsFinished).toHaveBeenLastCalledWith([server[1]])
    const finishedCount = f.api.status.mock.calls.length
    await vi.advanceTimersByTimeAsync(10_000)
    expect(f.api.status).toHaveBeenCalledTimes(finishedCount)
  })

  it('coalesces simultaneous list refreshes and clears loading after their shared response', async () => {
    const f = fixture()
    const pending = deferred<StatusResponse>()
    f.api.status.mockReturnValue(pending.promise)

    const requests = [f.state.refresh(), f.state.refresh(), f.state.refresh()]
    await flushMicrotasks()
    expect(f.api.status).toHaveBeenCalledTimes(1)
    expect(f.state.loading.value).toBe(true)
    const history = [run('done', 'postmarket', 'success')]
    pending.resolve({ items: history })

    expect(await Promise.all(requests)).toEqual([true, true, true])
    expect(f.state.loading.value).toBe(false)
    expect(f.state.recentRuns.value).toEqual(history)
  })

  it('deduplicates concurrent starts of the same job before the POST returns', async () => {
    const f = fixture()
    const pending = deferred<WarmupRun>()
    const running = run('a')
    f.api.start.mockReturnValue(pending.promise)
    f.api.status.mockResolvedValue({ items: [running] })

    const first = f.state.start('postmarket')
    const second = f.state.start('postmarket')
    await flushMicrotasks()
    expect(f.api.start).toHaveBeenCalledTimes(1)
    expect(f.state.busyByJob.value.postmarket).toBe(true)
    expect(f.state.canStart('postmarket')).toBe(false)
    pending.resolve(running)

    expect(await Promise.all([first, second])).toEqual([running, running])
    expect(f.onStarted).toHaveBeenCalledTimes(1)
    expect(f.state.activeCount.value).toBe(1)
  })

  it('reserves both concurrent slots during POSTs and rejects a third distinct job', async () => {
    const f = fixture()
    const a = deferred<WarmupRun>()
    const b = deferred<WarmupRun>()
    const server = [run('a'), run('b', 'weekend')]
    f.api.start.mockImplementation(job => job === 'postmarket' ? a.promise : b.promise)
    f.api.status.mockImplementation(async id => id ? server.find(item => item.id === id)! : { items: server })

    const first = f.state.start('postmarket')
    const second = f.state.start('weekend')
    await flushMicrotasks()
    expect(f.state.canStart('premarket')).toBe(false)
    expect(f.state.busyByJob.value.postmarket).toBe(true)
    expect(f.state.busyByJob.value.weekend).toBe(true)
    expect(await f.state.start('premarket')).toBeNull()
    expect(f.api.start).toHaveBeenCalledTimes(2)
    expect(f.api.start.mock.calls.map(([job]) => job)).toEqual(['postmarket', 'weekend'])

    a.resolve(server[0])
    b.resolve(server[1])
    await Promise.all([first, second])
    expect(f.state.activeCount.value).toBe(2)
    expect(f.state.canStart('intraday')).toBe(false)
    expect(f.onStarted).toHaveBeenCalledTimes(2)
  })

  it('does not submit another POST for a job already restored as running', async () => {
    const f = fixture()
    f.api.status.mockResolvedValue({ items: [run('a')] })
    await f.state.refresh()

    expect(await f.state.start('postmarket')).toBeNull()
    expect(f.api.start).not.toHaveBeenCalled()
    expect(f.state.busyByJob.value.postmarket).toBe(true)
  })

  it('releases a failed start reservation and reports the error without creating a failed run', async () => {
    const f = fixture()
    const failure = new Error('start unavailable')
    f.api.start.mockRejectedValue(failure)

    expect(await f.state.start('postmarket')).toBeNull()
    expect(f.state.canStart('postmarket')).toBe(true)
    expect(f.state.busyByJob.value.postmarket).toBeFalsy()
    expect(f.state.recentRuns.value).toEqual([])
    expect(f.onStartError).toHaveBeenCalledTimes(1)
    expect(f.onStartError).toHaveBeenCalledWith(failure)
    expect(f.onStarted).not.toHaveBeenCalled()
  })

  it('ignores a late POST after dispose: no started notification, list fetch, or state mutation', async () => {
    const f = fixture()
    const pending = deferred<WarmupRun>()
    f.api.start.mockReturnValue(pending.promise)
    const task = f.state.start('postmarket')
    await flushMicrotasks()
    f.state.dispose()
    const snapshot = [...f.state.recentRuns.value]
    pending.resolve(run('late'))
    await task

    expect(f.state.recentRuns.value).toEqual(snapshot)
    expect(f.onStarted).not.toHaveBeenCalled()
    expect(f.onRunsFinished).not.toHaveBeenCalled()
    expect(f.api.status).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(f.api.status).not.toHaveBeenCalled()
  })

  it('silences a late rejected POST after dispose', async () => {
    const f = fixture()
    const pending = deferred<WarmupRun>()
    f.api.start.mockReturnValue(pending.promise)
    const task = f.state.start('postmarket')
    await flushMicrotasks()
    f.state.dispose()
    const previousError = f.state.error.value
    pending.reject(new Error('late network failure'))

    expect(await task).toBeNull()
    expect(f.state.error.value).toBe(previousError)
    expect(f.onStartError).not.toHaveBeenCalled()
    expect(f.api.status).not.toHaveBeenCalled()
  })

  it('automatically disposes on Vue effect scope teardown', async () => {
    const f = fixture()
    const pending = deferred<WarmupRun>()
    f.api.start.mockReturnValue(pending.promise)
    const task = f.state.start('postmarket')
    await flushMicrotasks()
    f.scope.stop()
    pending.resolve(run('late'))
    await task

    expect(f.onStarted).not.toHaveBeenCalled()
    expect(f.api.status).not.toHaveBeenCalled()
    expect(f.state.recentRuns.value).toEqual([])
  })

  it('ignores a late list response when disposed during the post-start refresh', async () => {
    const f = fixture()
    const pendingList = deferred<StatusResponse>()
    f.api.start.mockResolvedValue(run('a'))
    f.api.status.mockReturnValue(pendingList.promise)
    const task = f.state.start('postmarket')
    await flushMicrotasks()
    expect(f.api.status).toHaveBeenCalledTimes(1)
    f.state.dispose()
    const snapshot = [...f.state.recentRuns.value]
    const notifications = f.onStarted.mock.calls.length
    pendingList.resolve({ items: [run('a', 'postmarket', 'success')] })
    await task
    await flushMicrotasks()

    expect(f.state.recentRuns.value).toEqual(snapshot)
    expect(f.onStarted).toHaveBeenCalledTimes(notifications)
    expect(f.onRunsFinished).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(f.api.status).toHaveBeenCalledTimes(1)
  })

  it('ignores a late polling response after dispose and does not schedule another poll', async () => {
    const f = fixture()
    const pending = deferred<StatusResponse>()
    f.api.status.mockResolvedValueOnce({ items: [run('a')] }).mockReturnValue(pending.promise)
    await f.state.refresh()
    await vi.advanceTimersByTimeAsync(1000)
    expect(f.api.status).toHaveBeenCalledTimes(2)
    f.state.dispose()
    const snapshot = [...f.state.recentRuns.value]
    pending.resolve({ items: [run('a', 'postmarket', 'success')] })
    await flushMicrotasks()

    expect(f.state.recentRuns.value).toEqual(snapshot)
    expect(f.onRunsFinished).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(f.api.status).toHaveBeenCalledTimes(2)
  })

  it('retains running state after a polling outage, then retries with backoff and recovers', async () => {
    const f = fixture()
    const failure = new Error('temporary outage')
    f.api.status
      .mockResolvedValueOnce({ items: [run('a')] })
      .mockRejectedValueOnce(failure)
      .mockResolvedValue({ items: [run('a', 'postmarket', 'success')] })
    await f.state.refresh()
    await vi.advanceTimersByTimeAsync(1000)

    expect(f.state.recentRuns.value[0].status).toBe('running')
    expect(f.state.busyByJob.value.postmarket).toBe(true)
    expect(f.state.canStart('postmarket')).toBe(false)
    expect(f.onRunsFinished).not.toHaveBeenCalled()
    expect(f.onPollError).toHaveBeenCalledWith(failure)
    expect(f.state.error.value).not.toBe('')
    expect(f.api.status).toHaveBeenCalledTimes(2)

    await vi.advanceTimersByTimeAsync(1000)
    expect(f.api.status).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(1000)
    expect(f.api.status).toHaveBeenCalledTimes(3)
    expect(f.state.activeCount.value).toBe(0)
    expect(f.onRunsFinished).toHaveBeenCalledTimes(1)
    expect(f.state.error.value).toBe('')
  })

  it('shares an in-flight poll with manual refresh requests rather than issuing extra lists', async () => {
    const f = fixture()
    const pending = deferred<StatusResponse>()
    f.api.status.mockResolvedValueOnce({ items: [run('a')] }).mockReturnValue(pending.promise)
    await f.state.refresh()
    await vi.advanceTimersByTimeAsync(1000)
    const requests = [f.state.refresh(), f.state.refresh()]
    await flushMicrotasks()
    expect(f.api.status).toHaveBeenCalledTimes(2)

    const completed = run('a', 'postmarket', 'success')
    pending.resolve({ items: [completed] })
    expect(await Promise.all(requests)).toEqual([true, true])
    expect(f.onRunsFinished).toHaveBeenCalledTimes(1)
    expect(f.onRunsFinished).toHaveBeenCalledWith([completed])
    expect(f.state.loading.value).toBe(false)
  })

  it('checks each known running ID omitted from a truncated list instead of silently unlocking it', async () => {
    const f = fixture()
    let omitActive = false
    const completed = run('a', 'postmarket', 'success')
    f.api.status.mockImplementation(async id => {
      if (id === 'a') return completed
      return { items: omitActive ? [] : [run('a')] }
    })
    await f.state.refresh()
    omitActive = true

    expect(await f.state.refresh()).toBe(true)
    expect(f.api.status).toHaveBeenCalledWith('a')
    expect(f.state.recentRuns.value.find(item => item.id === 'a')).toEqual(completed)
    expect(f.state.activeCount.value).toBe(0)
    expect(f.onRunsFinished).toHaveBeenCalledWith([completed])
  })

  it('keeps omitted active jobs busy when their individual status fetch fails', async () => {
    const f = fixture()
    let omitActive = false
    f.api.status.mockImplementation(async id => {
      if (id) throw new Error('individual status unavailable')
      return { items: omitActive ? [] : [run('a')] }
    })
    await f.state.refresh()
    omitActive = true
    await f.state.refresh()

    expect(f.api.status).toHaveBeenCalledWith('a')
    expect(f.state.recentRuns.value.find(item => item.id === 'a')?.status).toBe('running')
    expect(f.state.busyByJob.value.postmarket).toBe(true)
    expect(f.state.canStart('postmarket')).toBe(false)
    expect(f.onRunsFinished).not.toHaveBeenCalled()
    expect(f.state.error.value).not.toBe('')
  })

  it('does not let stale lists regress terminal jobs to running or repeat completion notifications', async () => {
    const f = fixture()
    const running = run('a')
    const completed = run('a', 'postmarket', 'success')
    f.api.status
      .mockResolvedValueOnce({ items: [running] })
      .mockResolvedValueOnce({ items: [completed] })
      .mockResolvedValueOnce({ items: [completed] })
      .mockResolvedValue({ items: [running] })
    await f.state.refresh()
    await f.state.refresh()
    await f.state.refresh()
    await f.state.refresh()

    expect(f.state.recentRuns.value.find(item => item.id === 'a')).toEqual(completed)
    expect(f.state.activeCount.value).toBe(0)
    expect(f.state.canStart('postmarket')).toBe(true)
    expect(f.onRunsFinished).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(10_000)
    expect(f.api.status).toHaveBeenCalledTimes(4)
  })

  it('batches all terminal transitions from a single refresh into one notification', async () => {
    const f = fixture()
    const completed = [run('a', 'postmarket', 'failed'), run('b', 'weekend', 'skipped')]
    f.api.status
      .mockResolvedValueOnce({ items: [run('a'), run('b', 'weekend')] })
      .mockResolvedValue({ items: completed })
    await f.state.refresh()
    await f.state.refresh()

    expect(f.onRunsFinished).toHaveBeenCalledTimes(1)
    expect(f.onRunsFinished.mock.calls[0][0]).toEqual(expect.arrayContaining(completed))
    expect(f.onRunsFinished.mock.calls[0][0]).toHaveLength(2)
    expect(f.state.activeCount.value).toBe(0)
  })

  it('returns false for list failures, clears loading, and allows a later manual retry', async () => {
    const f = fixture()
    f.api.status.mockRejectedValueOnce(new Error('offline')).mockResolvedValue({ items: [] })

    expect(await f.state.refresh()).toBe(false)
    expect(f.state.loading.value).toBe(false)
    expect(f.state.error.value).not.toBe('')
    expect(f.state.recentRuns.value).toEqual([])
    expect(await f.state.refresh()).toBe(true)
    expect(f.state.loading.value).toBe(false)
    expect(f.state.error.value).toBe('')
  })

  it('marks a missing 404 run as unverified instead of fabricating success or failure', async () => {
    const f = fixture()
    let lost = false
    f.api.status.mockImplementation(async id => {
      if (id) throw { response: { status: 404 } }
      return { items: lost ? [] : [run('a')] }
    })
    await f.state.refresh()
    lost = true

    expect(await f.state.refresh()).toBe(true)
    const unavailable = f.state.recentRuns.value.find(item => item.id === 'a')!
    expect(unavailable.status).toBe('unknown')
    expect(unavailable.reason).toBe('tracking_lost')
    expect(unavailable.error).toBeTruthy()
    expect(f.state.activeCount.value).toBe(0)
    expect(f.state.canStart('postmarket')).toBe(true)
    expect(f.onRunsFinished).toHaveBeenCalledTimes(1)
    expect(f.onRunsFinished).toHaveBeenCalledWith([unavailable])
    expect(f.onPollError).not.toHaveBeenCalled()
  })

  it('backs off consecutive failures without repeated error notifications and resets after recovery', async () => {
    const f = fixture()
    f.api.status
      .mockResolvedValueOnce({ items: [run('a')] })
      .mockRejectedValueOnce(new Error('outage 1'))
      .mockRejectedValueOnce(new Error('outage 2'))
      .mockResolvedValueOnce({ items: [run('a')] })
      .mockResolvedValue({ items: [run('a', 'postmarket', 'success')] })
    await f.state.refresh()
    await vi.advanceTimersByTimeAsync(1000)
    expect(f.api.status).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(2000)
    expect(f.api.status).toHaveBeenCalledTimes(3)
    expect(f.onPollError).toHaveBeenCalledTimes(1)
    expect(f.state.busyByJob.value.postmarket).toBe(true)

    await vi.advanceTimersByTimeAsync(3999)
    expect(f.api.status).toHaveBeenCalledTimes(3)
    await vi.advanceTimersByTimeAsync(1)
    expect(f.api.status).toHaveBeenCalledTimes(4)
    expect(f.state.error.value).toBe('')
    expect(f.state.activeCount.value).toBe(1)
    await vi.advanceTimersByTimeAsync(999)
    expect(f.api.status).toHaveBeenCalledTimes(4)
    await vi.advanceTimersByTimeAsync(1)
    expect(f.api.status).toHaveBeenCalledTimes(5)
    expect(f.state.activeCount.value).toBe(0)
    expect(f.onRunsFinished).toHaveBeenCalledTimes(1)
  })

  it('ignores a late per-ID reconciliation response after scope disposal', async () => {
    const f = fixture()
    const pending = deferred<StatusResponse>()
    let omitActive = false
    f.api.status.mockImplementation(async id => {
      if (id) return pending.promise
      return { items: omitActive ? [] : [run('a')] }
    })
    await f.state.refresh()
    omitActive = true
    const task = f.state.refresh()
    await flushMicrotasks()
    expect(f.api.status).toHaveBeenCalledWith('a')
    f.scope.stop()
    const snapshot = [...f.state.recentRuns.value]
    pending.resolve(run('a', 'postmarket', 'success'))

    expect(await task).toBe(false)
    expect(f.state.recentRuns.value).toEqual(snapshot)
    expect(f.onRunsFinished).not.toHaveBeenCalled()
    expect(f.onPollError).not.toHaveBeenCalled()
    const requestCount = f.api.status.mock.calls.length
    await vi.advanceTimersByTimeAsync(10_000)
    expect(f.api.status).toHaveBeenCalledTimes(requestCount)
  })

  it('counts a POST reservation and its list-restored run only once', async () => {
    const f = fixture()
    const pending = deferred<WarmupRun>()
    const running = run('a')
    f.api.start.mockReturnValue(pending.promise)
    f.api.status.mockResolvedValue({ items: [running] })
    const task = f.state.start('postmarket')
    await f.state.refresh()

    expect(f.state.activeCount.value).toBe(1)
    expect(f.state.busyByJob.value.postmarket).toBe(true)
    expect(f.state.canStart('weekend')).toBe(true)
    pending.resolve(running)
    await task
    expect(f.state.activeCount.value).toBe(1)
    expect(f.state.recentRuns.value.filter(item => item.id === 'a')).toHaveLength(1)
  })

  it('reconciles a rejected POST whose job was accepted on the server before the response failed', async () => {
    const f = fixture()
    const running = run('accepted-on-server')
    f.api.start.mockRejectedValue(new Error('response connection lost'))
    f.api.status.mockResolvedValue({ items: [running] })

    expect(await f.state.start('postmarket')).toBeNull()
    await flushMicrotasks()
    expect(f.api.status).toHaveBeenCalledTimes(1)
    expect(f.state.recentRuns.value).toEqual([running])
    expect(f.state.busyByJob.value.postmarket).toBe(true)
    expect(f.state.canStart('postmarket')).toBe(false)
    expect(f.onStarted).not.toHaveBeenCalled()
    expect(f.onStartError).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1000)
    expect(f.api.status).toHaveBeenCalledTimes(2)
  })
})
