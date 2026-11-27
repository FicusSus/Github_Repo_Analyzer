const integer = new Intl.NumberFormat('en-US')
const compact = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 })
const decimal = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 })
const dateFormat = new Intl.DateTimeFormat('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
const dateTimeFormat = new Intl.DateTimeFormat('en-US', {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})
const shortDate = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' })
const monthYear = new Intl.DateTimeFormat('en-US', { month: 'short', year: 'numeric', timeZone: 'UTC' })
const relative = new Intl.RelativeTimeFormat('en-US', { numeric: 'auto' })

export const DASH = '—'

export function formatInteger(value: number | null | undefined): string {
  return value === null || value === undefined ? DASH : integer.format(value)
}

export function formatCompact(value: number | null | undefined): string {
  if (value === null || value === undefined) return DASH
  return Math.abs(value) < 10_000 ? integer.format(value) : compact.format(value)
}

export function formatDecimal(value: number | null | undefined): string {
  return value === null || value === undefined ? DASH : decimal.format(value)
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return DASH
  const smallest = 10 ** -digits
  if (value > 0 && value < smallest) return `<${smallest.toFixed(digits)}%`
  return `${value.toFixed(digits)}%`
}

export function formatSignedPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return DASH
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(1)}%`
}

export function formatSigned(value: number | null | undefined): string {
  if (value === null || value === undefined) return DASH
  const sign = value > 0 ? '+' : ''
  return `${sign}${decimal.format(value)}`
}

export function formatDate(value: string | null | undefined): string {
  return value ? dateFormat.format(new Date(value)) : DASH
}

export function formatDateTime(value: string | null | undefined): string {
  return value ? dateTimeFormat.format(new Date(value)) : DASH
}

/** Formats a backend `YYYY-MM-DD` bucket date without shifting it into the local time zone. */
export function formatBucketDay(isoDate: string): string {
  return shortDate.format(new Date(`${isoDate}T00:00:00Z`))
}

export function formatBucketMonth(isoDate: string): string {
  return monthYear.format(new Date(`${isoDate}T00:00:00Z`))
}

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 365 * 24 * 3600],
  ['month', 30 * 24 * 3600],
  ['week', 7 * 24 * 3600],
  ['day', 24 * 3600],
  ['hour', 3600],
  ['minute', 60],
]

export function formatRelative(value: string | null | undefined, now: Date = new Date()): string {
  if (!value) return DASH
  const seconds = (new Date(value).getTime() - now.getTime()) / 1000
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit)
  }
  return 'just now'
}

export function formatDaysAgo(days: number | null | undefined): string {
  if (days === null || days === undefined) return DASH
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  return `${integer.format(days)} days ago`
}

export function shortSha(sha: string): string {
  return sha.slice(0, 7)
}
