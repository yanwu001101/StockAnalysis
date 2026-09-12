import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

// 页内 tab 与 ?tab= 双向同步：
//   - 旧路由 redirect 带来的 ?tab=xxx 能直接落到对应 tab；
//   - keep-alive 切回本页且地址上没有 tab 时，用本地记住的 tab 补回地址栏；
//   - 默认 tab 不写进地址，保持 URL 干净。
export function useRouteTab<T extends string>(defaultTab: T, allowed: readonly T[], key = 'tab') {
  const route = useRoute()
  const router = useRouter()
  const pageName = route.name

  function readFromRoute(): T | null {
    const raw = route.query[key]
    const v = Array.isArray(raw) ? raw[0] : raw
    return typeof v === 'string' && (allowed as readonly string[]).includes(v) ? (v as T) : null
  }

  const local = ref(readFromRoute() ?? defaultTab) as { value: T }

  function writeToRoute(v: T) {
    const query = { ...route.query }
    if (v === defaultTab) delete query[key]
    else query[key] = v
    router.replace({ query })
  }

  watch(
    () => [route.name, route.query[key]] as const,
    ([name]) => {
      if (name !== pageName) return
      const v = readFromRoute()
      if (v) local.value = v
      else if (local.value !== defaultTab) writeToRoute(local.value)
    },
  )

  return computed<T>({
    get: () => local.value,
    set: (v) => {
      if (v === local.value) return
      local.value = v
      if (route.name === pageName) writeToRoute(v)
    },
  })
}
