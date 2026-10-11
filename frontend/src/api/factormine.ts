import request from './request'

// ---- 因子挖掘（Factor Mining）：任务 / 候选 / 因子库 ----

export interface MineThresholds {
  min_ic: number
  min_icir: number
  min_t: number
  min_periods: number
  min_oos_ic: number
}

export interface MineConfig {
  market: string[]            // hs=沪深A股 cyb=创业板 kcb=科创板 bjs=北交所
  exclude_st?: boolean
  exclude_delisting?: boolean
  exclude_suspended?: boolean
  min_listed_days?: number
  start_date?: string
  end_date?: string
  horizons: number[]          // 预测周期（交易日）：1/3/5/10/20/60
  rebalance?: string          // 调仓周期：1d/3d/5d/10d/20d 或 weekly/monthly
  budget?: number             // 候选因子预算 100~10000
  method?: 'random' | 'grid' | 'beam'
  max_codes?: number
  layers?: number
  neutralize?: boolean
  keep_pct?: number
  max_missing_rate?: number
  dedup_threshold?: number
  full_validate_limit?: number
  oos_ratio?: number
  wf_top_k?: number
  wf_test_years?: number
  seed?: number
  thresholds?: Partial<MineThresholds>
}

export interface MineFunnel {
  generated: number
  tested: number
  pending: number
  unprocessed?: number
  invalid_expr: number
  leakage: number
  data_missing: number
  zero_variance: number
  quick_rejected: number
  quick_passed: number
  dedup_removed: number
  dedup_kept: number
  full_validated: number
  full_left?: number
  pass: number
  watch: number
  reject: number
  library: number
}

export interface MineJob {
  job_id: string
  status: 'QUEUED' | 'RUNNING' | 'PAUSED' | 'COMPLETED' | 'FAILED' | 'CANCELLED'
  phase: string | null
  note: string | null
  error: string | null
  data_version: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  elapsed_s?: number | null
  config: Partial<MineConfig>
  funnel: MineFunnel
}

export type FactorStatus = 'PENDING' | 'REJECTED' | 'QUICK_PASS' | 'VALIDATED'
export type FactorVerdict = 'PASS' | 'WATCH' | 'REJECT' | null

export interface MineFactorRow {
  id: string
  job_id: string
  seq: number
  expression: string
  normalized_expression: string
  category: string | null
  operator_list: string | null
  source_factors: string | null
  status: FactorStatus
  verdict: FactorVerdict
  reject_reason: string | null
  reject_detail: string | null
  missing_rate: number | null
  quick_rank_ic: number | null
  quick_icir: number | null
  rank_ic: number | null
  icir: number | null
  t_stat: number | null
  ic_positive_ratio: number | null
  oos_rank_ic: number | null
  pearson_ic: number | null
  stability: string | null
  cluster_id: number | null
  cluster_rep: number
  cluster_corr: number | null
  direction: string | null
  in_library: number
  data_version: string | null
  created_at: string
  updated_at: string
}

export interface IcSummary {
  mean: number
  std: number
  icir: number
  positive_ratio: number
  t_stat: number
  n: number
}

export interface YearlyStabilityRow {
  year: string
  ic_mean: number
  n: number
  positive_ratio: number
  dir_match: boolean
}

export interface CostRow { bps: number; net_spread_ann: number }

export interface WalkForwardRow {
  train: string
  test: string
  ic_mean: number
  icir: number
  n: number
  spread_ann: number | null
  top_max_drawdown: number | null
  stable: boolean
}

export interface MineFactorDetail extends MineFactorRow {
  stability_years?: YearlyStabilityRow[]
  ast?: Record<string, unknown> | null
  stats?: (FactorLabStats & Record<string, unknown>) | null
  cluster_peers?: Array<Record<string, unknown>>
}

