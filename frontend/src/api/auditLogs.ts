import { cachedGet } from './request'

export interface AuditLogItem {
  id: number
  user_id: number | null
  actor_name: string | null
  action: string
  target_type: string | null
  target_id: number | null
  domain_name: string | null
  detail: Record<string, any>
  ip_address: string | null
  created_at: string
}

export interface AuditLogListResponse {
  items: AuditLogItem[]
  total: number
  page: number
  page_size: number
}

export interface AuditLogQuery {
  page?: number
  page_size?: number
  keyword?: string
  action?: string
  target_type?: string
  scope?: 'all' | 'operation' | 'domain'
}

export function getAuditLogs(params: AuditLogQuery, force = false) {
  return cachedGet<AuditLogListResponse>('/audit-logs', {
    params,
    force,
    ttl: 15_000,
  })
}
