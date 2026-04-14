import request, { cachedGet, invalidateCache } from './request'

export interface AccountData {
  platform: string
  account_name: string
  credentials: Record<string, string>
  config?: Record<string, any>
}

function invalidateAccountRelatedCache() {
  invalidateCache('/platforms')
  invalidateCache('/domains')
  invalidateCache('/reports')
  invalidateCache('/alerts/expiring')
}

export function getAccounts(
  params?: { sort_by?: string; sort_order?: string; page?: number; page_size?: number; platform?: string },
  force = false,
) {
  return cachedGet('/platforms', { params, force, ttl: 30_000 })
}

export function createAccount(data: any) {
  invalidateAccountRelatedCache()
  return request.post('/platforms', data)
}

export function updateAccount(id: number, data: any) {
  invalidateAccountRelatedCache()
  return request.put(`/platforms/${id}`, data)
}

export function deleteAccount(id: number) {
  invalidateAccountRelatedCache()
  return request.delete(`/platforms/${id}`)
}

export function testAccount(id: number) {
  return request.post(`/platforms/${id}/test`)
}

export function syncAccount(id: number) {
  invalidateAccountRelatedCache()
  return request.post(`/platforms/${id}/sync`)
}

export function syncAllAccounts() {
  invalidateAccountRelatedCache()
  return request.post('/platforms/sync-all', null, { timeout: 300000 })
}
