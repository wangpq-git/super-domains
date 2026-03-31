import request from './request'

export function getOverviewStats() {
  return request.get('/reports/overview')
}

export function getExpiryReport(days: number = 90) {
  return request.get('/reports/expiry', { params: { days } })
}

export function getPlatformReport() {
  return request.get('/reports/platforms')
}

export function getAuditLogs(params: any = {}) {
  return request.get('/reports/audit', { params })
}
