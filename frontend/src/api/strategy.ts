import request from './request'
import type { ScreenerRequest, BacktestRequest, BacktestResult, FactorLabResult, StrategyConfig, SavedBacktestSummary } from '@/types'

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



// ---- 异步研究任务（回测/因子检验后台化：提交 + 轮询，不再吊死 HTTP 请求） ----

export type ResearchJobKind = 'backtest' | 'alphalab-backtest' | 'factorlab' | 'alphalab-factorlab'

export interface ResearchJobState {
  id: string
  kind: ResearchJobKind
  status: 'QUEUED' | 'RUNNING' | 'DONE' | 'FAILED'
  result: unknown
  error: string | null
  elapsed_s: number
}

export function submitResearchJob(kind: ResearchJobKind, body: unknown): Promise<{ job_id: string; status: string }> {
  return request.post(`/async/${kind}`, body)
}

export function getResearchJob(jobId: string): Promise<ResearchJobState> {
  return request.get(`/async/jobs/${jobId}`)
}
