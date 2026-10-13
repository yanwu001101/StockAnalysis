import type { PredictionResult } from '@/types'
import { isFiniteNumber, percent, metric } from './factorResult'

const score = (value: unknown): value is number => isFiniteNumber(value) && value >= 0 && value <= 100

export function predictionPresentation(prediction: PredictionResult) {
  const calibration = prediction.calibration
  // The current API's explicit insufficient-data result contains placeholder 50/50 scores.
  const insufficient = prediction.status === 'INSUFFICIENT_DATA' || prediction.signalLabel === '数据不足'
  const failed = prediction.status === 'FAILED'
  const calibrated = !insufficient && !failed && calibration?.insufficient === false &&
    isFiniteNumber(calibration.n) && calibration.n > 0 && Number.isInteger(calibration.n) &&
    isFiniteNumber(calibration.win_rate) && calibration.win_rate >= 0 && calibration.win_rate <= 1
  const raw = prediction.rawScore100 !== undefined ? prediction.rawScore100
    : calibration?.insufficient === false ? null : prediction.probabilityUp
  const trendScore = !insufficient && !failed && score(raw) ? raw : null
  const confidence = !insufficient && !failed && score(prediction.confidence) ? prediction.confidence : null
  const up = calibrated ? calibration.win_rate! * 100 : trendScore
  return {
    calibrated,
    insufficient,
    signalLabel: failed ? '计算失败' : insufficient ? '数据不足' : prediction.signalLabel,
    signal: failed || insufficient ? 'neutral' : prediction.signal,
    title: failed ? '趋势分析 · 计算失败' : insufficient ? '趋势分析 · 数据不足' : calibrated ? '历史上涨频率 · T+5' : '趋势评分 · 未校准',
    up,
    upText: calibrated ? percent(calibration.win_rate, 1, false) : metric(trendScore, 1),
    scoreText: trendScore == null ? '—' : `${metric(trendScore, 1)} / 100`,
    confidenceText: confidence == null ? '—' : `${metric(confidence, 1)} / 100`,
    averageReturn: percent(calibration?.avg_return),
    sampleText: isFiniteNumber(calibration?.n) ? metric(calibration.n, 0) : '—',
    calibrationMessage: failed ? '趋势计算失败，评分与校准结果不可用。' : insufficient ? '历史行情不足，趋势评分和校准结果均不可用。' : calibrated
      ? '相似信号的历史统计频率，不代表本只股票未来上涨概率。'
      : calibration?.insufficient ? '校准样本不足；下方仅为模型评分，不是上涨概率或历史胜率。'
      : calibration ? '校准数据缺失或异常；下方仅展示可用的原始评分，不作概率解释。'
      : '尚无历史校准；下方仅为模型评分，不是上涨概率或历史胜率。',
  }
}
