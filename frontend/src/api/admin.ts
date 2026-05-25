import request from './request'

export interface AdminHealth {
  timestamp: string
  mysql: {
    connected: boolean
    tables?: Record<string, number | null>
    error?: string
  }
  redis: {
    connected: boolean
    ds_key_count?: number
    memory_used_bytes?: number
    error?: string
  }
  spot: {
    present: boolean
    ttl_seconds?: number
    rows?: number
    size_bytes?: number
    error?: string
  }
  circuits: Record<string, string>
}

export interface WarmupRun {
  id: string
  job: string
  status: 'running' | 'success' | 'failed'
  started_at: string
  finished_at?: string | null
  duration_s?: number | null
  error?: string | null
}

export function getAdminHealth(): Promise<AdminHealth> {
  return request.get('/admin/health-detail')
}

export function clearAdminCache(pattern?: string): Promise<{ deleted: number; pattern?: string; error?: string }> {
  return request.post('/admin/cache/clear', null, {
    params: pattern ? { pattern } : undefined,
  })
}

export function startWarmup(job: 'postmarket' | 'weekend' | 'premarket' | 'intraday'): Promise<WarmupRun> {
  return request.post('/admin/warmup', null, { params: { job } })
}

export function getWarmupStatus(id?: string): Promise<WarmupRun | { items: WarmupRun[] }> {
  return request.get('/admin/warmup/status', { params: id ? { id } : undefined })
}
