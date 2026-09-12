import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { addToWatchlist, removeFromWatchlist } from '@/api/user'
import { padCode } from '@/utils/score'

// 自选股成员判断与增删，详情页按钮和自选页共用同一份逻辑。
export function useWatchlist() {
  const userStore = useUserStore()
  const groups = computed(() => userStore.watchlists || [])

  function groupOf(code: string | number) {
    const c = padCode(code)
    return groups.value.find(g => (g.stocks || []).some((s: any) => padCode(s.code) === c))
  }

  function has(code: string | number) {
    return !!groupOf(code)
  }

  async function ensureLoaded() {
    if (userStore.isLoggedIn && !groups.value.length) {
      try { await userStore.fetchWatchlists() } catch { /* 网络失败不打断页面；拦截器已提示 */ }
    }
  }

  async function add(code: string | number, groupId?: number) {
    const gid = groupId ?? groups.value[0]?.id ?? 0
    await addToWatchlist(gid, padCode(code))
    ElMessage.success('已加入自选股')
    await userStore.fetchWatchlists()
  }

  async function remove(code: string | number, groupId?: number) {
    const gid = groupId ?? groupOf(code)?.id ?? 0
    await removeFromWatchlist(gid, padCode(code))
    ElMessage.success('已从自选股移除')
    await userStore.fetchWatchlists()
  }

  async function toggle(code: string | number) {
    if (has(code)) await remove(code)
    else await add(code)
  }

  return { groups, groupOf, has, add, remove, toggle, ensureLoaded }
}
