import request from './request'

export interface AdminUserRow {
  id: number
  username: string
  nickname: string
  role: 'ADMIN' | 'USER'
  status: number
  lastLoginAt?: string | null
  mustChangePassword: boolean
  createdAt: string
}

export interface PageResp<T> {
  records: T[]
  total: number
  size: number
  current: number
}

export interface UserStats {
  total: number
  admins: number
  disabled: number
  todayNew: number
}

export function listUsers(params: {
  page?: number
  size?: number
  keyword?: string
  role?: string
  status?: number
}): Promise<PageResp<AdminUserRow>> {
  return request.get('/admin/users', { params })
}

export function getUserStats(): Promise<UserStats> {
  return request.get('/admin/users/stats')
}

export function toggleUserStatus(id: number): Promise<{ id: number; status: number }> {
  return request.post(`/admin/users/${id}/toggle-status`)
}

export function setUserRole(id: number, role: 'ADMIN' | 'USER') {
  return request.post(`/admin/users/${id}/role`, { role })
}

export function resetUserPassword(id: number): Promise<{ id: number; username: string; tempPassword: string }> {
  return request.post(`/admin/users/${id}/reset-password`)
}

export function deleteUser(id: number) {
  return request.delete(`/admin/users/${id}`)
}
