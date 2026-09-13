import request from './request'
import type { PaperOrders, PaperOverview } from '@/types'

export function getPaper(): Promise<PaperOverview> {
  return request.get('/paper')
}

export function getPaperOrders(date?: string): Promise<PaperOrders> {
  return request.get('/paper/orders', { params: date ? { date } : undefined })
}

export function resetPaper(body: { initialCapital: number; topN: number }): Promise<any> {
  return request.post('/paper/reset', body)
}

export function runPaper(): Promise<any> {
  return request.post('/paper/run', {})
}
