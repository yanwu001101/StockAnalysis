// 评分 / 信号相关的阈值与文案，全站只在这里定义一次。

export type Level = 'high' | 'mid' | 'low'
export type Signal = 'bullish' | 'bearish' | 'neutral'

export interface StrategyStats {
  bullish: number
  effective: number
  triggered: number
}

export function scoreLevel(score: number | null | undefined): Level {
  if (score == null || !Number.isFinite(score)) return 'low'
  if (score >= 80) return 'high'
  if (score >= 60) return 'mid'
  return 'low'
}

export function signalText(signal?: string | null): string {
  return signal === 'bullish' ? '看多' : signal === 'bearish' ? '看空' : '中性'
}

/** 看多策略占有效策略的比例决定等级。 */
export function stratLevel(stats?: StrategyStats | null): Level {
  if (!stats || !stats.effective) return 'low'
  const ratio = stats.bullish / stats.effective
  if (ratio >= 0.5) return 'high'
  if (ratio >= 0.3) return 'mid'
  return 'low'
}

export function levelTagType(level: Level): 'success' | 'warning' | 'danger' {
  return level === 'high' ? 'success' : level === 'mid' ? 'warning' : 'danger'
}

/** 股票代码统一补齐 6 位（后端偶尔返回数字型代码，前导 0 会丢）。 */
export function padCode(code: string | number | null | undefined): string {
  if (code == null) return ''
  return String(code).padStart(6, '0')
}

export function stockPath(code: string | number | null | undefined): string {
  return `/stock/${padCode(code)}`
}
