import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { nextTick } from 'vue'
import * as cloud from '@/api/strategyConfig'
import { useUserStore } from '@/stores/user'
import { useStrategyStore } from '@/stores/strategy'

vi.mock('@/api/strategyConfig', () => ({ getStrategyConfig: vi.fn(), putStrategyConfig: vi.fn() }))
vi.mock('@/api/user', () => ({ getUserInfo: vi.fn(), login: vi.fn(), getWatchlists: vi.fn() }))
const user = (id: number) => ({ id, username: String(id), nickname: 'test', avatar: '', createdAt: '' })
const empty = { version: 0, config: null, presets: [] }
async function settle() { await nextTick(); await Promise.resolve(); await nextTick() }
beforeEach(() => {
  vi.useFakeTimers(); localStorage.clear(); setActivePinia(createPinia())
  vi.mocked(cloud.getStrategyConfig).mockReset().mockResolvedValue(empty)
  vi.mocked(cloud.putStrategyConfig).mockReset().mockImplementation(async p => ({ ...p, version: p.version + 1 }))
})
afterEach(() => vi.useRealTimers())

describe('strategy preferences', () => {
  it('does not mutate the default objects and persists active local weights', () => {
    const store = useStrategyStore()
    const initial = store.strategies[0].weight
    store.updateWeight(store.strategies[0].id, 0)
    expect(JSON.parse(localStorage.getItem('strategy-config-v1:guest')!).config[store.strategies[0].id].weight).toBe(0)
    store.resetToDefault(); expect(store.strategies[0].weight).toBe(initial)
  })
  it('debounces cloud saves and preserves zero weights', async () => {
    const auth = useUserStore(); auth.token = 'a'; auth.userInfo = user(1)
    const store = useStrategyStore(); await settle()
    store.updateWeight('piotroski_f', 2); store.updateWeight('piotroski_f', 0)
    await vi.advanceTimersByTimeAsync(501)
    expect(cloud.putStrategyConfig).toHaveBeenCalledTimes(1)
    expect(vi.mocked(cloud.putStrategyConfig).mock.calls[0][0].config?.piotroski_f.weight).toBe(0)
  })
  it('isolates accounts and ignores an older pending cloud response', async () => {
    let resolve!: (v: any) => void
    vi.mocked(cloud.getStrategyConfig).mockReturnValueOnce(new Promise(r => { resolve = r }))
    const auth = useUserStore(); auth.token = 'a'; auth.userInfo = user(1)
    const store = useStrategyStore()
    auth.token = 'b'; auth.userInfo = user(2); await settle()
    resolve({ ...empty, version: 7, config: { piotroski_f: { weight: 999, enabled: true } } }); await settle()
    expect(store.strategies[0].weight).not.toBe(999)
    expect(cloud.putStrategyConfig).not.toHaveBeenCalled()
  })
  it('keeps local changes on cloud conflict and never retries blind overwrites', async () => {
    vi.mocked(cloud.putStrategyConfig).mockRejectedValue({ response: { status: 409 } })
    const auth = useUserStore(); auth.token = 'a'; auth.userInfo = user(1)
    const store = useStrategyStore(); await settle()
    store.updateWeight('piotroski_f', 7); await vi.advanceTimersByTimeAsync(501)
    expect(store.syncStatus).toBe('conflict')
    expect(store.strategies[0].weight).toBe(7)
    expect(JSON.parse(localStorage.getItem('strategy-config-v1:1')!).dirty).toBe(true)
  })
})
