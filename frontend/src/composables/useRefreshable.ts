import { onMounted, onBeforeUnmount, onActivated, onDeactivated } from 'vue'
import { useRefreshStore } from '@/stores/refresh'

interface UseRefreshableOpts {
  immediate?: boolean    // 默认 true: 首次挂载时自动跑一次
  autoRefresh?: boolean  // 默认 true: 按 settings.refreshInterval 周期刷新
}

export function useRefreshable(
  label: string,
  fn: () => Promise<any> | any,
  opts: UseRefreshableOpts = {}
) {
  const store = useRefreshStore()
  const immediate = opts.immediate !== false
  const autoRefresh = opts.autoRefresh !== false
  let firstMountDone = false

  function attach() {
    store.registerReloader(label, fn, { autoRefresh })
  }
  function detach() {
    store.unregisterReloader(label)
  }

  onMounted(async () => {
    attach()
    if (immediate) await store.invokeReloader(true)
    firstMountDone = true
  })

  // keep-alive 切回:onMounted 不会再触发,这里负责重新注册 reloader
  onActivated(() => {
    if (!firstMountDone) return  // 首次挂载已由 onMounted 处理,避免重复
    attach()
    // 数据展示页(autoRefresh: true)切回时立刻刷一次新数据
    // 用户输入页(autoRefresh: false)保留之前结果,不触发
    if (autoRefresh) store.invokeReloader(true)
  })

  onBeforeUnmount(detach)
  onDeactivated(detach)
}

