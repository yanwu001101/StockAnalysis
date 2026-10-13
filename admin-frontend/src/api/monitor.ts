import request from './request'
import type { PageResp } from './users'

export interface MonitorOverview {
  jvm: {
    heapUsedMB: number
    heapMaxMB: number
    processors: number
    uptimeMs: number
  }
  dataService: {
    mysql?: {
      connected?: boolean
      tables?: Record<string, number | null>
      freshness?: Record<string, FreshnessEntry>
      freshnessAnchor?: { date: string | null; source: string; asOf: string; cutoffDate: string; lagCalendarDays: number | null; calendarVerified: boolean; note: string }
      basisRefresh?: { pendingCount: number | null; items: { table: string; code: string; requiredBars: number }[]; scope?: string; note?: string; error?: string }
    }
    redis?: { connected?: boolean; ds_key_count?: number | null; memory_used_bytes?: number | null }
    spot?: { present?: boolean; ttl_seconds?: number | null; rows?: number | null }
  }
}

export interface FreshnessEntry {
  status?: string
  historyCodes?: number | null
  latestDate?: string | null
  anchorDate?: string | null
  anchorSource?: string
  eligibleUniverse?: number | null
  coveredOnAnchor?: number | null
  staleCodes?: number | null
  missingCodes?: number | null
  latestCoveragePct?: number | null
  historyCoveragePct?: number | null
  coverageMode?: string
  universeSource?: string
  fieldCoverageNote?: string
  error?: string
  note?: string
  fieldCoverage?: { field: string; presentCodes: number | null; eligibleCodes: number | null; coveragePct: number | null; scope: 'LATEST_RECORD_PER_CODE' }[]
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
