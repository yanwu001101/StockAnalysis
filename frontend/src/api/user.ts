import request from './request'
import type { UserInfo, WatchlistGroup } from '@/types'

export function login(username: string, password: string): Promise<{ token: string; user: UserInfo }> {
  return request.post('/user/login', { username, password })
}

export function register(username: string, password: string, nickname: string): Promise<any> {
  return request.post('/user/register', { username, password, nickname })
}

export function getUserInfo(): Promise<UserInfo> {
  return request.get('/user/info')
}

export function getWatchlists(): Promise<WatchlistGroup[]> {
  return request.get('/user/watchlists')
}

export function addToWatchlist(groupId: number, code: string): Promise<any> {
  return request.post('/user/watchlists/add', { groupId, code })
}

export function removeFromWatchlist(groupId: number, code: string): Promise<any> {
  return request.post('/user/watchlists/remove', { groupId, code })
}

export function createWatchlist(name: string): Promise<WatchlistGroup> {
  return request.post('/user/watchlists/create', { name })
}
