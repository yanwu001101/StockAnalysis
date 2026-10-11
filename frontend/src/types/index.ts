// Stock types
export interface Stock {
  code: string
  name: string
  industry: string
  price: number
  change: number
  changePercent: number
  marketCap: number
  volume: number
  turnover: number
}

export interface StockDetail extends Stock {
  roe: number
  rawRoe: number
  debtRatio: number
  cashFlowPerShare: number
  revenueGrowth: number
  profitGrowth: number
  grossMargin: number
  pe: number
  pb: number
  dividendYield: number
}

// Strategy types
export interface StrategyResult {
  strategyName: string
  score: number
  signal: 'bullish' | 'bearish' | 'neutral'
  details: Record<string, any>
  triggered: boolean
}

export interface StrategyConfig {
  id: string
  name: string
  nameEn: string
  description: string
  enabled: boolean
  weight: number
  icon: string
  color: string
}

export interface CompositeScore {
  total: number
  strategies: Record<string, StrategyResult>
  signal: 'bullish' | 'bearish' | 'neutral'
}

// K-line data
export interface KLineData {
  date: string
  open: number
  close: number
  high: number
  low: number
  volume: number
  turnover: number
}

// Market types
export interface BreadthBin { label: string; count: number }

export interface MarketBreadth {
  /** 参与统计的「当日有成交」股票数;停牌/无成交不计入(见 excluded) */
  sampled: number
  excluded: number
  up: number
  down: number
  flat: number
  limitUp: number
  limitDown: number
  touchedUp: number
  touchedDown: number
  brokenUp: number
  brokenDown: number
  /** 炸板率 % = 触板未封住 / 触板;无触板时为 null */
  brokenRate: number | null
  brokenRateDown: number | null
  upOver5: number
  downOver5: number
  medianChange: number | null
  totalAmountYi: number | null
  /** 成交额前 5% 个股占全市场成交额比例 % — 衡量资金集中度 */
  top5pctAmountShare: number | null
  histogram: BreadthBin[]
}

export interface MarketSummary {
  totalStocks: number
  upCount: number
  downCount: number
  flatCount: number
  avgChange: number
  topGainers: Stock[]
  topLosers: Stock[]
  /** 北向每日净买入自 2024-08 停止披露,恒为 null;不得回退成 0 */
  northboundFlow: number | null
  hotSectors: SectorData[]
  breadth?: MarketBreadth | null
}

export interface SectorData {
  name: string
  change: number
  /** 资金流/动量口径当前无可用数据源 → null,不是 0 */
  flow: number | null
  momentum: number | null
  rank: number
  count?: number
  amountYi?: number | null
  leader?: string | null
  leaderChange?: number | null
}

// Watchlist
export interface WatchlistGroup {
  id: number
  name: string
  stocks: StockDetail[]
  createdAt: string
}

// Screener request
export interface ScreenerRequest {
  strategies: Record<string, { enabled: boolean; weight: number }>
  filters: {
    minScore: number
    minMarketCap: number
    maxDebtRatio: number
    minRoe: number
    industries: string[]
  }
  limit: number
  requireTriggered?: string[]
}

// Backtest
export interface BacktestRequest {
  strategyConfig: Record<string, { enabled: boolean; weight: number }>
  startDate: string
  endDate: string
  initialCapital: number
  topN: number
}

export interface BacktestResult {
  totalReturn: number
  annualizedReturn: number
  maxDrawdown: number
  sharpeRatio: number
  winRate: number
  tradeCount: number
  equityCurve: { date: string; value: number }[]
  trades: TradeRecord[]
  /** P0: 基准对比与交易摩擦（后端有数据才返回） */
  benchmarkReturn?: number
  excessReturn?: number
  turnoverRate?: number
  totalCosts?: number
  benchmarkCurve?: { date: string; value: number }[]
  costs?: Record<string, number>
}

export interface PaperOverview {
  status?: "not-started"
  account?: { initial_capital: number; top_n: number; rebalance: string; cash: number; start_date: string | null }
  metrics: { total_return: number; annualized_return: number; max_drawdown: number; sharpe_ratio: number; benchmark_return: number; excess_return: number; trade_count: number }
  total_costs: number
  equity_curve: { date: string; equity: number; benchmark: number | null }[]
  positions: { code: string; shares: number; avg_cost: number; last_close: number; market_value: number; weight: number; pnl_pct: number; buy_date: string }[]
  recent_trades: { trade_date: string; code: string; side: string; shares: number; price: number; amount: number; cost: number; reason: string }[]
}

/** 实盘半自动·里程碑1：委托单（系统只生成清单，人工执行，状态存本机） */
export interface PaperOrder {
  code: string
  name: string
  side: 'buy' | 'sell' | string
  direction: string
  shares: number
  ref_price: number
  amount: number
  reason: string
}

