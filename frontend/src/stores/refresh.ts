import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useSettingsStore } from './settings'

type Reloader = () => Promise<any> | any

interface RegisterOpts {
  autoRefresh?: boolean
}

export const useRefreshStore = defineStore('refresh', () => {
  const localTimeMs = ref<number | null>(null)
  const dataTimeMs = ref<number | null>(null)
  const isRefreshing = ref(false)
  const label = ref('')
  const reloader = ref<Reloader | null>(null)
  const autoRefreshEnabled = ref(false)

  let timer: number | null = null
  let currentLabel = ''

  function recordDataTime(ms: number) {
    // 每次 axios 响应:更新 dataTimeMs(取最新, LWW)+ 同步 stamp localTimeMs
    // 这样 view 内部按钮触发的请求(不走 invokeReloader)也能让 RefreshBar 跟上
    dataTimeMs.value = ms
    localTimeMs.value = Date.now()
  }

  async function invokeReloader(silent = false) {
    if (!reloader.value || isRefreshing.value) return
    isRefreshing.value = true
    try {
      await reloader.value()
      // reloader 内部触发的 axios 响应已经 stamp 过 localTimeMs/dataTimeMs;
      // 补一刀确保 reloader 不发任何请求的边缘情况下时间也有更新
      localTimeMs.value = Date.now()
      if (!silent) {
        const ts = new Date(localTimeMs.value).toLocaleTimeString('zh-CN', { hour12: false })
        ElMessage.success({ message: `数据已刷新 · ${ts}`, duration: 1800 })
      }
    } catch (e: any) {
      ElMessage.error(`刷新失败: ${e?.message || '未知错误'}`)
    } finally {
      isRefreshing.value = false
    }
  }

  function startAutoRefresh() {
    stopAutoRefresh()
    if (!autoRefreshEnabled.value) return
    const settings = useSettingsStore()
    const intervalSec = Math.max(5, settings.refreshInterval || 15)
    timer = window.setInterval(() => {
      invokeReloader(true)
    }, intervalSec * 1000)
  }

  function stopAutoRefresh() {
    if (timer != null) {
      window.clearInterval(timer)
      timer = null
    }
  }

  function registerReloader(lbl: string, fn: Reloader, opts: RegisterOpts = {}) {
    currentLabel = lbl
    label.value = lbl
    reloader.value = fn
    localTimeMs.value = null
    dataTimeMs.value = null
    autoRefreshEnabled.value = opts.autoRefresh !== false
    startAutoRefresh()
  }

  function unregisterReloader(lbl: string) {
    if (lbl !== currentLabel) return  // 防竞态:别人已接管
    currentLabel = ''
    label.value = ''
    reloader.value = null
    autoRefreshEnabled.value = false
    localTimeMs.value = null
    dataTimeMs.value = null
    stopAutoRefresh()
  }

  const settings = useSettingsStore()
  watch(() => settings.refreshInterval, () => {
    if (autoRefreshEnabled.value) startAutoRefresh()
  })

  return {
    localTimeMs,
    dataTimeMs,
    isRefreshing,
    label,
    reloader,
    recordDataTime,
    invokeReloader,
    registerReloader,
    unregisterReloader,
  }
})
