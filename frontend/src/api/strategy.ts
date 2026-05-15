import request from './request'
import type { ScreenerRequest, BacktestRequest, BacktestResult, StrategyConfig } from '@/types'

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
