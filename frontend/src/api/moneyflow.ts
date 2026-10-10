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
  /** 资金流最新交易日(ISO),早于最近交易日即 stale */
  asOf?: string | null
  /** true = 资金流落后于最近交易日,当日数据待盘后更新 */
  stale?: boolean
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
  /** true = 近期窗口内无数据,退回到最后可得窗口(北向 2024-08 起停止逐日披露) */
  stale?: boolean
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

