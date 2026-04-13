import request, { cachedGet, invalidateCache } from './request'

export function getUsers(force = false) {
  return cachedGet('/users', { ttl: 60_000, force })
}

export function updateUser(id: number, data: any) {
  invalidateCache('/users')
  return request.put(`/users/${id}`, data)
}
