import { describe, expect, it } from 'vitest'
import {
  dayContext,
  displaySymbol,
  equitySeries,
  filterPaletteItems,
  nearestDay,
  tradeRows,
  type PaletteItem,
} from '@/utils/selectors'
import type { QuantVerdictPayload } from '@/types/quant'

const verdict: QuantVerdictPayload = {
  rawMetrics: {
    sharpeRatio: 1.5,
    maxDrawdown: -0.2,
    winRate: 0.6,
    totalReturn: 0.3,
    alpha: 0.1,
    beta: 1,
  },
  humanVerdict: {
    score: 72,
    signal: 'BUY',
    reasons: ['好'],
    colorClass: 'text-green',
  },
  chartMarkers: [
    { date: '2025-03-03', price: 10.5, action: 'BUY', reason: 'MACD 金叉' },
    { date: '2025-03-05', price: 11.0, action: 'SELL', reason: 'MACD 死叉' },
  ],
  metricStatus: {
    sharpeRatio: 'VALID',
    maxDrawdown: 'VALID',
    winRate: 'VALID',
    totalReturn: 'VALID',
    alpha: 'VALID',
    beta: 'VALID',
  },
  symbol: '600519',
  // [open, close, low, high]
  candles: [
    [10, 10.5, 9.8, 10.6],
    [10.5, 10.2, 10.0, 10.7],
    [10.2, 11.0, 10.1, 11.2],
  ],
  dates: ['2025-03-03', '2025-03-04', '2025-03-05'],
  equityCurve: [1_000_000, 1_050_000, 980_000],
  trades: [
    {
      date: '2025-03-03',
      side: 'BUY',
      shares: 1000,
      price: 10.5,
      commission: 31.5,
      stampTax: 0,
      transferFee: 2.1,
      pnl: null,
    },
    {
      date: '2025-03-05',
      side: 'SELL',
      shares: 1000,
      price: 11.0,
      commission: 33,
      stampTax: 11,
      transferFee: 2.2,
      pnl: 453.7,
    },
  ],
  debate: [
    { round: 1, side: 'BULL', argument: 'MACD 金叉', conviction: 0.55 },
    { round: 1, side: 'BEAR', argument: 'RSI 偏高', conviction: 0.4 },
  ],
  warnings: [],
}

describe('dayContext', () => {
  it('locates the exact day with OHLC and marker', () => {
    const ctx = dayContext(verdict, '2025-03-03')
    expect(ctx).not.toBeNull()
    expect(ctx?.index).toBe(0)
    expect(ctx?.open).toBe(10)
    expect(ctx?.close).toBe(10.5)
    expect(ctx?.marker?.action).toBe('BUY')
    expect(ctx?.marker?.reason).toBe('MACD 金叉')
  })

  it('computes changePct from open', () => {
    const ctx = dayContext(verdict, '2025-03-04')
    expect(ctx?.changePct).toBeCloseTo(10.2 / 10.5 - 1, 10)
    expect(ctx?.marker).toBeNull()
  })

  it('returns null for a date not on the axis (never a shifted match)', () => {
    expect(dayContext(verdict, '2025-03-06')).toBeNull()
    expect(dayContext(verdict, '')).toBeNull()
    expect(dayContext(null, '2025-03-03')).toBeNull()
  })
})

describe('nearestDay', () => {
  it('snaps to the previous tradeable day', () => {
    expect(nearestDay(verdict, '2025-03-04')).toBe('2025-03-04')
    expect(nearestDay(verdict, '2025-03-04T12:00:00')).toBe('2025-03-04')
    expect(nearestDay(verdict, '2025-03-02')).toBe('2025-03-03')
    expect(nearestDay(null, '2025-03-02')).toBeNull()
  })
})

describe('equitySeries', () => {
  it('aligns values with dates and finds the max drawdown', () => {
    const series = equitySeries(verdict)
    expect(series.dates).toEqual(['2025-03-03', '2025-03-04', '2025-03-05'])
    expect(series.values).toEqual([1_000_000, 1_050_000, 980_000])
    // 1050000 -> 980000
    expect(series.maxDrawdown).toBeCloseTo(980_000 / 1_050_000 - 1, 10)
  })

  it('empty payload -> empty series', () => {
    expect(equitySeries(null)).toEqual({ dates: [], values: [], maxDrawdown: null })
  })
})

describe('tradeRows', () => {
  it('flattens trades, sums fees and computes round-trip pnl pct', () => {
    const rows = tradeRows(verdict)
    expect(rows).toHaveLength(2)
    expect(rows[0].side).toBe('BUY')
    expect(rows[0].fees).toBeCloseTo(31.5 + 2.1, 10)
    expect(rows[0].pnlPct).toBeNull()
    expect(rows[1].side).toBe('SELL')
    expect(rows[1].fees).toBeCloseTo(33 + 11 + 2.2, 10)
    expect(rows[1].pnl).toBe(453.7)
    expect(rows[1].pnlPct).toBeCloseTo(453.7 / (10.5 * 1000), 10)
  })
})

describe('filterPaletteItems', () => {
  const items: PaletteItem[] = [
    { id: 'nav-1', label: '驾驶舱', hint: '宏观数据', group: 'navigation', target: '/command-center' },
    { id: 'nav-2', label: '回测实验室', hint: '策略配置', group: 'navigation', target: '/backtest' },
    { id: 'watch-1', label: '600519', hint: '自选', group: 'watchlist', target: '/analysis/600519' },
    { id: 'action-1', label: '分析「000001」', hint: '提交分析', group: 'action', target: 'analyze:000001' },
  ]

  it('empty query returns everything, navigation first', () => {
    const result = filterPaletteItems('', items)
    expect(result[0].group).toBe('navigation')
    expect(result).toHaveLength(4)
  })

  it('matches by subsequence', () => {
    // "舱" 是 "驾驶舱" 的子序列；"519" 是代码的子序列
    expect(filterPaletteItems('舱', items).map((item) => item.id)).toEqual(['nav-1'])
    expect(filterPaletteItems('59', items).map((item) => item.id)).toContain('watch-1')
  })

  it('matches watchlist symbols', () => {
    const result = filterPaletteItems('519', items)
    expect(result.map((item) => item.id)).toContain('watch-1')
  })

  it('no match -> empty', () => {
    expect(filterPaletteItems('zzzz', items)).toHaveLength(0)
  })
})

describe('displaySymbol', () => {
  it('adds the exchange prefix', () => {
    expect(displaySymbol('600519')).toBe('sh600519')
    expect(displaySymbol('000001')).toBe('sz000001')
    expect(displaySymbol('830799')).toBe('bj830799')
    expect(displaySymbol('sh600519')).toBe('sh600519')
  })
})
