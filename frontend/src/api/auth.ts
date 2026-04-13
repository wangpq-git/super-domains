import request, { cachedGet, invalidateCache } from './request'

export function login(username: string, password: string) {
  invalidateCache()
  return request.post('/auth/login', { username, password })
}

export function getMe(force = false) {
  return cachedGet('/auth/me', { ttl: 60_000, force })
}
