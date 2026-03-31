import request from './request'

export interface AccountData {
  platform: string
  name: string
  api_key: string
  api_secret?: string
}

export function getAccounts() {
  return request.get('/platforms')
}

export function createAccount(data: AccountData) {
  return request.post('/platforms', data)
}

export function updateAccount(id: number, data: Partial<AccountData>) {
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
