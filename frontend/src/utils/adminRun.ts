import type { WarmupRun } from '@/api/admin'

export function runStatusLabel(status: string): string {
  return ({ running: '运行中', success: '成功', partial: '部分完成', failed: '失败',
    skipped: '已跳过', unknown: '结果未验证' } as Record<string, string>)[status] || '未知状态'
}

export function runMessage(run: WarmupRun): { type: 'success' | 'warning' | 'error' | 'info'; message: string } {
  const type = run.status === 'success' ? 'success' : run.status === 'failed' ? 'error'
    : run.status === 'skipped' ? 'info' : 'warning'
  const reason = run.reason === 'weekend' ? '周末跳过' : run.reason === 'legacy_unverified'
    ? '旧任务未提供可验证结果' : run.reason
  return { type, message: `${run.job} · ${runStatusLabel(run.status)}${run.error || reason ? `：${run.error || reason}` : ''}` }
}

export function connectionLabel(value?: boolean | null): string {
  return value === true ? '已连接' : value === false ? '断开' : '未确认'
}
