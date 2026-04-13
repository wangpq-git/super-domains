import { cachedGet, invalidateCache } from './request'

export interface ServiceDiscoveryNamespaceOption {
  label: string
  namespace: string
}

export interface ServiceDiscoveryConfigResponse {
  configured: boolean
  namespace_options: ServiceDiscoveryNamespaceOption[]
}

export interface ServiceDiscoveryIngressItem {
  name: string
  namespace: string
  hosts: string[]
  ingress_class_name?: string | null
  load_balancers: string[]
  tls_hosts: string[]
}

export interface ServiceDiscoveryIngressListResponse {
  namespace: string
  items: ServiceDiscoveryIngressItem[]
}

export function getServiceDiscoveryConfig(force = false) {
  return cachedGet<ServiceDiscoveryConfigResponse>('/service-discovery/config', { force, ttl: 300_000 })
}

export function getServiceIngresses(namespace?: string, force = false) {
  return cachedGet<ServiceDiscoveryIngressListResponse>('/service-discovery/ingresses', {
    params: namespace ? { namespace } : {},
    force,
    ttl: 60_000,
  })
}

export function invalidateServiceDiscoveryCache() {
  invalidateCache('/service-discovery')
}
