/**
 * Typed API client (the only module that talks HTTP).
 *
 * Rules:
 *  - Base URL comes from VITE_API_BASE_URL (see .env / vite proxy fallback);
 *  - every failure becomes an `ApiError` with the backend's error code, so the
 *    UI maps codes to copy instead of showing raw transport errors;
 *  - 4xx is never retried, 5xx is retried up to 3 times with backoff.
 */
import type {
  AnalyzeRequest,
  AnalyzeResponse,
  ApiErrorBody,
  BacktestOverrides,
  MarketOverview,
  QuantVerdictPayload,
  SystemStats,
  TaskRecord,
} from '@/types/quant'

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'
const MAX_RETRIES = 3
const RETRY_BASE_MS = 400

export class ApiError extends Error {
  readonly code: string
  readonly status: number

  constructor(code: string, message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

const sleep = (ms: number): Promise<void> =>
  new Promise((resolve) => {
    setTimeout(resolve, ms)
  })

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let lastError: ApiError | undefined

  for (let attempt = 0; attempt < MAX_RETRIES; attempt += 1) {
    let response: Response
    try {
      response = await fetch(`${API_BASE}${path}`, {
        ...init,
        headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
      })
    } catch {
      lastError = new ApiError('NETWORK_ERROR', '网络不可达，请检查连接后重试', 0)
      await sleep(RETRY_BASE_MS * 2 ** attempt)
      continue
    }

    if (response.ok) {
      return (await response.json()) as T
    }

    const body = (await response.json().catch(() => null)) as ApiErrorBody | null
    const code = body?.error?.code ?? 'UNKNOWN_ERROR'
    const message = body?.error?.message ?? `请求失败（HTTP ${response.status}）`
    const error = new ApiError(code, message, response.status)

    // 4xx is a client mistake — retrying will not help.
    if (response.status >= 400 && response.status < 500) {
      throw error
    }
    lastError = error
    await sleep(RETRY_BASE_MS * 2 ** attempt)
  }

  throw lastError ?? new ApiError('UNKNOWN_ERROR', '请求失败', 0)
}

export const quantApi = {
  submit(symbol: string, backtest?: BacktestOverrides): Promise<AnalyzeResponse> {
    const body: AnalyzeRequest = backtest ? { symbol, backtest } : { symbol }
    return request<AnalyzeResponse>('/analyze', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },

  getResult(taskId: string): Promise<QuantVerdictPayload> {
    return request<QuantVerdictPayload>(`/result/${encodeURIComponent(taskId)}`)
  },

  getTask(taskId: string): Promise<TaskRecord> {
    return request<TaskRecord>(`/tasks/${encodeURIComponent(taskId)}`)
  },

  getStats(): Promise<SystemStats> {
    return request<SystemStats>('/stats')
  },

  getMarketOverview(): Promise<MarketOverview> {
    return request<MarketOverview>('/market/overview')
  },

  /** WebSocket URL for the progress stream (ws/wss follows the page scheme). */
  progressSocket(taskId: string): string {
    const configured: string = import.meta.env.VITE_WS_BASE_URL ?? '/ws/v1'
    if (/^wss?:\/\//.test(configured)) {
      return `${configured}/progress/${encodeURIComponent(taskId)}`
    }
    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
    return `${scheme}://${window.location.host}${configured}/progress/${encodeURIComponent(taskId)}`
  },
}
