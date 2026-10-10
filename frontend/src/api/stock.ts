import request from './request'
import type { StockDetail, KLineData, CompositeScore, PredictionResult } from '@/types'

export function getStockDetail(code: string, signal?: AbortSignal): Promise<StockDetail> {
  return request.get(`/stock/${code}`, { signal })
}

export function getStockKLine(code: string, period: string = 'daily', days: number = 250, signal?: AbortSignal, adjust: string = 'qfq'): Promise<KLineData[]> {
  return request.get(`/stock/${code}/kline`, { params: { period, days, adjust }, signal })
}

export function getStockStrategies(code: string, signal?: AbortSignal): Promise<CompositeScore> {
  return request.get(`/stock/${code}/strategies`, { signal })
}

export function getStockF10(code: string, signal?: AbortSignal): Promise<any> {
  return request.get(`/stock/${code}/f10`, { signal })
}

export interface FinQuarter {
  reportDate: string
  revenue: number | null
  netProfit: number | null
  revenueYoy: number | null
  netProfitYoy: number | null
  roe: number | null
  grossMargin: number | null
  debtRatio: number | null
  eps: number | null
  indRevenueYoy: number | null
  indNetProfitYoy: number | null
  indRoe: number | null
  indCount: number | null
}

export interface FinValuation {
  industry: string | null
  industrySize: number
  pe: number | null
  pb: number | null
  pePctile?: number
  pbPctile?: number
  roe?: number | null
  roePctile?: number
  roeQuarters?: number
}

export interface FinancialsData {
  code: string
  industry: string | null
  quarters: FinQuarter[]
  valuation: FinValuation | null
}

export function getStockFinancials(code: string, signal?: AbortSignal): Promise<FinancialsData> {
  return request.get(`/stock/${code}/financials`, { signal })
}

export interface BatchStrategyItem {
  code: string
  /** null = 数据不足以计算,前端显示「—」,不得当 0 用 */
  total: number | null
  signal: string | null
  strategyStats: { effective: number; total: number; bullish: number; bearish: number; triggered: number } | null
}

/** 一次请求拿多只股票的策略综合分与策略统计（与选股页同引擎、同权重口径）。 */
export function postStrategiesBatch(
  codes: string[],
  strategies?: Record<string, unknown>,
): Promise<{ items: BatchStrategyItem[] }> {
  return request.post('/stock/strategies/batch', { codes, strategies })
}

export function getStockPrediction(code: string, signal?: AbortSignal): Promise<PredictionResult> {
  return request.get(`/stock/${code}/prediction`, { signal })
}

export function getStockProSignal(code: string, signal?: AbortSignal): Promise<any> {
  return request.get(`/stock/${code}/pro-signal`, { signal })
}

export function searchStock(keyword: string): Promise<any[]> {
  return request.get('/stock/search', { params: { keyword } })
}
