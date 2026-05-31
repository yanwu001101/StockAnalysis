import request from './request'
import type { ScreenerRequest, BacktestRequest, BacktestResult, StrategyConfig, SavedBacktestSummary } from '@/types'

export function getStrategies(): Promise<StrategyConfig[]> {
  return request.get('/strategies')
}

export function getStrategyTop(strategyName: string, limit: number = 20): Promise<any[]> {
  return request.get(`/strategies/${strategyName}/top`, { params: { limit } })
}

export function compareStrategies(codes: string[]): Promise<any> {
  return request.get('/strategies/compare', { params: { codes: codes.join(',') } })
}

export function runScreener(req: ScreenerRequest): Promise<any[]> {
  return request.post('/screen', req)
}

export function runBacktest(req: BacktestRequest): Promise<BacktestResult> {
  return request.post('/backtest', req)
}

// ---- 保存的回测(账号云端,需登录) ----

export function saveBacktest(payload: {
  name: string
  request: any
  result: BacktestResult
}): Promise<{ id: number }> {
  return request.post('/user/backtests', payload)
}

export function listSavedBacktests(): Promise<SavedBacktestSummary[]> {
  return request.get('/user/backtests')
}

export function getSavedBacktest(id: number): Promise<{
  id: number
  name: string
  createdAt: string
  result: BacktestResult
  request: any
}> {
  return request.get(`/user/backtests/${id}`)
}

export function deleteSavedBacktest(id: number): Promise<any> {
  return request.delete(`/user/backtests/${id}`)
}

export interface StrategyTopsRow {
  code: string
  name: string
  industry: string
  price: number
  changePercent: number
  score: number
  signal: string
  triggered: boolean
}

export interface StrategyTops {
  strategies: Array<{ id: string; name: string; rows: StrategyTopsRow[] }>
  computed_at: string | null
  row_count: number
}

export function getStrategyTops(limit: number = 10): Promise<StrategyTops> {
  return request.get('/strategy-tops', { params: { limit } })
}
