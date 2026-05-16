import request from './request'

export interface LhbRow {
  code: string
  tradeDate: string
  reason: string
  buyAmount: number | null
  sellAmount: number | null
  netAmount: number | null
  seatType: string
  seatName: string
}

export interface LhbAggRow {
  code: string
  name: string
  industry: string
  appearances: number
  netSum: number
  lastSeen: string
  reasons?: string
  buySum?: number
  sellSum?: number
}

export function getLhbRecent(days = 30, code?: string): Promise<LhbRow[]> {
  return request.get('/lhb/recent', { params: { days, code } })
}

export function getLhbInstitutionRank(days = 30): Promise<LhbAggRow[]> {
  return request.get('/lhb/institution-rank', { params: { days } })
}

export function getLhbStockRank(days = 30): Promise<LhbAggRow[]> {
  return request.get('/lhb/stock-rank', { params: { days } })
}
