import request from './request'

export interface MainFlowRow {
  code: string
  name: string
  industry: string
  price: number
  changePercent: number
  mainNetSum: number
  superLargeSum: number
  largeSum: number
  days: number
}

export interface NbFlowRow {
  code: string
  name: string
  industry: string
  price: number
  changePercent: number
  sharesDiff: number
  currentShares: number
  currentRatio: number
  firstDate: string
  lastDate: string
}

export interface SectorRow {
  rank: number
  name: string
  avgChange: number
  count: number
  amount: number
}

export interface StockFlowPoint {
  date: string
  superLargeNet: number
  largeNet: number
  mediumNet: number
  smallNet: number
  mainNet: number
}

export function getMainRank(days = 5, limit = 30, direction: 'inflow' | 'outflow' = 'inflow'): Promise<MainFlowRow[]> {
  return request.get('/moneyflow/main-rank', { params: { days, limit, direction } })
}

export function getNorthboundRank(days = 5, limit = 30): Promise<NbFlowRow[]> {
  return request.get('/moneyflow/northbound-rank', { params: { days, limit } })
}

export function getSectorFlow(): Promise<SectorRow[]> {
  return request.get('/moneyflow/sector')
}

export function getStockFlow(code: string, days = 60): Promise<StockFlowPoint[]> {
  return request.get(`/moneyflow/stock/${code}`, { params: { days } })
}
