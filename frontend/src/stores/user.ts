import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { UserInfo, WatchlistGroup } from '@/types'
import * as userApi from '@/api/user'

export const useUserStore = defineStore('user', () => {
  const token = ref(localStorage.getItem('token') || '')
  const userInfo = ref<UserInfo | null>(null)
  const watchlists = ref<WatchlistGroup[]>([])
  // Derive from token so it stays in sync — older versions held a stale ref
  // that lied after silent token clearing (e.g. failed hydrate on refresh).
  const isLoggedIn = computed(() => !!token.value)

  async function login(username: string, password: string) {
    const res = await userApi.login(username, password)
    token.value = res.token
    userInfo.value = res.user
    localStorage.setItem('token', res.token)
    return res
  }

  async function fetchUserInfo() {
    if (!token.value) return
    try {
      userInfo.value = await userApi.getUserInfo()
    } catch {
      logout()
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
    token.value = ''
    userInfo.value = null
    watchlists.value = []
    localStorage.removeItem('token')
  }

  return { token, userInfo, watchlists, isLoggedIn, login, fetchUserInfo, hydrate, fetchWatchlists, logout }
})
