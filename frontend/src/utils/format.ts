/**
 * Shared formatting utilities for the domain management platform
 */

const BEIJING_TIME_ZONE = 'Asia/Shanghai'

function parseApiDate(value: string | null | undefined): Date | null {
  if (!value) return null
  const trimmed = value.trim()
  if (!trimmed) return null

  if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
    const [year, month, day] = trimmed.split('-').map(Number)
    return new Date(Date.UTC(year, month - 1, day))
  }

  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(trimmed) ? trimmed : `${trimmed}Z`
  const parsed = new Date(normalized)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

function formatInBeijing(
  value: string | null | undefined,
  options: Intl.DateTimeFormatOptions,
): string {
  const parsed = parseApiDate(value)
  if (!parsed) return value || '-'

  const parts = new Intl.DateTimeFormat('zh-CN', {
    timeZone: BEIJING_TIME_ZONE,
    hour12: false,
    ...options,
  }).formatToParts(parsed)

  const map = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  const year = map.year ?? '0000'
  const month = map.month ?? '00'
  const day = map.day ?? '00'
  const hour = map.hour ?? '00'
  const minute = map.minute ?? '00'
  const second = map.second ?? '00'

  if (options.hour === undefined) {
    return `${year}-${month}-${day}`
  }

  return `${year}-${month}-${day} ${hour}:${minute}:${second}`
}

/** Platform key -> display name mapping */
export const PLATFORM_LABELS: Record<string, string> = {
  cloudflare: 'Cloudflare',
  namecom: 'Name.com',
  dynadot: 'Dynadot',
  godaddy: 'GoDaddy',
  namecheap: 'Namecheap',
  namesilo: 'NameSilo',
  openprovider: 'OpenProvider',
  porkbun: 'Porkbun',
  spaceship: 'Spaceship',
}

/** Get display name for a platform key */
export function platformLabel(key: string): string {
  return PLATFORM_LABELS[key] ?? key
}

/** Format ISO datetime string to friendly format: YYYY-MM-DD HH:mm */
export function formatDateTime(isoStr: string | null | undefined): string {
  return formatInBeijing(isoStr, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

/** Format ISO date string to YYYY-MM-DD */
export function formatDate(isoStr: string | null | undefined): string {
  return formatInBeijing(isoStr, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
}

/** Platform tag type mapping for Element Plus */
export function platformTagType(platform: string): '' | 'success' | 'warning' | 'danger' | 'info' {
  const map: Record<string, '' | 'success' | 'warning' | 'danger' | 'info'> = {
    cloudflare: 'warning',
    namecom: 'success',
    dynadot: '',
    godaddy: 'success',
    namecheap: 'danger',
    namesilo: 'info',
    openprovider: 'info',
    porkbun: 'danger',
    spaceship: 'info',
  }
  return map[platform] ?? ''
}
