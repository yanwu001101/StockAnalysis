import request from './request'

export interface PortfolioPositionInput {
  id?: number
  code: string
  name?: string
  shares: number
  availableShares?: number
  avgCost: number
  targetWeight?: number
  notes?: string
}

export function getPortfolioPositions(): Promise<any[]> {
  return request.get('/portfolio/positions')
}

export function savePortfolioPosition(body: PortfolioPositionInput): Promise<any> {
  return request.post('/portfolio/positions', body)
}

export function importPortfolioText(body: { text: string; targetWeight?: number; source?: string }): Promise<any> {
  return request.post('/portfolio/import-text', body)
}

export function deletePortfolioPosition(id: number): Promise<any> {
  return request.delete(`/portfolio/positions/${id}`)
}

export function getPortfolioAdvice(cash = 0, mode = 'balanced', strategyConfig?: Record<string, { enabled: boolean; weight: number }>): Promise<any> {
  return request.post('/portfolio/advice', { cash, mode, strategyConfig })
}

export function getThsSyncStatus(): Promise<any> {
  return request.get('/portfolio/sync/ths/status')
}
