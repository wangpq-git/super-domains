import axios from 'axios'
import type { AxiosRequestConfig, AxiosResponse } from 'axios'
import { ElMessage } from '@/utils/message'
import router from '@/router'

const request = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

type CacheEntry<T = unknown> = {
  expiresAt: number
  data: T
}

type CachedGetOptions = AxiosRequestConfig & {
  ttl?: number
  force?: boolean
}

const memoryCache = new Map<string, CacheEntry>()
const inflightRequests = new Map<string, Promise<AxiosResponse<any>>>()
const CACHE_PREFIX = 'sdm-cache:'

function stableStringify(value: unknown): string {
  if (value === null || typeof value !== 'object') {
    return JSON.stringify(value)
  }

  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(',')}]`
  }

  const entries = Object.entries(value as Record<string, unknown>)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, nestedValue]) => `${JSON.stringify(key)}:${stableStringify(nestedValue)}`)
  return `{${entries.join(',')}}`
}

function buildCacheKey(url: string, config?: AxiosRequestConfig) {
  const params = config?.params ? stableStringify(config.params) : ''
  const base = config?.baseURL || request.defaults.baseURL || ''
  return `${base}:${url}:${params}`
}

function readCache<T>(key: string): CacheEntry<T> | null {
  const memoryEntry = memoryCache.get(key)
  if (memoryEntry && memoryEntry.expiresAt > Date.now()) {
    return memoryEntry as CacheEntry<T>
  }
  memoryCache.delete(key)

  const storageKey = `${CACHE_PREFIX}${key}`
  const raw = sessionStorage.getItem(storageKey)
  if (!raw) return null

  try {
    const parsed = JSON.parse(raw) as CacheEntry<T>
    if (parsed.expiresAt > Date.now()) {
      memoryCache.set(key, parsed)
      return parsed
    }
  } catch {
    // Ignore broken cache payloads and overwrite them on next request.
  }

  sessionStorage.removeItem(storageKey)
  return null
}

function writeCache<T>(key: string, entry: CacheEntry<T>) {
  memoryCache.set(key, entry)
  sessionStorage.setItem(`${CACHE_PREFIX}${key}`, JSON.stringify(entry))
}

export function invalidateCache(prefix = '') {
  for (const key of Array.from(memoryCache.keys())) {
    if (!prefix || key.includes(prefix)) {
      memoryCache.delete(key)
    }
  }

  for (let i = sessionStorage.length - 1; i >= 0; i -= 1) {
    const storageKey = sessionStorage.key(i)
    if (!storageKey?.startsWith(CACHE_PREFIX)) continue
    if (!prefix || storageKey.includes(prefix)) {
      sessionStorage.removeItem(storageKey)
    }
  }
}

export async function cachedGet<T = unknown>(url: string, config: CachedGetOptions = {}) {
  const { ttl = 60_000, force = false, ...requestConfig } = config
  const key = buildCacheKey(url, requestConfig)

  if (!force) {
    const cached = readCache<T>(key)
    if (cached) {
      return {
        data: cached.data,
        status: 200,
        statusText: 'OK',
        headers: {},
        config: requestConfig,
      } as AxiosResponse<T>
    }

    const inflight = inflightRequests.get(key)
    if (inflight) {
      return inflight as Promise<AxiosResponse<T>>
    }
  }

  const pendingRequest = request.get<T>(url, requestConfig).then((response) => {
    writeCache<T>(key, {
      data: response.data,
      expiresAt: Date.now() + ttl,
    })
    return response
  })

  inflightRequests.set(key, pendingRequest as Promise<AxiosResponse<any>>)

  try {
    return await pendingRequest
  } finally {
    inflightRequests.delete(key)
  }
}

request.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

request.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      invalidateCache()
      localStorage.removeItem('token')
      router.push({ name: 'Login' })
      ElMessage.error('登录已过期，请重新登录')
    }
    return Promise.reject(error)
  }
)

export default request
