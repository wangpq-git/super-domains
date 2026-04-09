import request from './request'

export interface SystemSettingItem {
  key: string
  category: string
  label: string
  description?: string | null
  value_type: 'string' | 'boolean' | 'integer' | 'json'
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

export function getSystemSettings() {
  return request.get<SystemSettingListResponse>('/system-settings')
}

export function updateSystemSettings(items: Array<{ key: string; value: any }>) {
  return request.put<SystemSettingListResponse>('/system-settings', { items })
}
