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

// User
export interface UserInfo {
  id: number
  username: string
  nickname: string
  avatar: string
  createdAt: string
}

// API response
export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}
