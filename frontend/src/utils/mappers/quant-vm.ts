/**
 * ViewModel mapper — metric -> plain language, strategy pattern.
 *
 * One translator class per metric: it owns both the scoring rule and the
 * Chinese wording (SOLID open-closed — adding a metric never touches the
 * registry). The backend has an identical table
 * (`backend/app/services/verdict.py`); this copy lets the UI explain a metric
 * before the verdict arrives. Thresholds are pinned by tests on both sides —
 * keep them in sync.
 */
import type {
  ColorClass,
  HumanReadableVerdict,
  MetricStatus,
  MetricStatusMap,
  QuantMetricsDTO,
  TradeSignal,
} from '@/types/quant'

export interface MetricTranslation {
  scoreDelta: number
  text: string
  available: boolean
}

export interface MetricTranslator {
  readonly key: keyof QuantMetricsDTO
  translate(value: number, status: MetricStatus): MetricTranslation
}

const BASE_SCORE = 50
const BUY_THRESHOLD = 65
const SELL_THRESHOLD = 35

abstract class BaseMetricTranslator implements MetricTranslator {
  abstract readonly key: keyof QuantMetricsDTO
  protected abstract readonly label: string

  translate(value: number, status: MetricStatus): MetricTranslation {
    if (status !== 'VALID') {
      return {
        scoreDelta: 0,
        text: `${this.label}无法计算（${status}），已按中性处理，不计入评分`,
        available: false,
      }
    }
    return this.valid(value)
  }

  protected abstract valid(value: number): MetricTranslation
}

class SharpeTranslator extends BaseMetricTranslator {
  readonly key = 'sharpeRatio' as const
  protected readonly label = '夏普比率'

  protected valid(value: number): MetricTranslation {
    if (value < 0) {
      return { scoreDelta: -20, text: `夏普比率 ${value.toFixed(2)}：承担风险没有换来回报`, available: true }
    }
    if (value < 1) {
      return { scoreDelta: -5, text: `夏普比率 ${value.toFixed(2)}：风险调整后收益一般`, available: true }
    }
    if (value < 2) {
      return { scoreDelta: 10, text: `夏普比率 ${value.toFixed(2)}：每承担一份风险获得的回报较好`, available: true }
    }
    return { scoreDelta: 20, text: `夏普比率 ${value.toFixed(2)}：风险调整后收益优秀`, available: true }
  }
}

class MaxDrawdownTranslator extends BaseMetricTranslator {
  readonly key = 'maxDrawdown' as const
  protected readonly label = '最大回撤'

  protected valid(value: number): MetricTranslation {
    const worstYuan = Math.abs(value) * 10_000
    if (value > -0.1) {
      return {
        scoreDelta: 10,
        text: `历史最差情况：每投入1万，最多可能亏 ${worstYuan.toFixed(0)} 元，回撤很浅`,
        available: true,
      }
    }
    if (value > -0.2) {
      return {
        scoreDelta: 0,
        text: `历史最差情况：每投入1万，最多可能亏 ${worstYuan.toFixed(0)} 元，回撤可接受`,
        available: true,
      }
    }
    if (value > -0.35) {
      return {
        scoreDelta: -10,
        text: `历史最差情况：每投入1万，最多可能亏 ${worstYuan.toFixed(0)} 元，回撤偏深`,
        available: true,
      }
    }
    return {
      scoreDelta: -20,
      text: `历史最差情况：每投入1万，最多可能亏 ${worstYuan.toFixed(0)} 元，回撤很深`,
      available: true,
    }
  }
}

class WinRateTranslator extends BaseMetricTranslator {
  readonly key = 'winRate' as const
  protected readonly label = '胜率'

  protected valid(value: number): MetricTranslation {
    const percent = value * 100
    if (percent >= 60) {
      return { scoreDelta: 10, text: `胜率 ${percent.toFixed(1)}%：多数交易能赚到钱`, available: true }
    }
    if (percent >= 45) {
      return { scoreDelta: 0, text: `胜率 ${percent.toFixed(1)}%：盈亏大致各半`, available: true }
    }
    return { scoreDelta: -10, text: `胜率 ${percent.toFixed(1)}%：多数交易以亏损收场`, available: true }
  }
}

class TotalReturnTranslator extends BaseMetricTranslator {
  readonly key = 'totalReturn' as const
  protected readonly label = '总收益率'

  protected valid(value: number): MetricTranslation {
    const percent = value * 100
    if (percent > 20) {
      return { scoreDelta: 10, text: `区间总收益 ${percent.toFixed(2)}%：表现较好`, available: true }
    }
    if (percent > 0) {
      return { scoreDelta: 0, text: `区间总收益 ${percent.toFixed(2)}%：小幅盈利`, available: true }
    }
    return { scoreDelta: -15, text: `区间总收益 ${percent.toFixed(2)}%：区间内亏损`, available: true }
  }
}

class AlphaTranslator extends BaseMetricTranslator {
  readonly key = 'alpha' as const
  protected readonly label = '阿尔法'

  protected valid(value: number): MetricTranslation {
    if (value > 0.05) {
      return { scoreDelta: 10, text: `年化阿尔法 ${value.toFixed(2)}：明显跑赢基准`, available: true }
    }
    if (value >= -0.05) {
      return { scoreDelta: 0, text: `年化阿尔法 ${value.toFixed(2)}：与基准大致持平`, available: true }
    }
    return { scoreDelta: -10, text: `年化阿尔法 ${value.toFixed(2)}：跑输基准`, available: true }
  }
}

class BetaTranslator extends BaseMetricTranslator {
  readonly key = 'beta' as const
  protected readonly label = '贝塔'

  protected valid(value: number): MetricTranslation {
    if (value >= 0.8 && value <= 1.2) {
      return { scoreDelta: 5, text: `贝塔 ${value.toFixed(2)}：波动与大盘基本同步`, available: true }
    }
    return { scoreDelta: -5, text: `贝塔 ${value.toFixed(2)}：波动明显偏离大盘`, available: true }
  }
}

export const TRANSLATORS: readonly MetricTranslator[] = [
  new SharpeTranslator(),
  new MaxDrawdownTranslator(),
  new WinRateTranslator(),
  new TotalReturnTranslator(),
  new AlphaTranslator(),
  new BetaTranslator(),
]

function clampScore(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)))
}

export function signalFor(score: number): TradeSignal {
  if (score >= BUY_THRESHOLD) return 'BUY'
  if (score <= SELL_THRESHOLD) return 'SELL'
  return 'HOLD'
}

export function colorClassFor(score: number): ColorClass {
  if (score >= BUY_THRESHOLD) return 'text-green'
  if (score >= SELL_THRESHOLD) return 'text-yellow'
  return 'text-red'
}

/**
 * Deterministic local verdict — the UI shows it while the real one streams in.
 * When `statuses` is omitted every metric is assumed VALID.
 */
export function translateMetrics(
  metrics: QuantMetricsDTO,
  statuses?: MetricStatusMap,
): HumanReadableVerdict {
  let score = BASE_SCORE
  const reasons: string[] = []

  for (const translator of TRANSLATORS) {
    const status: MetricStatus = statuses?.[translator.key] ?? 'VALID'
    const translation = translator.translate(metrics[translator.key], status)
    score += translation.scoreDelta
    reasons.push(translation.text)
  }

  const bounded = clampScore(score)
  return {
    score: bounded,
    signal: signalFor(bounded),
    reasons,
    colorClass: colorClassFor(bounded),
  }
}
