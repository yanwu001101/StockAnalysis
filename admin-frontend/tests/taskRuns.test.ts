import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, type App } from 'vue'
import { useTaskRuns } from '@/composables/useTaskRuns'
import * as api from '@/api/tasks'
vi.mock('@/api/tasks', () => ({ listRuns: vi.fn() }))
let app: App | undefined
let host: HTMLDivElement
beforeEach(() => { vi.useFakeTimers(); vi.mocked(api.listRuns).mockReset(); host = document.createElement('div') })
afterEach(() => { app?.unmount(); vi.useRealTimers() })
function mount() {
  let state!: ReturnType<typeof useTaskRuns>
  app = createApp({ setup() { state = useTaskRuns(); return () => h('div') } }); app.mount(host)
  return state
}
describe('read-only task history polling', () => {
  it('queues another read when a submitted run races with an older in-flight history read', async () => {
    let finish!: (value: { items: api.JobRun[] }) => void
    vi.mocked(api.listRuns).mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
      .mockResolvedValueOnce({ items: [{ id: 'new', job: 'daily', status: 'running', started_at: '' }] })
    const state = mount(); const old = state.refresh()
    await state.refresh() // a manual submission asks for history while the old read is pending
    finish({ items: [] }); await old; await vi.advanceTimersByTimeAsync(1)
    expect(api.listRuns).toHaveBeenCalledTimes(2)
    expect(state.runs.value[0].id).toBe('new')
  })
  it('polls active runs until a partial terminal result, never inventing success', async () => {
    vi.mocked(api.listRuns).mockResolvedValueOnce({ items: [{ id: '1', job: 'daily', status: 'running', started_at: '' }] })
      .mockResolvedValueOnce({ items: [{ id: '1', job: 'daily', status: 'partial', started_at: '', reason: 'one provider failed' }] })
    const state = mount(); await state.refresh()
    await vi.advanceTimersByTimeAsync(5000)
    expect(state.runs.value[0].status).toBe('partial')
    await vi.advanceTimersByTimeAsync(15000)
    expect(api.listRuns).toHaveBeenCalledTimes(2)
  })
  it('shows read failures and stops polling on unmount', async () => {
    vi.mocked(api.listRuns).mockResolvedValueOnce({ items: [{ id: '1', job: 'daily', status: 'running', started_at: '' }] })
      .mockRejectedValueOnce(new Error('offline'))
    const state = mount(); await state.refresh(); await vi.advanceTimersByTimeAsync(5000)
    expect(state.error.value).toBe('offline')
    app?.unmount(); app = undefined
    await vi.advanceTimersByTimeAsync(15000)
    expect(api.listRuns).toHaveBeenCalledTimes(2)
  })
})
