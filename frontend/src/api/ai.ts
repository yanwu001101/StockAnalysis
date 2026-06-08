import request from './request'

export interface AiConfigInput {
  provider: string
  baseUrl: string
  model: string
  apiKey?: string
  temperature: number
  enabled: boolean
}

export function getAiPresets(): Promise<{ items: any[] }> {
  return request.get('/ai/presets')
}

export function getAiConfig(): Promise<any> {
  return request.get('/ai/config')
}

export function saveAiConfig(body: AiConfigInput): Promise<any> {
  return request.post('/ai/config', body)
}

export function testAiConfig(): Promise<any> {
  return request.post('/ai/test')
}

export function analyzePortfolio(body: { cash: number; question: string }): Promise<any> {
  return request.post('/ai/analyze/portfolio', body)
}

export function getAiHistory(): Promise<any[]> {
  return request.get('/ai/history')
}

export function saveAiFeedback(id: number, feedback: string, note: string): Promise<any> {
  return request.post(`/ai/history/${id}/feedback`, { feedback, note })
}
