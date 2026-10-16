import { describe, expect, it } from 'vitest'
import {
  TRANSLATORS,
  colorClassFor,
  signalFor,
  translateMetrics,
} from '@/utils/mappers/quant-vm'
import type { MetricStatusMap, QuantMetricsDTO } from '@/types/quant'

const metrics: QuantMetricsDTO = {
  sharpeRatio: 1.5,
  maxDrawdown: -0.12,
  winRate: 0.5,
  totalReturn: 0.1,
  alpha: 0.02,
  beta: 1.0,
}

const allValid: MetricStatusMap = {
  sharpeRatio: 'VALID',
  maxDrawdown: 'VALID',
  winRate: 'VALID',
  totalReturn: 'VALID',
  alpha: 'VALID',
  beta: 'VALID',
}

describe('translateMetrics', () => {
  it('registry covers the six contract metrics', () => {
    expect(TRANSLATORS.map((t) => t.key).sort()).toEqual(
      ['alpha', 'beta', 'maxDrawdown', 'sharpeRatio', 'totalReturn', 'winRate'].sort(),
    )
  })

  it('turns max_drawdown -0.15 into the per-10k worst case', () => {
    const verdict = translateMetrics({ ...metrics, maxDrawdown: -0.15 }, allValid)
    expect(verdict.reasons.some((r) => r.includes('最多可能亏 1500 元'))).toBe(true)
  })

  it('never emits a fabricated score for an uncomputable metric', () => {
    const verdict = translateMetrics(
      { ...metrics, sharpeRatio: 0 },
      { ...allValid, sharpeRatio: 'INSUFFICIENT_DATA' },
    )
    const sharpeReason = verdict.reasons.find((r) => r.includes('夏普比率')) ?? ''
    expect(sharpeReason).toContain('无法计算')
    expect(sharpeReason).toContain('不计入评分')
  })

  it('bounded score for the worst possible metrics', () => {
    const verdict = translateMetrics(
      {
        sharpeRatio: -5,
        maxDrawdown: -0.9,
        winRate: 0,
        totalReturn: -0.9,
        alpha: -0.9,
        beta: 3,
      },
      allValid,
    )
    expect(verdict.score).toBe(0)
    expect(verdict.signal).toBe('SELL')
    expect(verdict.colorClass).toBe('text-red')
  })

  it('reaches BUY on strong metrics', () => {
    const verdict = translateMetrics(
      {
        sharpeRatio: 2.5,
        maxDrawdown: -0.05,
        winRate: 0.7,
        totalReturn: 0.5,
        alpha: 0.2,
        beta: 1.0,
      },
      allValid,
    )
    expect(verdict.score).toBeGreaterThanOrEqual(65)
    expect(verdict.signal).toBe('BUY')
    expect(verdict.colorClass).toBe('text-green')
  })
})

describe('thresholds', () => {
  it('signal boundaries', () => {
    expect(signalFor(65)).toBe('BUY')
    expect(signalFor(64)).toBe('HOLD')
    expect(signalFor(36)).toBe('HOLD')
    expect(signalFor(35)).toBe('SELL')
  })

  it('colour boundaries', () => {
    expect(colorClassFor(80)).toBe('text-green')
    expect(colorClassFor(50)).toBe('text-yellow')
    expect(colorClassFor(10)).toBe('text-red')
  })
})
