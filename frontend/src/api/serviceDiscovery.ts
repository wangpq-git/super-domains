import request from './request'

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

export function getServiceDiscoveryConfig() {
  return request.get<ServiceDiscoveryConfigResponse>('/service-discovery/config')
}

export function getServiceIngresses(namespace?: string) {
  return request.get<ServiceDiscoveryIngressListResponse>('/service-discovery/ingresses', {
    params: namespace ? { namespace } : {},
  })
}
