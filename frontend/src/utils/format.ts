/**
 * Shared formatting utilities for the domain management platform
 */

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
  if (!isoStr) return '-'
  const d = new Date(isoStr)
  if (isNaN(d.getTime())) return isoStr
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** Format ISO date string to YYYY-MM-DD */
export function formatDate(isoStr: string | null | undefined): string {
  if (!isoStr) return '-'
  const d = new Date(isoStr)
  if (isNaN(d.getTime())) return isoStr
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
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
