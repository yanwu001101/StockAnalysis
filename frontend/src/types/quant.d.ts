/**
 * Wire contracts — mirrored 1:1 from the backend
 * (`backend/app/domain/models.py`, camelCase aliases).
 *
 * The backend serialises with `by_alias=True`, so every JSON key is camelCase;
 * these interfaces are the single source of truth for the frontend. No `any`,
 * no type assertions anywhere in this file.
 */

// ---------------------------------------------------------------------------
// scalar unions
// ---------------------------------------------------------------------------

export type TradeSignal = 'BUY' | 'HOLD' | 'SELL'

/** Verdict colour: risk semantics (green = safe, red = dangerous). */
export type ColorClass = 'text-green' | 'text-yellow' | 'text-red'

export type AgentId = 'fundamental' | 'sentiment' | 'technical' | 'risk'

export type AgentStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED'

export type TaskStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED'

export type MetricStatus = 'VALID' | 'INSUFFICIENT_DATA' | 'FAILED'

export type WsPayloadType = 'progress' | 'verdict' | 'heartbeat' | 'error'

export type DebateSide = 'BULL' | 'BEAR'

// ---------------------------------------------------------------------------
// verdict contracts
// ---------------------------------------------------------------------------

export interface QuantMetricsDTO {
  sharpeRatio: number
  maxDrawdown: number
  winRate: number
  totalReturn: number
  alpha: number
  beta: number
}

/** Per-metric provenance: a float cannot say "uncomputable", this can. */
export type MetricStatusMap = Record<keyof QuantMetricsDTO, MetricStatus>

export interface HumanReadableVerdict {
  score: number
  signal: TradeSignal
  reasons: string[]
  colorClass: ColorClass
}

export interface ChartMarker {
  /** YYYY-MM-DD — must align exactly with the candlestick x-axis. */
  date: string
  price: number
  action: 'BUY' | 'SELL'
  reason: string
}

export interface TradeDTO {
  date: string
  side: 'BUY' | 'SELL'
  shares: number
  price: number
  commission: number
  stampTax: number
  transferFee: number
  /** 已实现盈亏（SELL 侧；BUY 侧为 null） */
  pnl: number | null
}

export interface DebateDTO {
  round: number
  side: DebateSide
  argument: string
  conviction: number
}

export interface QuantVerdictPayload {
  rawMetrics: QuantMetricsDTO
  humanVerdict: HumanReadableVerdict
  chartMarkers: ChartMarker[]
  metricStatus: MetricStatusMap
  symbol: string
  /** [open, close, low, high] per bar — ECharts candlestick order. */
  candles: number[][]
  /** Same length and order as `candles` (YYYY-MM-DD); aligns markPoints. */
  dates: string[]
  /** Mark-to-market equity aligned 1:1 with `dates`. */
  equityCurve: number[]
  trades: TradeDTO[]
  debate: DebateDTO[]
  warnings: string[]
}

// ---------------------------------------------------------------------------
// progress contracts
// ---------------------------------------------------------------------------

export interface AgentProgressPayload {
  taskId: string
  agentId: AgentId
  agentName: string
  status: AgentStatus
  progress: number
  message: string
  timestamp: number
}

export type WsPayload =
  | { type: 'progress'; payload: AgentProgressPayload }
  | { type: 'verdict'; payload: QuantVerdictPayload }
  | { type: 'heartbeat'; payload: Record<string, string> }
  | { type: 'error'; payload: { message: string } }

export interface WsEnvelope {
  type: WsPayloadType
  taskId: string
  payload: WsPayload['payload']
}

// ---------------------------------------------------------------------------
// REST contracts
// ---------------------------------------------------------------------------

/** 回测实验室的可选覆盖项（请求体 camelCase）。 */
export interface BacktestOverrides {
  initialCapital?: number
  commissionRate?: number
  commissionMin?: number
  stampTaxRate?: number
  transferFeeRate?: number
  slippage?: number
  lotSize?: number
  /** YYYY-MM-DD */
  startDate?: string
  endDate?: string
}

export interface AnalyzeRequest {
  symbol: string
  backtest?: BacktestOverrides
}

export interface AnalyzeResponse {
  taskId: string
  symbol: string
  status: TaskStatus
}

export interface TaskRecord {
  taskId: string
  symbol: string
  status: TaskStatus
  createdAt: number
  updatedAt: number
  error: string | null
  verdict: QuantVerdictPayload | null
}

export interface SystemStats {
  total: number
  running: number
  completed: number
  failed: number
  successRate: number
}

export interface MarketOverview {
  benchmarkSymbol: string
  benchmarkName: string
  lastClose: number | null
  changePct: number | null
  asOf: string
  advancing: number | null
  declining: number | null
  flat: number | null
  breadthAvailable: boolean
}

export interface ApiErrorBody {
  error: {
    code: string
    message: string
  }
}
