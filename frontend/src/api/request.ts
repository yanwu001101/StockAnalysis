import axios from 'axios'
import { ElMessage } from 'element-plus'
import type { ApiResponse } from '@/types'

// API 根地址解析顺序：设置页里手动填的 > 打包时的 VITE_API_BASE > 同源 /api。
// 浏览器里同源代理即可；打成 App（Capacitor）后页面不在服务器上，必须指向绝对地址。
const API_BASE_KEY = 'apiBase'
export const DEFAULT_API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) || '/api'

export function getApiBase(): string {
  try {
    const saved = localStorage.getItem(API_BASE_KEY)
    if (saved && saved.trim()) return normalizeApiBase(saved)
  } catch { /* localStorage 不可用 */ }
  return DEFAULT_API_BASE
}

export function setApiBase(v: string | null | undefined) {
  const clean = v?.trim()
  try {
    if (clean) localStorage.setItem(API_BASE_KEY, normalizeApiBase(clean))
    else localStorage.removeItem(API_BASE_KEY)
  } catch { /* ignore */ }
  request.defaults.baseURL = getApiBase()
}

/** 允许只填主机（192.168.10.18:18080），自动补 http:// 与 /api。 */
export function normalizeApiBase(v: string): string {
  let s = v.trim().replace(/\/+$/, '')
  if (!s) return DEFAULT_API_BASE
  if (s.startsWith('/')) return s
  if (!/^https?:\/\//i.test(s)) s = 'http://' + s
  if (!/\/api$/i.test(s)) s += '/api'
  return s
}

const request = axios.create({
  baseURL: getApiBase(),
  timeout: 360000,
  headers: {
    'Content-Type': 'application/json',
  },
})

request.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

request.interceptors.response.use(
  (response) => {
    const res = response.data as ApiResponse<any>
    if (res.code !== 200) {
      ElMessage.error(res.message || '请求失败')
      return Promise.reject(new Error(res.message || '请求失败'))
    }
    if (res.dataTime != null) {
      // 在拦截器内动态 import,避免和 store 初始化顺序产生循环依赖
      import('@/stores/refresh').then(({ useRefreshStore }) => {
        useRefreshStore().recordDataTime(res.dataTime!)
      })
    }
    return res.data
  },
  (error) => {
    if (axios.isCancel(error)) return Promise.reject(error)
    if (error.response?.status === 401) {
      // 仅用户域接口（登录态）才强制踢回登录；行情/选股等公开接口偶发 401 不应清 token。
      const url = String(error.config?.url || '')
      const needsAuth = /\/(user|portfolio|ai|admin)\b/i.test(url)
      if (needsAuth) {
        try { localStorage.removeItem('token') } catch { /* ignore */ }
        const path = window.location.pathname
        if (path !== '/login' && !path.startsWith('/login')) {
          window.location.href = '/login'
        }
        return Promise.reject(error)
      }
      // 公开接口 401：只提示，不登出
      ElMessage.error(error.response?.data?.message || '未授权（无需登录的接口异常）')
      return Promise.reject(error)
    }
    const message = error.response?.data?.message || error.response?.data?.msg || error.message || '网络错误'
    ElMessage.error(message)
    return Promise.reject(error)
  }
)

export default request
