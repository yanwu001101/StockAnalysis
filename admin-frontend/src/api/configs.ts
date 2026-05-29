import request from './request'

export interface AppConfigRow {
  k: string
  v: string
  description: string
  updatedAt: string
  updatedBy?: number
}

export function listConfigs(keyword?: string): Promise<AppConfigRow[]> {
  return request.get('/admin/configs', { params: keyword ? { keyword } : undefined })
}

export function upsertConfig(k: string, v: string, description: string) {
  return request.put(`/admin/configs/${encodeURIComponent(k)}`, { v, description })
}

export function deleteConfig(k: string) {
  return request.delete(`/admin/configs/${encodeURIComponent(k)}`)
}
