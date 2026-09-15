import request from './request'

/** 排名快照头:一次全宇宙评分的不可变记录(计算时间/行情时间/数据源) */
export interface SnapshotHeader {
  snapshot_id: string
  trade_date: string
  slot: string
  computed_at: string
  quote_time: string | null
  quote_source: string | null
  universe_n: number
  scored_n: number
  buyzone_n: number
  weights_key: string
  elapsed_ms: number
  status: string
}

export interface GroupDelta { group: string; label: string; delta: number; now: number | null; prev: number | null }

/** 相对上一快照的变化拆解:排名/综合分变化 + 各因子组贡献差 + 行情差 + 口径变化 */
export interface RankChange {
  prev_rank: number | null
  rank_delta: number | null
  composite_prev?: number
  composite_delta?: number
  group_deltas?: GroupDelta[]
  price_prev?: number | null
  price_delta_pct?: number | null
  reasons?: string[]
  flags?: string[]
  new: boolean
}

export type BuyState =
  | 'in_zone' | 'near_above' | 'wait_pullback' | 'extended'
  | 'below_zone' | 'invalidated' | 'no_zone' | 'bearish'

export interface DecisionParts {
  composite: number
  rank_stability: number
  trend_stability: number
  buy_quality: number
  sector_strength: number
  safety: number
}

/** 稳定候选池条目(全部由服务端计算) */
export interface PoolEntry {
  priority: number
  code: string
  name: string
  industry: string
  price: number | null
  pct_change: number | null
  amount?: number | null
  volume?: number | null
  composite: number
  rank: number
  rank_series: (number | null)[]
  rank_stability: number | null
  rank_stability_grade: string
  rank_stability_level: number
  trend_stability: number | null
  buy_state: BuyState
  buy_label: string
  buy_quality: number | null
  buy_zone: [number, number] | null
  sell_zone: [number, number] | null
  invalid_level: number | null
  invalidation: string | null
  dist_pct: number | null
  direction_label: string | null
  expected_target: [number, number] | null
  sector_strength: number | null
  risk: number
  risk_level: '低' | '中' | '高'
  risk_why: string[]
  decision: number
  decision_parts: DecisionParts
  decision_missing: string[]
  explain: string[]
  wait_text: string | null
  held: boolean
  is_actionable: boolean
  state_note?: string | null
  kline_date: string | null
  change?: RankChange | null
}

export interface TCandidate {
  code: string
  name: string
  shares: number
  available: number
  locked_today: number
  avg_cost: number | null
  last_buy_date: string | null
  pool: Partial<PoolEntry> | null
  t_signal?: any
  t_note?: string | null
}

export interface Failover {
  trigger: string
  next: { code: string; name: string; state: string; zone: [number, number] | null; wait_text: string | null } | null
}

export interface DecisionToday {
  status: 'ok' | 'no_snapshot'
  message?: string
  loggedIn?: boolean
  snapshot: SnapshotHeader | null
  prev_snapshot_id?: string | null
  window?: { snapshot_id: string; slot: string | null; trade_date: string | null }[]
  sample_n?: number
  sample_ok?: boolean
  sample_note?: string | null
  generated_at?: string
  trade_date_today?: string
  positions_n?: number
  focus: PoolEntry[]
  buy_now: PoolEntry | null
  alternates: PoolEntry[]
  waiting: PoolEntry[]
  failover: Failover | null
  new_entry_candidates: PoolEntry[]
  t_candidates: TCandidate[]
  locked_today: TCandidate[]
  watch_list: PoolEntry[]
  watch_extra_codes: string[]
  pool: PoolEntry[]
  weights: Record<string, number>
  rules: string[]
}

export function getDecisionToday(withT = true): Promise<DecisionToday> {
  return request.get('/decision/today', { params: { withT } })
}

export function getDecisionSnapshots(date?: string): Promise<{ snapshots: SnapshotHeader[]; latest_id: string | null }> {
  return request.get('/decision/snapshots', { params: date ? { date } : {} })
}

export function getDecisionSnapshot(id: string, limit?: number): Promise<{ snapshot: SnapshotHeader; prev: SnapshotHeader | null; items: any[] }> {
  return request.get(`/decision/snapshot/${id}`, { params: limit ? { limit } : {} })
}

export interface StockSnapshotPoint {
  snapshot_id: string
  slot: string
  trade_date: string
  computed_at: string
  quote_time: string | null
  quote_source: string | null
  price: number | null
  pct_change: number | null
  volume: number | null
  amount: number | null
  composite: number
  rank: number
  signal: string
  kline_date: string | null
  sector_rank_pct: number | null
  groups: Record<string, { score: number | null; contrib: number; weight_share: number; n: number }>
  buy: any
  change: RankChange | null
}

export function getDecisionStockHistory(code: string, n = 24): Promise<{ code: string; history: StockSnapshotPoint[] }> {
  return request.get(`/decision/stock/${code}/history`, { params: { n } })
}

export function runDecisionSnapshot(): Promise<{ status: string; snapshot?: SnapshotHeader; message?: string }> {
  return request.post('/decision/snapshot/run', {})
}

/** 快照口径的评分选股:{items, meta, prev} */
export interface ScreenSnapshotMeta {
  mode: 'snapshot' | 'live' | 'none'
  reason?: string
  snapshot_id?: string
  computed_at?: string
  quote_time?: string | null
  quote_source?: string | null
  universe_n?: number
  scored_n?: number
  kline_date?: string | null
  weights?: 'default' | 'custom'
  prev_snapshot_id?: string | null
}

export function runScreenerSnapshot(req: any): Promise<{ items: any[]; meta: ScreenSnapshotMeta; prev?: SnapshotHeader | null }> {
  return request.post('/screen/snapshot', req)
}

export const BUY_STATE_TYPE: Record<BuyState, 'success' | 'warning' | 'info' | 'danger'> = {
  in_zone: 'success',
  near_above: 'warning',
  wait_pullback: 'warning',
  below_zone: 'info',
  extended: 'info',
  no_zone: 'info',
  invalidated: 'danger',
  bearish: 'danger',
}

export const GROUP_LABEL: Record<string, string> = {
  trend: '趋势', momentum: '动量', volume_price: '量价', fund: '资金',
  sector: '板块', quality: '基本面', risk: '低波/风险',
}

export const PART_LABEL: Record<keyof DecisionParts, string> = {
  composite: '综合评分', rank_stability: '排名稳定度', trend_stability: '趋势稳定度',
  buy_quality: '买点质量', sector_strength: '板块强度', safety: '安全度(100−风险)',
}
