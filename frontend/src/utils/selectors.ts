/**
 * Pure selectors shared by the workspaces.
 *
 * Everything here is a total function of its inputs — no store access, no
 * dates-from-now, no randomness — so the linkage logic (click a candle day ->
 * both side panels react) is unit-testable without mounting a component.
 */
import type {
  ChartMarker,
  QuantVerdictPayload,
  TradeDTO,
} from '@/types/quant'

export interface DayContext {
  index: number
  date: string
  open: number
  close: number
  low: number
  high: number
  /** 当日涨跌幅（相对开盘），如 0.0123 */
  changePct: number
  /** 当日若产生交易信号，则带上信号与理由 */
  marker: ChartMarker | null
}

/**
 * Locate a trading day inside a verdict payload.
 * Returns null when the date is not on the axis — never a shifted match.
 */
export function dayContext(
  verdict: QuantVerdictPayload | null,
  date: string,
): DayContext | null {
  if (verdict === null) return null
  const index = verdict.dates.indexOf(date)
  if (index < 0 || index >= verdict.candles.length) return null
  const candle = verdict.candles[index]
  if (!candle || candle.length < 4) return null
  const [open, close, low, high] = candle
  const changePct = open > 0 ? close / open - 1 : 0
  const marker = verdict.chartMarkers.find((item) => item.date === date) ?? null
  return { index, date, open, close, low, high, changePct, marker }
}

/** Nearest tradeable day at or before `date` (for keyboard/arrow navigation). */
export function nearestDay(verdict: QuantVerdictPayload | null, date: string): string | null {
  if (verdict === null || verdict.dates.length === 0) return null
  const exact = verdict.dates.indexOf(date)
  if (exact >= 0) return date
  let candidate: string | null = null
  for (const item of verdict.dates) {
    if (item <= date) candidate = item
    else break
  }
  return candidate ?? verdict.dates[0]
}

export interface EquitySeries {
  dates: string[]
  values: number[]
  /** 区间最大回撤（用于图表标注），无数据时为 null */
  maxDrawdown: number | null
}

/** Equity curve aligned with the candle axis; empty input -> empty series. */
export function equitySeries(verdict: QuantVerdictPayload | null): EquitySeries {
  if (verdict === null || verdict.dates.length === 0) {
    return { dates: [], values: [], maxDrawdown: null }
  }
  const values = verdict.equityCurve.slice(0, verdict.dates.length)
  let peak = Number.NEGATIVE_INFINITY
  let maxDrawdown: number | null = null
  for (const value of values) {
    if (value > peak) peak = value
    if (peak > 0) {
      const drawdown = value / peak - 1
      if (maxDrawdown === null || drawdown < maxDrawdown) maxDrawdown = drawdown
    }
  }
  return {
    dates: verdict.dates.slice(0, values.length),
    values,
    maxDrawdown,
  }
}

export interface TradeRow {
  key: string
  date: string
  side: 'BUY' | 'SELL'
  shares: number
  price: number
  fees: number
  pnl: number | null
  pnlPct: number | null
}

/** Flatten trades for the log table; fees = commission + stamp + transfer. */
export function tradeRows(verdict: QuantVerdictPayload | null): TradeRow[] {
  if (verdict === null) return []
  const rows: TradeRow[] = []
  let entryPrice: number | null = null
  verdict.trades.forEach((trade: TradeDTO, index: number) => {
    const fees = trade.commission + trade.stampTax + trade.transferFee
    let pnlPct: number | null = null
    if (trade.side === 'BUY') {
      entryPrice = trade.price
    } else if (entryPrice !== null && entryPrice > 0 && trade.pnl !== null) {
      pnlPct = trade.pnl / (entryPrice * trade.shares)
    }
    rows.push({
      key: `${trade.date}-${trade.side}-${index}`,
      date: trade.date,
      side: trade.side,
      shares: trade.shares,
      price: trade.price,
      fees,
      pnl: trade.pnl,
      pnlPct,
    })
  })
  return rows
}

// ---------------------------------------------------------------------------
// Command palette filtering
// ---------------------------------------------------------------------------

export interface PaletteItem {
  id: string
  /** 展示名（股票名或指令名） */
  label: string
  /** 副标题/说明 */
  hint: string
  group: 'navigation' | 'watchlist' | 'action'
  /** 导航目标路由或动作标识 */
  target: string
}

/** Subsequence fuzzy match; returns null when `query` is not a subsequence. */
function fuzzyScore(text: string, query: string): number | null {
  const lowerText = text.toLowerCase()
  const lowerQuery = query.toLowerCase()
  if (lowerQuery.length === 0) return 1
  let score = 0
  let cursor = 0
  let streak = 0
  for (const char of lowerQuery) {
    const found = lowerText.indexOf(char, cursor)
    if (found < 0) return null
    streak = found === cursor ? streak + 1 : 1
    score += 1 + streak * 0.5 + (found === 0 ? 2 : 0)
    cursor = found + 1
  }
  return score
}

/**
 * Filter and rank palette items. Empty query returns everything, navigation
 * first. Deterministic ordering: score desc, then label asc.
 */
export function filterPaletteItems(
  query: string,
  items: readonly PaletteItem[],
): PaletteItem[] {
  const trimmed = query.trim()
  const groupOrder: Record<PaletteItem['group'], number> = {
    navigation: 0,
    action: 1,
    watchlist: 2,
  }
  if (trimmed.length === 0) {
    return [...items].sort(
      (a, b) =>
        groupOrder[a.group] - groupOrder[b.group] || a.label.localeCompare(b.label),
    )
  }
  const scored: Array<{ item: PaletteItem; score: number }> = []
  for (const item of items) {
    const labelScore = fuzzyScore(item.label, trimmed)
    const hintScore = fuzzyScore(item.hint, trimmed)
    const best = Math.max(labelScore ?? Number.NEGATIVE_INFINITY, (hintScore ?? Number.NEGATIVE_INFINITY) * 0.5)
    if (best !== Number.NEGATIVE_INFINITY) {
      scored.push({ item, score: best })
    }
  }
  scored.sort(
    (a, b) =>
      groupOrder[a.item.group] - groupOrder[b.item.group] ||
      b.score - a.score ||
      a.item.label.localeCompare(b.item.label),
  )
  return scored.map((entry) => entry.item)
}

/** 6 位代码 -> 带交易所前缀展示（sh600519 / sz000001） */
export function displaySymbol(symbol: string): string {
  const code = symbol.replace(/\D/g, '').padStart(6, '0').slice(-6)
  if (/^[69]/.test(code)) return `sh${code}`
  if (/^[48]/.test(code)) return `bj${code}`
  return `sz${code}`
}
