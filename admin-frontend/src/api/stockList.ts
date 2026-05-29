import request from './request'

export interface StockListRow {
  id: number
  listType: 'whitelist' | 'blacklist' | 'pool'
  code: string
  note: string
  createdAt: string
  createdBy?: number
}

export function listStockList(type?: string): Promise<StockListRow[]> {
  return request.get('/admin/stock-list', { params: type ? { type } : undefined })
}

export function addStockList(payload: { listType: string; code: string; note?: string }) {
  return request.post('/admin/stock-list', payload)
}

export function removeStockList(id: number) {
  return request.delete(`/admin/stock-list/${id}`)
}