/** factorlab.analyze_scores 的返回结构（复用同一检验引擎） */
export interface FactorLabStats {
  factor_name?: string
  expression?: string
  factor_id?: string
  start: string
  end: string
  rebalance: string
  layers: number
  codes_analyzed: number
  periods: number
  sample_info?: { periods: number; avg_cross_section: number; observations: number }
  ic_summary: IcSummary
  ic_series: { date: string; ic: number }[]
  ic_pearson_summary?: IcSummary
  ic_neutral_summary?: IcSummary | null
  rating?: {
    grade: string
    strength: number
    confidence: number
    direction: 'positive' | 'reverse' | 'neutral'
    status: string
    dimensions: Record<string, number>
    net_spread_ann: number
    cost_annualized?: number
    cost_per_turnover?: number
    robustness?: number
    tradability?: number
    direction_sign?: number
    flags: string[]
  }
  layer_curves: Record<string, number | string>[]
  layer_stats: { layer: number; total: number; annualized: number; max_drawdown: number }[]
  layer_monotonicity?: number
  turnover_annualized?: number
  top_minus_bottom_annualized?: number
  decay: { horizon: number; ic_mean: number; icir: number; n: number }[]
  regime?: { bull: { ic_mean: number; n: number; spread_ann: number }; bear: { ic_mean: number; n: number; spread_ann: number } } | null
  // factormine 附加
  is_summary?: IcSummary
  oos_summary?: IcSummary | null
  oos_start?: string
  yearly_stability?: YearlyStabilityRow[]
  stability_ratio?: number | null
  cost_table?: CostRow[]
  walk_forward?: WalkForwardRow[] | null
}

export interface AtomInfo {
  name: string
  category: string
  desc: string
  window: number
  needs: string[]
  status: 'ok' | 'limited' | 'unsupported'
  status_note: string | null
  coverage?: Record<string, { rows: number; from: string | null; to: string | null; ok: boolean }>
}

export interface OperatorInfo {
  name: string
  kind: 'ts' | 'cross' | 'math' | 'cond'
  signature: string
  desc: string
  aliases: string[]
  allows_cross: boolean
  allows_ts: boolean
  future_risk: string
  future_risk_note: string
}

export interface ScreenResult {
  factor_id: string
  expression: string
  as_of: string
  universe_size: number
  direction: string
  direction_note: string
  items: { rank: number; code: string; name: string; factor_value: number }[]
}

// ---- API ----

export function createMineJob(cfg: MineConfig): Promise<{ job_id: string; status: string }> {
  return request.post('/factormine/mine', cfg)
}

export function getMineJob(jobId: string): Promise<MineJob> {
  return request.get(`/factormine/job/${jobId}`)
}

export function mineJobAction(jobId: string, action: 'pause' | 'resume' | 'cancel'): Promise<{ ok: boolean }> {
  return request.post(`/factormine/job/${jobId}/${action}`)
}

export function listMineFactors(params: {
  job_id?: string
  status?: string
  verdict?: string
  in_library?: boolean
  min_rank_ic?: number
  limit?: number
  offset?: number
  order?: string
}): Promise<MineFactorRow[]> {
  return request.get('/factormine/factors', { params })
}

export function getMineFactor(factorId: string): Promise<MineFactorDetail> {
  return request.get(`/factormine/factor/${factorId}`)
}

export function setFactorLibrary(factorId: string, inLibrary: boolean, note?: string): Promise<MineFactorRow> {
  return request.post(`/factormine/factor/${factorId}/library`, { in_library: inLibrary, note })
}

export function revalidateFactor(factorId: string): Promise<MineFactorRow> {
  return request.post(`/factormine/factor/${factorId}/revalidate`)
}

export function screenWithFactor(factorId: string, topN = 20): Promise<ScreenResult> {
  return request.post(`/factormine/factor/${factorId}/screen`, { top_n: topN })
}

export function getMineLibrary(): Promise<{
  items: MineFactorRow[]
  stats: { total?: number; pass_n?: number; watch_n?: number; lib_n?: number }
}> {
  return request.get('/factormine/library')
}

export function getMineAtoms(): Promise<{
  atoms: AtomInfo[]
  capabilities: Record<string, { rows: number; from: string | null; to: string | null; ok: boolean }>
  note: string
}> {
  return request.get('/factormine/atoms')
}

export function getMineOperators(): Promise<{
  operators: OperatorInfo[]
  builtin: { name: string; kind: string; desc: string }[]
  notes: string[]
}> {
  return request.get('/factormine/operators')
}
