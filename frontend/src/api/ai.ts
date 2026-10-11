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

// ---- AI 多轮对话（专业金融顾问） ----

export interface ChatSessionItem {
  id: number
  title: string
  updatedAt: string
}

export interface ChatMessageItem {
  role: 'user' | 'assistant'
  content: string
  createdAt: string
}

export interface ChatReply {
  sessionId: number
  title: string
  reply: string
  model: string
}

/** 发送一条消息；sessionId 为空 = 新建会话。 */
export function chatAi(sessionId: number | null, message: string): Promise<ChatReply> {
  return request.post('/ai/chat', { sessionId, message })
}

export function getChatSessions(): Promise<ChatSessionItem[]> {
  return request.get('/ai/chat/sessions')
}

export function getChatMessages(sessionId: number): Promise<ChatMessageItem[]> {
  return request.get(`/ai/chat/sessions/${sessionId}/messages`)
}

export function deleteChatSession(sessionId: number): Promise<{ deleted: boolean }> {
  return request.delete(`/ai/chat/sessions/${sessionId}`)
}
