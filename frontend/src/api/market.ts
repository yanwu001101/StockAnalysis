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

export function getIndices(): Promise<any[]> {
  return request.get('/market/indices')
}

export function getGainers(limit: number = 20): Promise<any[]> {
  return request.get('/market/gainers', { params: { limit } })
}

export function getLosers(limit: number = 20): Promise<any[]> {
  return request.get('/market/losers', { params: { limit } })
}

export function getMostActive(limit: number = 20): Promise<any[]> {
  return request.get('/market/most-active', { params: { limit } })
}
