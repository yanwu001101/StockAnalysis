import { onBeforeUnmount, ref } from 'vue'
import { listRuns, type JobRun } from '@/api/tasks'

/** Poll only while a server-reported run is active; never trigger a job here. */
export function useTaskRuns() {
  const runs = ref<JobRun[]>([])
  const loading = ref(false)
  const error = ref('')
  let disposed = false
  let refreshAgain = false
  let timer: ReturnType<typeof setTimeout> | undefined
  async function refresh() {
    if (disposed) return
    if (loading.value) { refreshAgain = true; return }
    if (timer) clearTimeout(timer)
    loading.value = true
    try { runs.value = (await listRuns()).items || []; error.value = '' }
    catch (e) { error.value = e instanceof Error ? e.message : '任务历史加载失败' }
    finally {
      loading.value = false
      if (!disposed && refreshAgain) { refreshAgain = false; timer = setTimeout(refresh, 0) }
      else if (!disposed && runs.value.some(run => run.status === 'running')) timer = setTimeout(refresh, 5000)
    }
  }
  onBeforeUnmount(() => { disposed = true; if (timer) clearTimeout(timer) })
  return { runs, loading, error, refresh }
}
