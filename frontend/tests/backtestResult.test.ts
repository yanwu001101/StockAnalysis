import { describe, expect, it } from 'vitest'
import { backtestMetricItems, parseBacktestResult } from '@/utils/backtestResult'
import { useBacktestResult } from '@/composables/useBacktestResult'

const valid = () => ({
  totalReturn: 0, annualizedReturn: 0, maxDrawdown: 0, sharpeRatio: null, winRate: null, tradeCount: 0,
  equityCurve: [{ date: '2026-10-09', value: 1 }], trades: [],
})

describe('backtest response and presentation contract', () => {
  it('rejects business errors even when a job reports DONE', () => {
    expect(() => parseBacktestResult({ error: 'no price matrix' })).toThrow('no price matrix')
    expect(() => parseBacktestResult({ ...valid(), status: 'FAILED' })).toThrow('回测计算失败')
    expect(() => parseBacktestResult({ ...valid(), status: 'INSUFFICIENT_DATA' })).toThrow('有效样本不足')
    expect(() => parseBacktestResult({ ...valid(), equityCurve: [] })).toThrow('未返回净值序列')
  })

  it('keeps actual zero distinct from missing, NaN and Infinity', () => {
    const r = parseBacktestResult({ ...valid(), annualizedReturn: NaN, benchmarkReturn: Infinity })
    const rows = Object.fromEntries(backtestMetricItems(r).map(row => [row.label, row]))
    expect(rows['总收益率'].value).toBe('0.00%')
    expect(rows['最大回撤'].value).toBe('0.00%')
    expect(rows['交易次数'].value).toBe(0)
    expect(rows['总收益率'].cls).toBe('')
    for (const label of ['年化收益率', '夏普比率', '胜率', '基准 (沪深300)', '超额收益', '交易成本合计']) {
      expect(rows[label].value).toBe('—')
    }
    expect(r.benchmarkReturn).toBeNull()
  })

  it('normalizes both drawdown sign conventions without displaying a double negative', () => {
    for (const drawdown of [-0.125, 0.125]) {
      expect(backtestMetricItems(parseBacktestResult({ ...valid(), maxDrawdown: drawdown }))[2].value).toBe('-12.50%')
    }
  })

  it('does not claim all portfolio win rates are closed-trade statistics', () => {
    const generic = backtestMetricItems(parseBacktestResult(valid())).find(row => row.label === '胜率')
    expect(generic?.foot).toContain('未提供分母口径')
    const single = backtestMetricItems(parseBacktestResult({ ...valid(), win_rate_basis: 'CLOSED_TRADES' }))
      .find(row => row.label === '胜率')
    expect(single?.foot).toContain('未平仓不计入')
    const equity = backtestMetricItems(parseBacktestResult({ ...valid(), metrics: { win_rate_basis: 'EQUITY_UP_PERIODS', win_rate_sample_size: 252 } }))
    expect(equity[4].label).toBe('净值上涨期占比')
    expect(equity[4].foot).toContain('n=252')
  })

  it('trusts per-metric failure state over a conflicting numeric zero while retaining valid counts', () => {
    const r = parseBacktestResult({ ...valid(), sharpeRatio: 0, metrics: {
      status: 'VALID', metric_status: { sharpe_ratio: 'INSUFFICIENT_DATA', trade_count: 'VALID' },
      metric_reasons: { sharpe_ratio: 'ZERO_RETURN_VOLATILITY' },
    } })
    expect(r.sharpeRatio).toBeNull()
    const rows = backtestMetricItems(r)
    expect(rows[3].value).toBe('—')
    expect(rows[3].foot).toContain('波动为零')
    expect(rows[5].value).toBe(0)
  })

  it('keeps gaps in the curve and preserves genuine zero observations', () => {
    const r = parseBacktestResult({ ...valid(), equityCurve: [
      { date: '2026-10-08', value: null }, { date: '2026-10-09', value: 0 },
    ] })
    expect(r.equityCurve.map(point => point.value)).toEqual([null, 0])
    expect(() => parseBacktestResult({ ...valid(), equityCurve: [{ date: '2026-10-09', value: null }] })).toThrow('缺少有效观测')
  })

  it('preserves next-day execution evidence and unclosed positions without synthesizing a sale', () => {
    const r = parseBacktestResult({ ...valid(),
      execution_model: 'SIGNAL_CLOSE_NEXT_TRADING_DAY_OPEN',
      open_position: { code: '000001', shares: 100, market_value: 1000, valuation_date: '2026-10-09' },
      trades: [{ code: '000001', signal_date: '2026-10-08', date: '2026-10-09', side: 'buy', shares: 100, price: 10 }],
    })
    expect(r.execution_model).toBe('SIGNAL_CLOSE_NEXT_TRADING_DAY_OPEN')
    expect(r.open_position?.shares).toBe(100)
    expect(r.trades).toHaveLength(1)
    expect(r.trades[0].side).toBe('buy')
  })
})

describe('backtest result and submitted parameter lifecycle', () => {
  it('freezes submitted parameters before awaiting and does not pair them with later edits', async () => {
    const state = useBacktestResult()
    const request = { expression: 'rank(close)', topN: 5, strategyConfig: { quality: { weight: 20 } } }
    let finish!: (value: unknown) => void
    const task = state.run(request, () => new Promise(resolve => { finish = resolve }))
    request.topN = 20; request.strategyConfig.quality.weight = 99
    finish(valid()); await task
    expect(state.lastRequest.value).toEqual({ expression: 'rank(close)', topN: 5, strategyConfig: { quality: { weight: 20 } } })
    expect(state.loading.value).toBe(false)
  })

  it('clears old success immediately on rerun and leaves no saveable stale result on failure', async () => {
    const state = useBacktestResult()
    await state.run({ topN: 5 }, async () => valid())
    let fail!: (reason: Error) => void
    const task = state.run({ topN: 10 }, () => new Promise((_, reject) => { fail = reject }))
    expect(state.result.value).toBeNull()
    expect(state.lastRequest.value).toBeNull()
    fail(new Error('任务失败'))
    await expect(task).rejects.toThrow('任务失败')
    expect(state.error.value).toBe('任务失败')
    expect(state.result.value).toBeNull()
    expect(state.loading.value).toBe(false)
  })

  it('renders coverage failure distinctly and restores original saved parameters', async () => {
    const state = useBacktestResult()
    await expect(state.run({}, async () => ({ error: '覆盖不足', error_kind: 'coverage' }))).rejects.toThrow('覆盖不足')
    expect(state.errorTitle.value).toBe('样本不足')
    expect(state.result.value).toBeNull()
    await state.restore(async () => ({ result: valid(), request: { mode: 'factor', expression: 'rank(roe)' } }))
    expect(state.error.value).toBe('')
    expect(state.lastRequest.value?.expression).toBe('rank(roe)')
  })

  it('rejects concurrent runs without clearing the in-flight state', async () => {
    const state = useBacktestResult()
    let finish!: (value: unknown) => void
    const task = state.run({ topN: 5 }, () => new Promise(resolve => { finish = resolve }))
    await expect(state.run({ topN: 10 }, async () => valid())).rejects.toThrow('已有回测任务')
    expect(state.loading.value).toBe(true)
    finish(valid()); await task
    expect(state.lastRequest.value?.topN).toBe(5)
  })
})
