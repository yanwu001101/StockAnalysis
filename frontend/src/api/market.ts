import request from './request'
import type { MarketSummary, SectorData } from '@/types'

export function getMarketSummary(): Promise<MarketSummary> {
  return request.get('/market/summary')
}

export function getSectorRotation(): Promise<SectorData[]> {
  return request.get('/market/sector-rotation')
}

export function getNorthboundFlow(days: number = 30): Promise<any[]> {
  return request.get('/market/northbound-flow', { params: { days } })
}

export function getTopStocks(limit: number = 20): Promise<any[]> {
  return request.get('/market/top-stocks', { params: { limit } })
}