export interface PaperOrders {
  status: 'ok' | 'no-trades' | 'no-db' | string
  trade_date: string | null
  generated_at?: string
  orders: PaperOrder[]
  target_positions: { code: string; name: string; shares: number; avg_cost: number; last_close: number }[]
  note?: string
}

export type FactorStatus = 'VALID' | 'CANDIDATE' | 'INSIGNIFICANT' | 'INSUFFICIENT_DATA' | 'FAILED'
export interface ICSummary {
  mean: number | null
  std: number | null
  icir: number | null
  positive_ratio: number | null
  negative_ratio?: number | null
  t_stat: number | null
  p_value?: number | null
  n: number
}
export interface FactorLabResult {
  engine_version?: string
  status?: FactorStatus
  error?: string
  error_kind?: 'coverage' | 'compute' | 'expression'
  sample_info?: { periods: number; avg_cross_section: number | null; observations: number; skipped_periods?: number; holding_trading_days?: number }
  strategy_id: string | null
  factor_name?: string
  expression?: string
  start: string
  end: string
  rebalance: string
  layers: number
  codes_analyzed: number
  periods: number
  smoothing_days?: number
  ic_summary: ICSummary
  ic_adjusted_summary?: ICSummary
  ic_series: { date: string; ic: number; n?: number; execution_date?: string; return_end?: string }[]
  ic_neutral_summary?: ICSummary | null
  ic_pearson_summary?: ICSummary | null
  rating?: { grade: string; strength: number; confidence: number;
             direction: 'positive' | 'reverse' | 'neutral'; status: string; status_code?: FactorStatus;
             dimensions: Record<string, number | null>; net_spread_ann: number;
             adjusted_gross_spread_ann?: number | null; adjusted_net_spread_ann?: number | null;
             cost_per_turnover: number; cost_annualized?: number | null;
             robustness?: number | null; tradability?: number | null; flags: string[];
             robustness_components?: Record<string, number>; tradability_note?: string } | null
  validation?: { split_ratio: number; direction_sign: number; status: string; note: string;
                 train: ICSummary & { start?: string; end?: string }; test: ICSummary & { start?: string; end?: string };
                 normalized_test: ICSummary; direction_consistent: boolean | null;
                 rolling_window: number; rolling: (ICSummary & { date: string })[] }
  market_cap_diagnostic?: { enabled: boolean; summary?: ICSummary | null; point_in_time: false; used_in_rating: false; note: string }
  methodology?: { signal: string; execution: string; exit: string; annualization: string; universe: string;
                  universe_as_of: string; cost: string; industry: string; limitations: string[] }
  layer_monotonicity?: number | null
  turnover_annualized?: number | null
  regime?: { bull: { ic_mean: number; n: number; spread_ann: number }; bear: { ic_mean: number; n: number; spread_ann: number } } | null
  layer_curves: Record<string, number | string>[]
  layer_stats: { layer: number; total: number; annualized: number }[]
  top_minus_bottom_annualized: number | null
  decay: { horizon: number; ic_mean: number | null; icir: number | null; p_value?: number | null; n: number }[]
}

export interface TradeRecord {
  date: string
  code: string
  name: string
  action: 'buy' | 'sell'
  price: number
  shares: number
  pnl: number
}

// 保存的回测列表项(后端只回摘要列)
export interface SavedBacktestSummary {
  id: number
  name: string
  stockCode: string
  strategyId: string
  startDate: string
  endDate: string
  totalReturn: number
  annualizedReturn: number
  maxDrawdown: number
  sharpeRatio: number
  winRate: number
  tradeCount: number
  createdAt: string
}

// User
export interface UserInfo {
  id: number
  username: string
  nickname: string
  avatar: string
  role?: 'ADMIN' | 'USER'
  createdAt: string
}

// API response
export interface ApiResponse<T> {
  code: number
  message: string
  data: T
  dataTime?: number
}

// Prediction types
export interface SignalDimension {
  name: string
  nameEn: string
  score: number        // -1 to +1
  weight: number
  detail: string
  subSignals: Record<string, string>
}

export interface PredictionResult {
  code: string
  name: string
  price: number
  probabilityUp: number
  probabilityDown: number
  confidence: number
  signal: 'bullish' | 'bearish' | 'neutral'
  signalLabel: string
  compositeDirection: number
  dimensions: SignalDimension[]
  keyDrivers: string[]
  riskWarnings: string[]
  timeHorizon: string
  calibration?: {
    insufficient: boolean
    win_rate?: number
    avg_return?: number
    n?: number
    bucket?: [number, number]
    cal_date?: string
    universe?: number
  } | null
  rawScore100?: number
}
