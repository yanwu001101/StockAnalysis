import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { UserInfo, WatchlistGroup } from '@/types'
import * as userApi from '@/api/user'

export const useUserStore = defineStore('user', () => {
  const token = ref(localStorage.getItem('token') || '')
  const userInfo = ref<UserInfo | null>(null)
  const watchlists = ref<WatchlistGroup[]>([])
  const PROFILE_TTL = 60_000
  let fetchedAt = 0
  let retryAt = 0
  let session = 0
  let pending: { token: string; promise: Promise<void> } | null = null
  // Derive from token so it stays in sync — older versions held a stale ref
  // that lied after silent token clearing (e.g. failed hydrate on refresh).
  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => userInfo.value?.role === 'ADMIN')

  async function login(username: string, password: string) {
    const res = await userApi.login(username, password)
    session++
    pending = null
    token.value = res.token
    userInfo.value = res.user
    localStorage.setItem('token', res.token)
    fetchedAt = Date.now()
    retryAt = 0
    return res
  }

  async function fetchUserInfo(force = false) {
    if (!token.value) return
    const requestToken = token.value
    if (pending?.token === requestToken) return pending.promise
    if (!force && ((userInfo.value && Date.now() - fetchedAt < PROFILE_TTL) || Date.now() < retryAt)) return
    const currentSession = session
    const promise = (async () => {
      try {
        const info = await userApi.getUserInfo()
        if (currentSession !== session || requestToken !== token.value) return
        userInfo.value = info
        fetchedAt = Date.now()
        retryAt = 0
      } catch (e: any) {
        if (currentSession !== session || requestToken !== token.value) return
        // 网络失败保留会话；旧会话请求不能踢掉新登录的用户。
        if (e?.response?.status === 401 || e?.code === 401) logout()
        else retryAt = Date.now() + 5_000
      }
    })()
    pending = { token: requestToken, promise }
    try { await promise } finally {
      if (pending?.promise === promise) pending = null
    }
  }

  /**
   * Restore session on app boot. Cheap no-op when there's no token;
   * silently logs out (and lets axios interceptor redirect) on a stale one.
   */
  async function hydrate() {
    if (!token.value) return
    await fetchUserInfo()
  }

  async function fetchWatchlists() {
    watchlists.value = await userApi.getWatchlists()
  }

  function logout() {
    session++
    pending = null
    fetchedAt = retryAt = 0
    token.value = ''
    userInfo.value = null
    watchlists.value = []
    localStorage.removeItem('token')
  }

  return { token, userInfo, watchlists, isLoggedIn, isAdmin, login, fetchUserInfo, hydrate, fetchWatchlists, logout }
})
