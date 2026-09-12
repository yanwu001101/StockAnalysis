import { computed, ref } from 'vue'

// 手机/桌面判断（模块级单例，所有组件共享同一份状态）：
//   - 视口 ≤768px 视为手机；
//   - UA 是移动设备且视口 ≤1024px（手机横屏）也视为手机；
//   - 大平板横屏走桌面布局。
// 可用 ?view=mobile|desktop|auto 或设置页手动覆盖，覆盖值存 localStorage.viewMode。
export type ViewMode = 'auto' | 'mobile' | 'desktop'

const PHONE_MQ = '(max-width: 768px)'
const TABLET_MQ = '(max-width: 1024px)'
const MOBILE_UA = /Android|iPhone|iPad|iPod|Mobile|HarmonyOS|Windows Phone/i

const hasWindow = typeof window !== 'undefined'
const uaMobile = hasWindow && MOBILE_UA.test(navigator.userAgent)

const viewMode = ref<ViewMode>(readInitialMode())
const phone = ref(false)
const tablet = ref(false)
let listening = false

function readInitialMode(): ViewMode {
  if (!hasWindow) return 'auto'
  try {
    const q = new URLSearchParams(window.location.search).get('view')
    if (q === 'mobile' || q === 'desktop' || q === 'auto') {
      localStorage.setItem('viewMode', q)
      return q
    }
    const saved = localStorage.getItem('viewMode')
    if (saved === 'mobile' || saved === 'desktop') return saved
  } catch { /* localStorage 不可用时按自动处理 */ }
  return 'auto'
}

function listen(mq: string, target: { value: boolean }) {
  const mql = window.matchMedia(mq)
  target.value = mql.matches
  const handler = (e: MediaQueryListEvent) => { target.value = e.matches }
  if (typeof mql.addEventListener === 'function') mql.addEventListener('change', handler)
  else mql.addListener(handler)
}

function ensureListening() {
  if (listening || !hasWindow) return
  listening = true
  listen(PHONE_MQ, phone)
  listen(TABLET_MQ, tablet)
}

const isMobile = computed(() => {
  if (viewMode.value === 'mobile') return true
  if (viewMode.value === 'desktop') return false
  return phone.value || (uaMobile && tablet.value)
})

function setViewMode(mode: ViewMode) {
  viewMode.value = mode
  try { localStorage.setItem('viewMode', mode) } catch { /* ignore */ }
}

export function useDevice() {
  ensureListening()
  return { isMobile, viewMode, setViewMode, uaMobile }
}
