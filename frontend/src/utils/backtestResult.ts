import type { BacktestResult } from '@/types'
import type { StatItem } from '@/types/ui'
import { isFiniteNumber, metric, percent } from './factorResult'
import { evidenceReason, evidenceStatus } from './metricEvidence'
export { isFiniteNumber, percent } from './factorResult'

const METRIC_KEYS = {
  totalReturn: 'total_return', annualizedReturn: 'annualized_return', maxDrawdown: 'max_drawdown',
  sharpeRatio: 'sharpe_ratio', winRate: 'win_rate', tradeCount: 'trade_count', benchmarkReturn: 'benchmark_return',
  excessReturn: 'excess_return', turnoverRate: 'turnover_rate', totalCosts: 'total_costs',
} as const

export class BacktestResultError extends Error {
  constructor(message: string, readonly status: 'FAILED' | 'INSUFFICIENT_DATA' = 'FAILED') {
    super(message)
    this.name = 'BacktestResultError'
  }
}

/** Transport DONE is not evidence of a successful calculation. Keep missing metrics null. */
export function parseBacktestResult(payload: unknown): BacktestResult {
  if (!payload || typeof payload !== 'object') throw new BacktestResultError('回测未返回有效结果')
  const r = payload as Record<string, any>
  if (r.error || r.status === 'FAILED' || r.status === 'INSUFFICIENT_DATA') {
    const insufficient = r.status === 'INSUFFICIENT_DATA' || r.error_kind === 'coverage'
    const message = typeof r.error === 'string' ? r.error : r.error?.message
    throw new BacktestResultError(message || (insufficient ? '有效样本不足' : '回测计算失败'),
      insufficient ? 'INSUFFICIENT_DATA' : 'FAILED')
  }
  if (!Array.isArray(r.equityCurve) || !r.equityCurve.length) {
    throw new BacktestResultError('回测未返回净值序列，不能展示为有效结果', 'INSUFFICIENT_DATA')
  }
  const result = { ...r } as BacktestResult
  for (const key of Object.keys(METRIC_KEYS) as (keyof typeof METRIC_KEYS)[]) {
    const status = r.metrics?.metric_status?.[METRIC_KEYS[key]]
    result[key] = (!status || status === 'VALID') && isFiniteNumber(r[key]) ? r[key] : null
  }
  result.equityCurve = r.equityCurve.map((point: any) => ({
    date: String(point?.date ?? ''), value: isFiniteNumber(point?.value) ? point.value : null,
  }))
  if (!result.equityCurve.some(point => point.date && point.value != null)) {
    throw new BacktestResultError('净值序列缺少有效观测，不能展示为有效结果', 'INSUFFICIENT_DATA')
  }
  if (Array.isArray(r.benchmarkCurve)) result.benchmarkCurve = r.benchmarkCurve.map((point: any) => ({
    date: String(point?.date ?? ''), value: isFiniteNumber(point?.value) ? point.value : null,
  }))
  result.trades = Array.isArray(r.trades) ? r.trades : []
  return result
}

export function backtestMetricItems(r: BacktestResult): StatItem[] {
  const color = (value: number | null | undefined) =>
    !isFiniteNumber(value) || value === 0 ? '' : value > 0 ? 'price-up' : 'price-down'
  const basis = r.metrics?.win_rate_basis || r.win_rate_basis
  const sampleSize = r.metrics?.win_rate_sample_size ?? r.win_rate_sample_size
  const items: StatItem[] = [
    { label: '总收益率', value: percent(r.totalReturn), cls: color(r.totalReturn) },
    { label: '年化收益率', value: percent(r.annualizedReturn), cls: color(r.annualizedReturn) },
    { label: '最大回撤', value: isFiniteNumber(r.maxDrawdown) ? percent(-Math.abs(r.maxDrawdown)) : '—', cls: isFiniteNumber(r.maxDrawdown) && r.maxDrawdown !== 0 ? 'price-down' : '' },
    { label: '夏普比率', value: metric(r.sharpeRatio, 2) },
    { label: basis === 'EQUITY_UP_PERIODS' ? '净值上涨期占比' : '胜率', value: percent(r.winRate, 1, false), foot: `${basis === 'CLOSED_TRADES'
      ? '盈利平仓笔数 / 已平仓笔数；未平仓不计入'
      : basis === 'EQUITY_UP_PERIODS' ? '净值上涨期数 / 有效收益期数；不是交易胜率'
      : '服务端未提供分母口径，不作交易胜率解释'} · n=${metric(sampleSize, 0)}` },
    { label: '交易次数', value: isFiniteNumber(r.tradeCount) ? r.tradeCount : '—' },
    { label: '基准 (沪深300)', value: percent(r.benchmarkReturn), cls: color(r.benchmarkReturn) },
    { label: '超额收益', value: percent(r.excessReturn), cls: color(r.excessReturn) },
    { label: '年化换手率', value: percent(r.turnoverRate, 0, false) },
    { label: '交易成本合计', value: isFiniteNumber(r.totalCosts) ? `${(r.totalCosts / 10000).toFixed(2)} 万` : '—' },
  ]
  Object.values(METRIC_KEYS).forEach((key, index) => {
    const status = r.metrics?.metric_status?.[key]
    const reason = r.metrics?.metric_reasons?.[key]
    if (status && status !== 'VALID') {
      items[index].value = '—'; items[index].cls = ''
      items[index].foot = [items[index].foot, evidenceStatus(status), evidenceReason(reason)].filter(Boolean).join(' · ')
    }
  })
  return items
}
