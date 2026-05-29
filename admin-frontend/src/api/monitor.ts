import request from './request'
import type { PageResp } from './users'

export interface MonitorOverview {
  jvm: {
    heapUsedMB: number
    heapMaxMB: number
    processors: number
    uptimeMs: number
  }
  dataService: any
}

export interface AccessLogEntry {
  ts: string
  method: string
  uri: string
  query: string | null
  status: number
  elapsedMs: number
  ip: string
}

export interface AuditLogRow {
  id: number
  adminId: number
  adminName: string
  action: string
  target: string
  payloadJson: string | null
  ip: string
  createdAt: string
}

export function getOverview(): Promise<MonitorOverview> {
  return request.get('/admin/monitor/overview')
}

export function getAccessLog(limit = 200): Promise<AccessLogEntry[]> {
  return request.get('/admin/monitor/access-log', { params: { limit } })
}

export function getAuditLog(params: { page?: number; size?: number; action?: string }): Promise<PageResp<AuditLogRow>> {
  return request.get('/admin/monitor/audit-log', { params })
}
