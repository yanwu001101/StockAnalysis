export type TagType = 'success' | 'warning' | 'danger' | 'info'
export function jobStatus(status: string | null | undefined): { label: string; type: TagType } {
  switch (status) {
    case 'running': return { label: '运行中', type: 'warning' }
    case 'success': return { label: '成功', type: 'success' }
    case 'partial': return { label: '部分成功', type: 'warning' }
    case 'failed': return { label: '失败', type: 'danger' }
    case 'skipped': return { label: '已跳过', type: 'info' }
    default: return { label: '结果未确认', type: 'info' }
  }
}
export function healthStatus(status: string | null | undefined): { label: string; type: TagType } {
  switch (status) {
    case 'COVERED': return { label: '参考日已覆盖', type: 'success' }
    case 'PARTIAL': return { label: '部分覆盖', type: 'warning' }
    case 'DELAYED': return { label: '落后参考日', type: 'warning' }
    case 'NO_DATA': return { label: '无数据', type: 'warning' }
    case 'FAILED': return { label: '检查失败', type: 'danger' }
    case 'EVENT_DRIVEN': return { label: '事件驱动', type: 'info' }
    default: return { label: '未确认', type: 'info' }
  }
}
export function connectedStatus(value: unknown): { label: string; type: TagType } {
  return value === true ? { label: '正常', type: 'success' }
    : value === false ? { label: '断开', type: 'danger' } : { label: '未确认', type: 'info' }
}
export function numberText(value: unknown, digits = 0, suffix = '') {
  return typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(digits)}${suffix}` : '—'
}
export function uptimeText(ms: unknown) {
  if (typeof ms !== 'number' || !Number.isFinite(ms) || ms < 0) return '—'
  return `${Math.floor(ms / 3600000)}h ${Math.floor(ms % 3600000 / 60000)}m`
}
