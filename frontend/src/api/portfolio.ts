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
  /** 今日买入股数:服务端累加持仓并按 A 股 T+1 锁定,当日不生成卖出信号 */
  todayBought?: number
  buyPrice?: number
  /** 编辑表单里 shares 已是总股数(含今日买入)时为 true;"记录买入"快捷路径不传 */
  sharesIsTotal?: boolean
  lastBuyDate?: string
  lockedShares?: number
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
