import request from './request'

// 短线做 T(日内 T+0)建议
export interface TSubscores {
  position: number
  volume: number
  momentum: number
  index: number
}

export interface TIndexCtx {
  key: string
  name: string
  pct_change: number
  pos: number
  vwap_dev: number
  slope_30m: number
  trend: 'up' | 'down' | 'flat'
  regime: 'strong' | 'neutral' | 'weak'
}

export interface TPosition {
  shares: number
  available: number
  avg_cost: number
  pnl_pct: number | null
}

export interface TTrendPoint {
  t: string
  price: number
  avg: number
  vol: number
}

export interface TPriceLimit {
  limit_pct: number
  up: number
  down: number
  near_limit_up: boolean
  near_limit_down: boolean
}

export interface TSignal {
  code: string
  name: string
  price: number | null
  pct_change: number | null
  vwap: number | null
  day_high: number | null
  day_low: number | null
  day_open: number | null
  prev_close: number | null
  intraday_pos: number | null
  vwap_dev: number | null
  amplitude: number | null
  action: 'positive_t' | 'negative_t' | 'wait' | 'no_data'
  action_label: string
  strength: number
  buy_zone: [number, number] | null
  sell_zone: [number, number] | null
  reasons: string[]
  risks: string[]
  data_time: string | null
  disclaimer: string
  // ---- 可解释评分 ----
  subscores: TSubscores
  weights: TSubscores
  // ---- 日内结构 ----
  poc: number | null
  value_area: [number, number] | null
  supports: number[]
  resists: number[]
  // ---- 量能 ----
  pv_pattern: string | null
  active_buy_ratio: number | null
  big_order_net: number | null
  big_order_dir: number
  liangbi: number | null
  // ---- 大盘 ----
  index_ctx: TIndexCtx | null
  // ---- 持仓真 T ----
  has_position: boolean
  position: TPosition | null
  t_mode: string
  t_side: string | null
  t_shares: number
  cover_price: number | null
  est_profit: number | null
  est_profit_pct: number | null
  new_avg_cost: number | null
  cost_impact: number | null
  available_capped: boolean
  // ---- A 股规则 & 画图 ----
  price_limit: TPriceLimit | null
  degraded: boolean
  trend: TTrendPoint[] | null
}

export interface TPositionInput {
  shares?: number
  avg_cost?: number
  available?: number
}

export function getTSignal(code: string, pos?: TPositionInput): Promise<TSignal> {
  const params: Record<string, number> = {}
  if (pos) {
    if (pos.shares != null) params.shares = pos.shares
    if (pos.avg_cost != null) params.avg_cost = pos.avg_cost
    if (pos.available != null) params.available = pos.available
  }
  return request.get(`/t/stock/${code}`, { params })
}

export function getTSignalBatch(codes: string[]): Promise<TSignal[]> {
  return request.post('/t/batch', { codes })
}

export interface TBatchPosition {
  code: string
  shares?: number
  avg_cost?: number
  available?: number
}

export function getTSignalBatchWithPositions(positions: TBatchPosition[]): Promise<TSignal[]> {
  return request.post('/t/batch', { positions })
}

// 量价形态中文说明(前端展示用)
export const PV_LABEL: Record<string, string> = {
  up_vol_up: '价升量增',
  down_vol_up: '价跌量增',
  up_vol_dry: '价升量缩',
  down_vol_dry: '价跌量缩',
  flat: '量价平稳',
}
