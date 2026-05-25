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

export function getStockPrediction(code: string, signal?: AbortSignal): Promise<PredictionResult> {
  return request.get(`/stock/${code}/prediction`, { signal })
}

export function getStockProSignal(code: string, signal?: AbortSignal): Promise<any> {
  return request.get(`/stock/${code}/pro-signal`, { signal })
}

export function searchStock(keyword: string): Promise<any[]> {
  return request.get('/stock/search', { params: { keyword } })
}
