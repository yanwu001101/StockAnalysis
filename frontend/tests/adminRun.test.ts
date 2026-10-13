import { describe, expect, it } from 'vitest'
import { connectionLabel, runMessage, runStatusLabel } from '../src/utils/adminRun'
import type { WarmupRun } from '../src/api/admin'

describe('maintenance outcome presentation', () => {
  it.each([
    ['success', 'success', '成功'], ['failed', 'error', '失败'],
    ['partial', 'warning', '部分完成'], ['skipped', 'info', '已跳过'],
    ['unknown', 'warning', '结果未验证'],
  ] as const)('keeps %s distinct', (status, type, label) => {
    const run: WarmupRun = { id: 'x', job: 'postmarket', started_at: '', status }
    expect(runMessage(run).type).toBe(type)
    expect(runStatusLabel(status)).toBe(label)
  })
  it('does not present unqueried connections as disconnected', () => {
    expect(connectionLabel(null)).toBe('未确认')
    expect(connectionLabel(undefined)).toBe('未确认')
    expect(connectionLabel(false)).toBe('断开')
    expect(connectionLabel(true)).toBe('已连接')
  })
})
