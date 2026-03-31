import request from './request'

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

export function getDnsRecords(domainId: number) {
  return request.get(`/dns/${domainId}/records`)
}

export function syncDnsRecords(domainId: number) {
  return request.post(`/dns/${domainId}/sync`)
}

export function createDnsRecord(domainId: number, data: DnsRecordData) {
  return request.post(`/dns/${domainId}/records`, data)
}

export function updateDnsRecord(recordId: number, data: Partial<DnsRecordData>) {
  return request.put(`/dns/records/${recordId}`, data)
}

export function deleteDnsRecord(recordId: number) {
  return request.delete(`/dns/records/${recordId}`)
}
