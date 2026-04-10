import request from './request'

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

export function getCosDiscoveryConfig() {
  return request.get<CosDiscoveryConfigResponse>('/cos-discovery/config')
}

export function getCosDomains() {
  return request.get<CosDiscoveryDomainListResponse>('/cos-discovery/domains')
}
