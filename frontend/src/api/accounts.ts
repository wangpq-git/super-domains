import request from './request'

export interface AccountData {
  platform: string
  account_name: string
  credentials: Record<string, string>
  config?: Record<string, any>
}

export function getAccounts() {
  return request.get('/platforms')
}

export function createAccount(data: any) {
  return request.post('/platforms', data)
}

export function updateAccount(id: number, data: any) {
  return request.put(`/platforms/${id}`, data)
}

export function deleteAccount(id: number) {
  return request.delete(`/platforms/${id}`)
}

export function testAccount(id: number) {
  return request.post(`/platforms/${id}/test`)
}

export function syncAccount(id: number) {
  return request.post(`/platforms/${id}/sync`)
}

export function syncAllAccounts() {
  return request.post('/platforms/sync-all')
}
