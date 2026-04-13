import request, { cachedGet, invalidateCache } from './request'

export interface DnsRecordData {
  record_type: string
  name: string
  content: string
  ttl?: number
  priority?: number
  proxied?: boolean
}

export interface DnsRecord extends DnsRecordData {
  id: number
  domain_id: number
  external_id: string | null
  sync_status: string
  created_at: string
  updated_at: string
}

export function getDnsRecords(domainId: number, params?: { sort_by?: string; sort_order?: string }, force = false) {
  return cachedGet(`/dns/${domainId}/records`, { params, ttl: 30_000, force })
}

export function syncDnsRecords(domainId: number) {
  invalidateCache('/dns/')
  return request.post(`/dns/${domainId}/sync`)
}

export function createDnsRecord(domainId: number, data: DnsRecordData) {
  invalidateCache('/dns/')
  return request.post(`/dns/${domainId}/records`, data)
}

export function updateDnsRecord(recordId: number, data: Partial<DnsRecordData>) {
  invalidateCache('/dns/')
  return request.put(`/dns/records/${recordId}`, data)
}

export function deleteDnsRecord(recordId: number) {
  invalidateCache('/dns/')
  return request.delete(`/dns/records/${recordId}`)
}
