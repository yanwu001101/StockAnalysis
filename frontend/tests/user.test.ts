import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import * as api from '@/api/user'
import { useUserStore } from '@/stores/user'

vi.mock('@/api/user', () => ({ getUserInfo: vi.fn(), login: vi.fn(), getWatchlists: vi.fn() }))
const a = { id: 1, username: 'a', nickname: 'A', avatar: '', createdAt: '' }
const b = { ...a, id: 2, username: 'b' }
beforeEach(() => {
  vi.useFakeTimers(); vi.setSystemTime(new Date('2026-10-11T12:00:00Z'))
  vi.mocked(api.getUserInfo).mockReset(); vi.mocked(api.login).mockReset()
  localStorage.clear(); localStorage.setItem('token', 'a'); setActivePinia(createPinia())
})
afterEach(() => vi.useRealTimers())

describe('profile TTL and session isolation', () => {
  it('collapses concurrent hydration and caches successful profiles', async () => {
    vi.mocked(api.getUserInfo).mockResolvedValue(a)
    const store = useUserStore()
    await Promise.all(Array.from({ length: 10 }, () => store.hydrate()))
    await store.hydrate()
    expect(api.getUserInfo).toHaveBeenCalledTimes(1)
    vi.advanceTimersByTime(60_001); await store.hydrate()
    expect(api.getUserInfo).toHaveBeenCalledTimes(2)
  })
  it('ignores a late profile after logout', async () => {
    let resolve!: (value: typeof a) => void
    vi.mocked(api.getUserInfo).mockReturnValue(new Promise(r => { resolve = r }))
    const store = useUserStore(); const task = store.hydrate()
    store.logout(); resolve(a); await task
    expect(store.userInfo).toBeNull(); expect(store.isLoggedIn).toBe(false)
  })
  it('does not log out the new account on an old request 401', async () => {
    let reject!: (error: unknown) => void
    vi.mocked(api.getUserInfo).mockReturnValue(new Promise((_, r) => { reject = r }))
    vi.mocked(api.login).mockResolvedValue({ token: 'b', user: b })
    const store = useUserStore(); const task = store.hydrate()
    await store.login('b', 'test'); reject({ response: { status: 401 } }); await task
    expect(store.token).toBe('b'); expect(store.userInfo?.id).toBe(2)
  })
  it('keeps the token on outages and backs off retries', async () => {
    vi.mocked(api.getUserInfo).mockRejectedValue(new Error('offline'))
    const store = useUserStore(); await store.hydrate(); await store.hydrate()
    expect(store.token).toBe('a'); expect(api.getUserInfo).toHaveBeenCalledTimes(1)
  })
  it('expires the current session for application-level 401', async () => {
    vi.mocked(api.getUserInfo).mockRejectedValue({ code: 401 })
    const store = useUserStore(); await store.hydrate()
    expect(store.isLoggedIn).toBe(false)
  })
})
