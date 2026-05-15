import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { UserInfo, WatchlistGroup } from '@/types'
import * as userApi from '@/api/user'

export const useUserStore = defineStore('user', () => {
  const token = ref(localStorage.getItem('token') || '')
  const userInfo = ref<UserInfo | null>(null)
  const watchlists = ref<WatchlistGroup[]>([])
  const isLoggedIn = ref(!!token.value)

  async function login(username: string, password: string) {
    const res = await userApi.login(username, password)
    token.value = res.token
    userInfo.value = res.user
    isLoggedIn.value = true
    localStorage.setItem('token', res.token)
    return res
  }

  async function fetchUserInfo() {
    if (!token.value) return
    try {
      userInfo.value = await userApi.getUserInfo()
      isLoggedIn.value = true
    } catch {
      logout()
    }
  }

  async function fetchWatchlists() {
    watchlists.value = await userApi.getWatchlists()
  }

  function logout() {
    token.value = ''
    userInfo.value = null
    isLoggedIn.value = false
    watchlists.value = []
    localStorage.removeItem('token')
  }

  return { token, userInfo, watchlists, isLoggedIn, login, fetchUserInfo, fetchWatchlists, logout }
})
