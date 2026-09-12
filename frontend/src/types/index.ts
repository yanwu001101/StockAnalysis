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
export interface MarketSummary {
  totalStocks: number
  upCount: number
  downCount: number
  flatCount: number
  avgChange: number
  topGainers: Stock[]
  topLosers: Stock[]
  northboundFlow: number
  hotSectors: SectorData[]
}

export interface SectorData {
  name: string
  change: number
  flow: number
  momentum: number
  rank: number
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

export interface FactorLabResult {
  error?: string
  error_kind?: "coverage" | "compute"
  sample_info?: { periods: number; avg_cross_section: number; observations: number }
  strategy_id: string
  start: string
  end: string
  rebalance: string
  layers: number
  codes_analyzed: number
  periods: number
  ic_summary: { mean: number; std: number; icir: number; positive_ratio: number; t_stat: number; n: number }
  ic_series: { date: string; ic: number }[]
  ic_neutral_summary?: { mean: number; std: number; icir: number; positive_ratio: number; t_stat: number; n: number }
  rating?: { grade: string; strength: number; confidence: number;
             direction: "positive" | "reverse" | "neutral"; status: string;
             dimensions: Record<string, number>; net_spread_ann: number;
             cost_per_turnover: number; cost_annualized?: number;
             robustness?: number; tradability?: number; flags: string[] }
  layer_monotonicity?: number
  turnover_annualized?: number
  regime?: { bull: { ic_mean: number; n: number; spread_ann: number }; bear: { ic_mean: number; n: number; spread_ann: number } } | null
  layer_curves: Record<string, number | string>[]
  layer_stats: { layer: number; total: number; annualized: number }[]
  top_minus_bottom_annualized: number
  decay: { horizon: number; ic_mean: number; icir: number; n: number }[]
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
}
