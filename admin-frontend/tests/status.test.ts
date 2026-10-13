import { describe, expect, it } from 'vitest'
import { connectedStatus, healthStatus, jobStatus, numberText, uptimeText } from '@/utils/status'
describe('admin evidence status', () => {
  it('does not classify partial, skipped or unknown outcomes as successful', () => {
    expect(jobStatus('success').type).toBe('success')
    expect(jobStatus('partial').label).toBe('部分成功')
    expect(jobStatus('failed').type).toBe('danger')
    for (const state of ['partial', 'skipped', 'unknown', 'new-server-state']) expect(jobStatus(state).type).not.toBe('success')
  })
  it('distinguishes missing connection evidence from a disconnected service', () => {
    expect(connectedStatus(undefined).label).toBe('未确认')
    expect(connectedStatus(false).label).toBe('断开')
    expect(connectedStatus(true).label).toBe('正常')
  })
  it('names reference coverage without promising live-market freshness', () => {
    expect(healthStatus('COVERED').label).toBe('参考日已覆盖')
    expect(healthStatus('EVENT_DRIVEN').label).toBe('事件驱动')
    expect(healthStatus('FAILED').label).toBe('检查失败')
    expect(healthStatus(undefined).label).toBe('未确认')
  })
  it('shows true zero but never turns missing or nonfinite coverage into zero', () => {
    expect(numberText(0, 1, '%')).toBe('0.0%')
    for (const value of [null, undefined, NaN, Infinity]) expect(numberText(value, 1, '%')).toBe('—')
    expect(uptimeText(undefined)).toBe('—')
    expect(uptimeText(0)).toBe('0h 0m')
  })
})
