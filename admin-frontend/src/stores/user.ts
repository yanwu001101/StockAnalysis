import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import * as authApi from '@/api/auth'

export const useUserStore = defineStore('adminUser', () => {
  const token = ref(localStorage.getItem('admin_token') || '')
  const userInfo = ref<authApi.AdminUserInfo | null>(null)
  const isLoggedIn = computed(() => !!token.value)
  const role = computed(() => userInfo.value?.role || '')
  const isAdmin = computed(() => userInfo.value?.role === 'ADMIN')

  async function login(username: string, password: string) {
    const res = await authApi.login(username, password)
    if (res.user.role !== 'ADMIN') {
      throw new Error('该账号无管理员权限')
    }
    token.value = res.token
    userInfo.value = res.user
    localStorage.setItem('admin_token', res.token)
    return res
  }

  async function hydrate() {
    if (!token.value) return
    try {
      const u = await authApi.getMyInfo()
      if (u.role !== 'ADMIN') {
        logout()
        return
      }
      userInfo.value = u
    } catch {
      logout()
    }
  }

  function logout() {
    token.value = ''
    userInfo.value = null
    localStorage.removeItem('admin_token')
  }

  return { token, userInfo, isLoggedIn, role, isAdmin, login, hydrate, logout }
})
