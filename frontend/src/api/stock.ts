import request from './request'
import type { StockDetail, KLineData, CompositeScore } from '@/types'

export function getStockDetail(code: string): Promise<StockDetail> {
  return request.get(`/stock/${code}`)
}

export function getStockKLine(code: string, period: string = 'daily', days: number = 250): Promise<KLineData[]> {
  return request.get(`/stock/${code}/kline`, { params: { period, days } })
}

export function getStockStrategies(code: string): Promise<CompositeScore> {
  return request.get(`/stock/${code}/strategies`)
}

export function searchStock(keyword: string): Promise<any[]> {
  return request.get('/stock/search', { params: { keyword } })
}
