import request, { cachedGet, invalidateCache } from './request'

export interface DomainParams {
  platform?: string
  status?: string
  search?: string
  expiry_start?: string
  expiry_end?: string
  exclude_expired?: boolean
  dns_manageable_only?: boolean
  sort_by?: string
  sort_order?: string
  page?: number
  page_size?: number
}

export function getDomains(params: DomainParams, force = false) {
  return cachedGet('/domains', { params, force, ttl: 30_000 })
}

export function getDomainStats(force = false) {
  return cachedGet('/domains/stats', { force, ttl: 60_000 })
}

export function onboardDomainToCloudflare(domainId: number) {
  invalidateCache('/domains')
  return request.post(`/domains/${domainId}/onboard-cloudflare`)
}
