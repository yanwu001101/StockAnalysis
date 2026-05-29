import request from './request'

export interface AdminUserInfo {
  id: number
  username: string
  nickname: string
  role: 'ADMIN' | 'USER'
  mustChangePassword?: boolean
}

export interface LoginResponse {
  token: string
  user: AdminUserInfo
}

export function login(username: string, password: string): Promise<LoginResponse> {
  return request.post('/user/login', { username, password })
}

export function getMyInfo(): Promise<AdminUserInfo> {
  return request.get('/user/info')
}
