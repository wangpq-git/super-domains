import request from './request'

export interface DomainParams {
  platform?: string
  status?: string
  search?: string
  expiry_start?: string
  expiry_end?: string
  page?: number
  page_size?: number
}

export function getDomains(params: DomainParams) {
  return request.get('/domains', { params })
}

export function getDomainStats() {
  return request.get('/domains/stats')
}
