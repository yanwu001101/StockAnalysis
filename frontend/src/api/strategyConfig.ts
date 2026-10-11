import request from './request'

export type WeightMap = Record<string, { enabled: boolean; weight: number }>
export interface CloudStrategyConfig {
  version: number
  config: WeightMap | null
  presets: { name: string; config: WeightMap }[]
  updatedAt?: string | null
}
export const getStrategyConfig = (): Promise<CloudStrategyConfig> => request.get('/user/strategy-config')
export const putStrategyConfig = (body: CloudStrategyConfig): Promise<CloudStrategyConfig> => request.put('/user/strategy-config', body)
