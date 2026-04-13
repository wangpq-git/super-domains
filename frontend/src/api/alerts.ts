import request, { cachedGet, invalidateCache } from './request'

export interface AlertSchedule {
  type: string
  days?: number[]
  time?: string
}

export interface AlertRuleData {
  name: string
  rule_type: string
  days_before?: number
  is_enabled?: boolean
  channels: string[]
  recipients: string[]
  apply_to_all?: boolean
  specific_platforms?: string[]
  specific_domains?: number[]
  excluded_platforms?: string[]
  severity?: 'urgent' | 'warning' | 'info'
  schedule?: AlertSchedule
}

export interface AlertRule extends AlertRuleData {
  id: number
  last_triggered_at?: string | null
  created_at: string
}

export interface ExpiringDomain {
  id: number
  domain_name: string
  expiry_date: string
  days_left: number
  status: string
  platform: string | null
  account: string | null
}

export function getAlertRules(force = false) {
  return cachedGet('/alerts/rules', { ttl: 60_000, force })
}

export function createAlertRule(data: AlertRuleData) {
  invalidateCache('/alerts')
  return request.post('/alerts/rules', data)
}

export function updateAlertRule(id: number, data: Partial<AlertRuleData>) {
  invalidateCache('/alerts')
  return request.put(`/alerts/rules/${id}`, data)
}

export function deleteAlertRule(id: number) {
  invalidateCache('/alerts')
  return request.delete(`/alerts/rules/${id}`)
}

export function checkAlerts() {
  invalidateCache('/alerts')
  return request.post('/alerts/check')
}

export function getExpiringDomains(days: number = 30, page = 1, pageSize = 20, force = false) {
  return cachedGet('/alerts/expiring', {
    params: { days, page, page_size: pageSize },
    ttl: 60_000,
    force,
  })
}
