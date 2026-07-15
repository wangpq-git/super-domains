import { cachedGet, invalidateCache } from './request'

export interface CosDiscoveryConfigResponse {
  configured: boolean
}

export interface CosDiscoveryDomainItem {
  bucket_name: string
  custom_domain: string
  origin_type: string
  cname: string
}

export interface CosDiscoveryDomainListResponse {
  items: CosDiscoveryDomainItem[]
  skipped_bucket_count: number
}

export function getCosDiscoveryConfig(force = false) {
  return cachedGet<CosDiscoveryConfigResponse>('/cos-discovery/config', { force, ttl: 300_000 })
}

export function getCosDomains(force = false) {
  return cachedGet<CosDiscoveryDomainListResponse>('/cos-discovery/domains', {
    force,
    ttl: 60_000,
    params: force ? { refresh: true } : undefined,
  })
}

export function invalidateCosDiscoveryCache() {
  invalidateCache('/cos-discovery')
}
