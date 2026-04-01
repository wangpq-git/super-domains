import request from './request'

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
}

export interface AlertRule extends AlertRuleData {
  id: number
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

export function getAlertRules() {
  return request.get('/alerts/rules')
}

export function createAlertRule(data: AlertRuleData) {
  return request.post('/alerts/rules', data)
}

export function updateAlertRule(id: number, data: Partial<AlertRuleData>) {
  return request.put(`/alerts/rules/${id}`, data)
}

export function deleteAlertRule(id: number) {
  return request.delete(`/alerts/rules/${id}`)
}

export function checkAlerts() {
  return request.post('/alerts/check')
}

export function getExpiringDomains(days: number = 30, page = 1, pageSize = 20) {
  return request.get('/alerts/expiring', { params: { days, page, page_size: pageSize } })
}
