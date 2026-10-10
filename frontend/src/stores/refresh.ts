import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useSettingsStore } from './settings'

type Reloader = () => Promise<any> | any

interface RegisterOpts {
  autoRefresh?: boolean
}

interface Entry {
  fn: Reloader
  autoRefresh: boolean
  running: boolean
}

/**
 * 多路刷新注册表。
 *
 * 旧实现是「单槽 reloader」：后注册的组件会覆盖前一个，而每个组件 onMounted
 * 又都调 `invokeReloader()`（= 跑当前那个 reloader）。结果一个页面里 N 个
 * useRefreshable 组件 = 同一批接口被拉 N 次，甚至跑的是别人的 loader。
 * 现在按 label 注册，组件挂载只跑自己的（invokeLabel），全局刷新按钮/轮询
 * 才跑全部（invokeReloader），每个 label 各自防重入。
 */
export const useRefreshStore = defineStore('refresh', () => {
  const localTimeMs = ref<number | null>(null)
  const dataTimeMs = ref<number | null>(null)
  const label = ref('')
  const autoRefreshEnabled = ref(false)

  const entries = new Map<string, Entry>()
  const size = ref(0)          // 响应式镜像，供 UI 判断「有没有可刷新的东西」
  const runningCount = ref(0)
  const isRefreshing = computed(() => runningCount.value > 0)
  // 兼容旧模板里的 `store.reloader` 真值判断（RefreshBar 显隐 / disabled）
  const hasReloader = computed(() => size.value > 0)

  let timer: number | null = null
  let currentLabel = ''

  function recordDataTime(ms: number) {
    // 每次 axios 响应:更新 dataTimeMs(取最新, LWW)+ 同步 stamp localTimeMs
    // 这样 view 内部按钮触发的请求(不走 invokeReloader)也能让 RefreshBar 跟上
    dataTimeMs.value = ms
    localTimeMs.value = Date.now()
  }

  function touchTimes(silent: boolean) {
    localTimeMs.value = Date.now()
    if (!silent) {
      const ts = new Date(localTimeMs.value).toLocaleTimeString('zh-CN', { hour12: false })
      ElMessage.success({ message: `数据已刷新 · ${ts}`, duration: 1800 })
    }
  }

  async function invokeLabel(lbl: string, silent = false) {
    const e = entries.get(lbl)
    if (!e || e.running) return   // 每个 loader 各自防重入
    e.running = true
    runningCount.value++
    try {
      await e.fn()
      touchTimes(silent)
    } catch (err: any) {
      ElMessage.error(`刷新失败: ${err?.message || '未知错误'}`)
    } finally {
      e.running = false
      runningCount.value = Math.max(0, runningCount.value - 1)
    }
  }

  /** 全局刷新（刷新按钮 / 自动轮询）：把已注册的全部各跑一次，跑过的不重复。 */
  async function invokeReloader(silent = false) {
    const todo = [...entries.entries()].filter(([, e]) => !e.running)
    if (!todo.length) return
    await Promise.allSettled(todo.map(([lbl]) => invokeLabel(lbl, true)))
    // 全部 reloader 内部都已 stamp 过；补一刀确保不发请求的组件也有时间
    touchTimes(silent)
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
    entries.set(lbl, { fn, autoRefresh: opts.autoRefresh !== false, running: false })
    size.value = entries.size
    currentLabel = lbl
    label.value = lbl
    localTimeMs.value = null
    dataTimeMs.value = null
    autoRefreshEnabled.value = [...entries.values()].some(e => e.autoRefresh)
    startAutoRefresh()
  }

  function unregisterReloader(lbl: string) {
    const e = entries.get(lbl)
    if (!e) return
    entries.delete(lbl)
    size.value = entries.size
    if (currentLabel === lbl) {
      const rest = [...entries.keys()]
      currentLabel = rest.length ? rest[rest.length - 1] : ''
      label.value = currentLabel
    }
    autoRefreshEnabled.value = [...entries.values()].some(x => x.autoRefresh)
    if (!entries.size) {
      localTimeMs.value = null
      dataTimeMs.value = null
      stopAutoRefresh()
    }
  }

  const settings = useSettingsStore()
  watch(() => settings.refreshInterval, () => {
    if (autoRefreshEnabled.value) startAutoRefresh()
  })

  return {
    localTimeMs, dataTimeMs, label, isRefreshing,
    reloader: hasReloader,
    recordDataTime,
    invokeReloader, invokeLabel,
    registerReloader, unregisterReloader,
  }
})
