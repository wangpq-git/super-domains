import request from './request'

export function batchSyncAccounts(accountIds: number[]) {
  return request.post('/batch/sync', { account_ids: accountIds })
}

export function batchUpdateDns(domainIds: number[], records: any[], action: string) {
  return request.post('/batch/dns', { domain_ids: domainIds, records, action })
}

export function batchUpdateNameservers(domainIds: number[], nameservers: string[]) {
  return request.post('/batch/nameservers', { domain_ids: domainIds, nameservers })
}

export function exportDomainsCsv() {
  return request.get('/export/domains', { params: { format: 'csv' }, responseType: 'blob' })
}

export function exportDomainsXlsx() {
  return request.get('/export/domains', { params: { format: 'xlsx' }, responseType: 'blob' })
}
