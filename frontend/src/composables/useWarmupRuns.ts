import { computed, getCurrentScope, onScopeDispose, ref, shallowRef } from 'vue'
import { getWarmupStatus, startWarmup, type WarmupRun } from '@/api/admin'

type Job = Parameters<typeof startWarmup>[0]
type WarmupApi = { start: typeof startWarmup; status: typeof getWarmupStatus }
type Options = {
  api?: WarmupApi
  pollMs?: number
  maxConcurrent?: number
  onStarted?: (run: WarmupRun) => void
  onRunsFinished?: (runs: WarmupRun[]) => void
  onPollError?: (error: Error) => void
  onStartError?: (error: Error) => void
}

const statuses = new Set(['running', 'success', 'partial', 'failed', 'skipped', 'unknown'])
const asError = (error: unknown) => error instanceof Error ? error : new Error(String(error))

function parseRun(value: unknown): WarmupRun {
  const run = value as WarmupRun | null
  if (!run || typeof run.id !== 'string' || !run.id || typeof run.job !== 'string'
      || !statuses.has(run.status)) throw new Error('任务状态响应无效，请重试查询')
  return { ...run }
}

/** One lifecycle owns list refresh, active-run reconciliation and notifications.
 * The backend job is not cancelled by dispose(); only its UI observer is stopped.
 */
export function useWarmupRuns(options: Options = {}) {
  const api = options.api ?? { start: startWarmup, status: getWarmupStatus }
  const pollMs = options.pollMs ?? 2000
  const maxConcurrent = options.maxConcurrent ?? 2
  const recentRuns = shallowRef<WarmupRun[]>([])
  const startingJobs = ref<Job[]>([])
  const loading = ref(false)
  const error = ref('')
  const running = computed(() => recentRuns.value.filter(run => run.status === 'running'))
  const busyByJob = computed<Record<string, boolean>>(() => Object.fromEntries(
    [...running.value.map(run => run.job), ...startingJobs.value].map(job => [job, true])))
  const activeCount = computed(() => running.value.length + startingJobs.value.filter(
    job => !running.value.some(run => run.job === job)).length)
  const startPromises = new Map<Job, Promise<WarmupRun | null>>()
  const notified = new Set<string>()
  let refreshPromise: Promise<boolean> | null = null
  let timer: ReturnType<typeof setTimeout> | undefined
  let disposed = false
  let failures = 0

  function stopTimer() {
    if (timer !== undefined) clearTimeout(timer)
    timer = undefined
  }

  function schedulePoll() {
    stopTimer()
    if (disposed || !running.value.length) return
    timer = setTimeout(() => { timer = undefined; void refresh() },
      Math.min(pollMs * 2 ** Math.min(failures, 4), 30_000))
  }

  function mergeRuns(incoming: WarmupRun[], completed: WarmupRun[]) {
    if (disposed) return
    const next = new Map(recentRuns.value.map(run => [run.id, run]))
    for (const run of incoming) {
      const previous = next.get(run.id)
      // An older list response cannot undo a terminal status already observed.
      if (previous && previous.status !== 'running' && run.status === 'running') continue
      next.set(run.id, run)
      if (previous?.status === 'running' && run.status !== 'running' && !notified.has(run.id)) {
        notified.add(run.id)
        completed.push(run)
      }
    }
    const sorted = [...next.values()].sort((a, b) => (b.started_at || '').localeCompare(a.started_at || ''))
    // Retain every active run even if it fell outside the server's recent-20 list.
    recentRuns.value = [...sorted.filter(run => run.status === 'running'),
      ...sorted.filter(run => run.status !== 'running').slice(0, 20)]
  }

  function refresh(): Promise<boolean> {
    if (disposed) return Promise.resolve(false)
    if (refreshPromise) return refreshPromise
    stopTimer()
    loading.value = true
    const completed: WarmupRun[] = []
    const task = (async () => {
      try {
        const response = await api.status()
        if (disposed) return false
        if (!response || !('items' in response) || !Array.isArray(response.items)) {
          throw new Error('任务列表响应无效，请重试查询')
        }
        const listed = response.items.map(parseRun)
        mergeRuns(listed, completed)
        const ids = new Set(listed.map(run => run.id))
        const missing = running.value.filter(run => !ids.has(run.id))
        const details = await Promise.allSettled(missing.map(async previous => {
          try {
            const response = await api.status(previous.id)
            if (disposed) return null
            const run = parseRun(response)
            if (run.id !== previous.id) throw new Error('任务状态 ID 不匹配')
            return run
          } catch (cause) {
            if (disposed) return null
            const failure = cause as { response?: { status?: number }; code?: number }
            if (failure.response?.status === 404 || failure.code === 404) {
              return { ...previous, status: 'unknown' as const, reason: 'tracking_lost',
                error: '任务记录已不可用，无法确认执行结果；可能发生服务重启。' }
            }
            throw cause
          }
        }))
        if (disposed) return false
        const failed = details.find(result => result.status === 'rejected')
        mergeRuns(details.flatMap(result => result.status === 'fulfilled' && result.value ? [result.value] : []), completed)
        if (failed?.status === 'rejected') throw failed.reason
        error.value = ''
        failures = 0
        return true
      } catch (cause) {
        if (disposed) return false
        const failure = asError(cause)
        error.value = failure.message
        failures++
        // A failed query is not a failed job. Keep active jobs busy and retry.
        if (failures === 1) options.onPollError?.(failure)
        return false
      }
    })().finally(() => {
      if (refreshPromise === task) refreshPromise = null
      if (disposed) return
      loading.value = false
      if (completed.length) options.onRunsFinished?.(completed)
      schedulePoll()
    })
    refreshPromise = task
    return task
  }

  function canStart(job: Job): boolean {
    return !disposed && !busyByJob.value[job] && activeCount.value < maxConcurrent
  }

  function start(job: Job): Promise<WarmupRun | null> {
    if (disposed) return Promise.resolve(null)
    const pending = startPromises.get(job)
    if (pending) return pending
    if (!canStart(job)) {
      options.onStartError?.(new Error(busyByJob.value[job] ? '同名任务仍在运行' : '数据任务并发已满，请稍后重试'))
      return Promise.resolve(null)
    }
    startingJobs.value = [...startingJobs.value, job]
    const task = (async () => {
      try {
        const response = await api.start(job)
        if (disposed) return null
        const run = parseRun(response)
        if (run.job !== job) throw new Error('已启动任务类型不匹配，请刷新任务状态')
        mergeRuns([run], [])
        options.onStarted?.(run)
        void refresh()
        return run
      } catch (cause) {
        if (disposed) return null
        options.onStartError?.(asError(cause))
        // The POST may have reached the server even when its response failed.
        void refresh()
        return null
      }
    })().finally(() => {
      startPromises.delete(job)
      if (!disposed) startingJobs.value = startingJobs.value.filter(value => value !== job)
    })
    startPromises.set(job, task)
    return task
  }

  function dispose() {
    disposed = true
    stopTimer()
  }
  if (getCurrentScope()) onScopeDispose(dispose)

  return { recentRuns, busyByJob, activeCount, loading, error, canStart, refresh, start, dispose }
}
