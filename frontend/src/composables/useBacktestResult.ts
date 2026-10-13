import { ref, shallowRef } from 'vue'
import type { BacktestResult } from '@/types'
import { BacktestResultError, parseBacktestResult } from '@/utils/backtestResult'

type RequestSnapshot = Record<string, any>
const snapshot = (request: RequestSnapshot) => JSON.parse(JSON.stringify(request)) as RequestSnapshot

/** One result and its submitted parameters are an indivisible, saveable snapshot. */
export function useBacktestResult() {
  const result = shallowRef<BacktestResult | null>(null)
  const lastRequest = shallowRef<RequestSnapshot | null>(null)
  const loading = ref(false)
  const error = ref('')
  const errorTitle = ref('计算失败')

  async function resolve(load: () => Promise<{ result: unknown; request: RequestSnapshot }>) {
    if (loading.value) throw new Error('已有回测任务在处理中')
    loading.value = true
    result.value = null
    lastRequest.value = null
    error.value = ''
    try {
      const next = await load()
      const parsed = parseBacktestResult(next.result)
      lastRequest.value = snapshot(next.request)
      result.value = parsed
      return parsed
    } catch (e) {
      error.value = e instanceof Error ? e.message : '回测失败，请稍后重试'
      errorTitle.value = e instanceof BacktestResultError && e.status === 'INSUFFICIENT_DATA'
        ? '样本不足' : '计算失败'
      throw e
    } finally {
      loading.value = false
    }
  }

  function run(request: RequestSnapshot, load: (request: RequestSnapshot) => Promise<unknown>) {
    const submitted = snapshot(request)
    return resolve(async () => ({ result: await load(snapshot(submitted)), request: submitted }))
  }

  return { result, lastRequest, loading, error, errorTitle, run, restore: resolve }
}
