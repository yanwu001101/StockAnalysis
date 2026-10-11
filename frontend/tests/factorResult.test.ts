import { describe, expect, it } from 'vitest'
import { metric, factorStatus } from '@/utils/factorResult'

describe('financial display contract', () => {
  it('distinguishes zero from missing and invalid numbers', () => {
    expect(metric(0)).toBe('0.0000')
    expect(metric(null)).toBe('—')
    expect(metric(NaN)).toBe('—')
    expect(metric(Infinity)).toBe('—')
  })
  it('uses the server status for both batch and detail', () => {
    expect(factorStatus({ status: 'INSUFFICIENT_DATA' }).text).toBe('样本不足')
    expect(factorStatus({ status: 'VALID' }).cls).toBe('st-good')
    expect(factorStatus({ error_kind: 'compute' }).text).toBe('计算失败')
  })
})
