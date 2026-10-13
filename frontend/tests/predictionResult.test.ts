import { describe, expect, it } from 'vitest'
import type { PredictionResult } from '@/types'
import { predictionPresentation } from '@/utils/predictionResult'

const fixture = (overrides: Partial<PredictionResult> = {}): PredictionResult => ({
  code: '000001', name: '测试', price: 10, probabilityUp: 89.5, probabilityDown: 10.5,
  confidence: 72, signal: 'bullish', signalLabel: '偏多', compositeDirection: 0.5,
  dimensions: [], keyDrivers: [], riskWarnings: [], timeHorizon: '3-5 个交易日', ...overrides,
})

describe('prediction score versus calibrated history', () => {
  it('shows uncalibrated scores on a 100-point scale, never as a probability', () => {
    const p = predictionPresentation(fixture())
    expect(p.calibrated).toBe(false)
    expect(p.title).toBe('趋势评分 · 未校准')
    expect(p.scoreText).toBe('89.5 / 100')
    expect(p.confidenceText).toBe('72.0 / 100')
    expect(p.upText).not.toContain('%')
    expect(p.averageReturn).toBe('—')
  })

  it('shows a sample-insufficient status while retaining the reported sample count', () => {
    const p = predictionPresentation(fixture({ calibration: { insufficient: true, n: 12 } }))
    expect(p.calibrationMessage).toContain('校准样本不足')
    expect(p.sampleText).toBe('12')
    expect(p.calibrated).toBe(false)
  })

  it('rejects malformed calibration rather than fabricating a zero win rate', () => {
    for (const calibration of [
      { insufficient: false, n: 100 }, { insufficient: false, n: 0, win_rate: 0.8 },
      { insufficient: false, n: 100, win_rate: NaN }, { insufficient: false, n: 100, win_rate: 1.01 },
    ]) {
      const p = predictionPresentation(fixture({ calibration }))
      expect(p.calibrated).toBe(false)
      expect(p.scoreText).toBe('—')
      expect(p.upText).toBe('—')
    }
  })

  it('preserves real zero calibration observations and leaves missing average returns blank', () => {
    const p = predictionPresentation(fixture({ calibration: { insufficient: false, n: 100, win_rate: 0, avg_return: null } }))
    expect(p.calibrated).toBe(true)
    expect(p.upText).toBe('0.0%')
    expect(p.averageReturn).toBe('—')
    const zero = predictionPresentation(fixture({ calibration: { insufficient: false, n: 100, win_rate: 0, avg_return: 0 } }))
    expect(zero.averageReturn).toBe('0.00%')
  })

  it('suppresses backend 50/50 fallback scores when the prediction lacks input data', () => {
    const p = predictionPresentation(fixture({ signalLabel: '数据不足', probabilityUp: 50, probabilityDown: 50, confidence: 0 }))
    expect(p.title).toContain('数据不足')
    expect(p.scoreText).toBe('—')
    expect(p.confidenceText).toBe('—')
  })

  it('preserves explicit missing and genuine zero scores without fallback coercion', () => {
    expect(predictionPresentation(fixture({ rawScore100: null })).scoreText).toBe('—')
    expect(predictionPresentation(fixture({ rawScore100: 0, confidence: 0 })).scoreText).toBe('0.0 / 100')
    expect(predictionPresentation(fixture({ confidence: Infinity })).confidenceText).toBe('—')
    expect(predictionPresentation(fixture({ status: 'FAILED' })).scoreText).toBe('—')
  })
})
