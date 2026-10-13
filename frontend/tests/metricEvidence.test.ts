import { describe, expect, it } from 'vitest'
import { evidenceLines } from '@/utils/metricEvidence'

describe('metrics metadata presentation', () => {
  it('shows observation counts, annualization and benchmark interior gaps without recomputing returns', () => {
    const text = evidenceLines({ status: 'VALID',
      sample_info: { equity_observations: 11, valid_equity_observations: 11, return_observations: 10,
        expected_return_observations: 10, start: '2026-01-01', end: '2026-01-15', periods_per_year: 252 },
      benchmark_info: { status: 'VALID', observations: 9, expected_observations: 11, coverage_ratio: 9 / 11,
        reason: 'INTERIOR_BENCHMARK_GAPS', alignment: 'EXACT_EQUITY_ENDPOINTS' },
    }).join('\n')
    expect(text).toContain('有效观测 11 / 11')
    expect(text).toContain('年化每年 252 期')
    expect(text).toContain('相同净值起止日比较')
    expect(text).toContain('81.8%')
    expect(text).toContain('基准内部存在缺口')
  })
  it('does not call unavailable sample and benchmark data zero', () => {
    const text = evidenceLines({ status: 'INSUFFICIENT_DATA', benchmark_info: { status: 'INSUFFICIENT_DATA', reason: 'MISSING_BENCHMARK_ENDPOINT' } }).join('\n')
    expect(text).toContain('样本不足')
    expect(text).toContain('有效观测 — / —')
    expect(text).toContain('基准缺少相同起止日')
    expect(text).not.toContain('0.0%')
  })
})
