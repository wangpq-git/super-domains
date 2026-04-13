import request, { cachedGet, invalidateCache } from './request'

export interface SystemSettingItem {
  key: string
  category: string
  label: string
  description?: string | null
  value_type: 'string' | 'boolean' | 'integer' | 'json'
  ui_type?: 'input' | 'textarea'
  rows?: number | null
  is_secret: boolean
  restart_required: boolean
  value: any
  masked_value?: string | null
  is_configured: boolean
  source: 'database' | 'environment' | 'default'
}

export interface SystemSettingListResponse {
  items: SystemSettingItem[]
}

export function getSystemSettings(force = false) {
  return cachedGet<SystemSettingListResponse>('/system-settings', { ttl: 60_000, force })
}

export function updateSystemSettings(items: Array<{ key: string; value: any }>) {
  invalidateCache('/system-settings')
  return request.put<SystemSettingListResponse>('/system-settings', { items })
}
