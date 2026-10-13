import type { MetricsEvidence } from '@/types'
import { metric, percent } from './factorResult'

const REASONS: Record<string, string> = {
  NOT_ENOUGH_EQUITY_OBSERVATIONS: '净值观测不足', MISSING_EQUITY_OBSERVATIONS: '净值观测缺失',
  NONFINITE_EQUITY_OBSERVATIONS: '净值含非有限数', NOT_ENOUGH_RETURN_OBSERVATIONS: '收益区间样本不足',
  ZERO_RETURN_VOLATILITY: '收益波动为零，比率无定义', NO_DRAWDOWN: '未发生回撤，比率无定义',
  NO_CLOSED_TRADES: '没有已平仓交易', BENCHMARK_UNAVAILABLE: '基准不可用',
  MISSING_BENCHMARK_ENDPOINT: '基准缺少相同起止日', INTERIOR_BENCHMARK_GAPS: '基准内部存在缺口',
  UNIQUE_DATE_INDEX_REQUIRED: '日期索引不唯一或不可用', NOT_PROVIDED: '未提供',
  NONFINITE_RESULT: '计算结果非有限数', INVALID_EQUITY_VALUES: '净值存在无效值',
  DUPLICATE_EQUITY_INDEX: '净值日期重复',
}
export const evidenceReason = (reason: string | null | undefined) => reason ? REASONS[reason] || reason : ''
export const evidenceStatus = (status: string | undefined) => status === 'VALID' ? '可用'
  : status === 'FAILED' ? '计算失败' : status === 'INSUFFICIENT_DATA' ? '样本不足' : '未提供状态'

export function evidenceLines(evidence: MetricsEvidence | null | undefined): string[] {
  if (!evidence) return ['未提供样本和计算状态，历史结果需重跑才能补齐证据。']
  const s = evidence.sample_info
  const b = evidence.benchmark_info
  return [
    `净值输入：${evidenceStatus(evidence.status)} · 有效观测 ${metric(s?.valid_equity_observations, 0)} / ${metric(s?.equity_observations, 0)} · 收益区间 ${metric(s?.return_observations, 0)} / ${metric(s?.expected_return_observations, 0)}`,
    `样本范围 ${s?.start || '—'} 至 ${s?.end || '—'} · 年化每年 ${metric(s?.periods_per_year, 0)} 期；净值可用不代表每个比率都有定义。`,
    `基准：${evidenceStatus(b?.status)} · ${b?.alignment === 'EXACT_EQUITY_ENDPOINTS' ? '相同净值起止日比较' : '对齐口径未提供'} · 覆盖 ${metric(b?.observations, 0)} / ${metric(b?.expected_observations, 0)}（${percent(b?.coverage_ratio, 1, false)}）${b?.reason ? ` · ${evidenceReason(b.reason)}` : ''}`,
  ]
}
