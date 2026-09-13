import request from './request'
import type { ScreenerRequest, BacktestRequest, BacktestResult, FactorLabResult, StrategyConfig, SavedBacktestSummary } from '@/types'

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

export interface FactorLabRequest {
  strategyId: string
  startDate: string
  endDate: string
  rebalance?: string
  layers?: number
  maxCodes?: number
}

export function runFactorLab(req: FactorLabRequest): Promise<FactorLabResult> {
  return request.post('/factorlab', req)
}

// ---- Alpha Lab:自定义因子（WorldQuant 式截面表达式） ----

export interface AlphaFieldGroup {
  category: string
  items: { name: string; desc: string }[]
}

export interface AlphaExample {
  name: string
  expr: string
  desc: string
}

export interface AlphaHelp {
  fields: AlphaFieldGroup[]
  examples: AlphaExample[]
  notes: string[]
}

export interface AlphaFactorLabRequest {
  expression: string
  startDate: string
  endDate: string
  rebalance?: string
  layers?: number
  maxCodes?: number
  neutralize?: boolean
}

export function runAlphaFactorLab(req: AlphaFactorLabRequest): Promise<FactorLabResult> {
  return request.post('/alphalab/factorlab', req)
}

export interface AlphaBacktestRequest {
  expression: string
  startDate: string
  endDate: string
  initialCapital?: number
  topN?: number
  rebalance?: string
  costs?: Record<string, number>
}

export function runAlphaBacktest(req: AlphaBacktestRequest): Promise<BacktestResult> {
  return request.post('/alphalab/backtest', req)
}

export function getAlphaHelp(): Promise<AlphaHelp> {
  return request.get('/alphalab/help')
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
