import { ref } from 'vue'
import { submitResearchJob, getResearchJob, type ResearchJobKind } from '@/api/strategy'

/**
 * 异步研究任务：提交 → 每 2s 轮询 → 返回结果。
 * run() 抛错 = 提交失败/任务失败/超时（调用方 toast）；业务性错误
 * （如检验覆盖不足 {"error": ...}）不算失败，原样返回由调用方按旧逻辑展示。
 * elapsed 供按钮显示「计算中 Ns」——后台跑多久页面都不再吊死。
 */
export function useResearchJob() {
  const running = ref(false)
  const elapsed = ref(0)
  let timer: number | null = null

  async function run<T>(kind: ResearchJobKind, body: unknown, timeoutMs = 15 * 60_000): Promise<T> {
    if (running.value) throw new Error('已有任务在计算中，请稍候')
    running.value = true
    elapsed.value = 0
    const started = Date.now()
    timer = window.setInterval(() => { elapsed.value = Math.round((Date.now() - started) / 1000) }, 1000)
    try {
      const { job_id } = await submitResearchJob(kind, body)
      for (;;) {
        await new Promise(r => setTimeout(r, 2000))
        const job = await getResearchJob(job_id)
        if (job.status === 'DONE') return job.result as T
        if (job.status === 'FAILED') throw new Error(job.error || '计算失败')
        if (Date.now() - started > timeoutMs) throw new Error('计算超时——请缩小时间区间或股票数后重试')
      }
    } finally {
      running.value = false
      if (timer) { clearInterval(timer); timer = null }
    }
  }

  return { running, elapsed, run }
}
