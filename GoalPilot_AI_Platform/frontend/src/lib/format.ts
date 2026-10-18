/** Shared formatting helpers. Every money value in the UI goes through formatMoney. */

export function formatMoney(
  value: number | null | undefined,
  currency = 'INR',
  locale = 'en-IN',
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '--'
  try {
    return new Intl.NumberFormat(locale, {
      style: 'currency',
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value)
  } catch {
    return `${currency} ${formatNumber(value, locale)}`
  }
}

export function formatNumber(value: number | null | undefined, locale = 'en-IN'): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '--'
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

export function formatMoneyCompact(
  value: number | null | undefined,
  currency = 'INR',
  locale = 'en-IN',
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '--'
  try {
    return new Intl.NumberFormat(locale, {
      style: 'currency',
      currency,
      notation: 'compact',
      maximumFractionDigits: 1,
    }).format(value)
  } catch {
    return formatMoney(value, currency, locale)
  }
}

/**
 * Optimiser scores are not money and must not be rendered with the 2-decimal money format:
 * an objective of 6.7161 was displayed as "6.72", which reads as ₹6.72. Scores keep up to
 * four decimals, which is enough to see a change without implying currency precision.
 */
export function formatScore(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '--'
  if (value === 0) return '0'
  const digits = Math.abs(value) >= 1 ? 4 : 6
  return new Intl.NumberFormat('en-IN', {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  }).format(value)
}

/** Ratios arrive as 0..1 fractions; percentages are shown to one decimal place. */
export function formatPct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '--'
  return `${(value * 100).toFixed(digits)}%`
}

/** Values already expressed as a percentage number (e.g. pct_error). */
export function formatPctRaw(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '--'
  return `${value.toFixed(digits)}%`
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '--'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: '2-digit' })
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '--'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function humanise(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (character) => character.toUpperCase())
}

export function currentPeriod(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

export function prettyJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

/** Render any scalar as readable text. Used for dynamic API dictionaries. */
export function valueText(value: unknown): string {
  if (value === null || value === undefined) return '--'
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : formatNumber(value)
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map((item) => valueText(item)).join(', ')
  return prettyJson(value)
}
