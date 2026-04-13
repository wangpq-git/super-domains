import { cachedGet } from './request'

export function getOverviewStats(force = false) {
  return cachedGet('/reports/overview', { ttl: 60_000, force })
}

export function getExpiryReport(days: number = 90, force = false) {
  return cachedGet('/reports/expiry', { params: { days }, ttl: 60_000, force })
}

export function getPlatformReport(force = false) {
  return cachedGet('/reports/platforms', { ttl: 60_000, force })
}

export function getAuditLogs(params: any = {}, force = false) {
  return cachedGet('/reports/audit', { params, ttl: 30_000, force })
}
