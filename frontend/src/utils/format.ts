// Centralized number / percent / date formatters.
// One place so the whole UI stays consistent and a future preference change
// (e.g. locale, decimals) flips everywhere at once.

import dayjs from 'dayjs'

/** Add thousand separators. `null/undefined/NaN` → "—". */
export function formatNumber(v: number | null | undefined, decimals = 0): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return v.toLocaleString('zh-CN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

/** Format as percent. Input is already in percent units (e.g. 12.5 → "12.50%"). */
export function formatPercent(v: number | null | undefined, decimals = 2): string {
  if (v == null || !Number.isFinite(v)) return '—'
  const sign = v > 0 ? '+' : ''
  return `${sign}${v.toFixed(decimals)}%`
}

/**
 * Format an absolute CNY amount according to the chosen unit.
 *  - 'yi'  → 亿元 (1e8 base)
 *  - 'wan' → 万元 (1e4 base)
 *  - 'auto' → switch based on magnitude
 *
 * Returns the numeric part only; suffix is exposed separately so callers can
 * choose to style it differently (e.g. smaller text).
 */
export type AmountUnit = 'yi' | 'wan' | 'auto'

export function formatAmount(
  v: number | null | undefined,
  unit: AmountUnit = 'yi',
  decimals = 2,
): { value: string; suffix: string } {
  if (v == null || !Number.isFinite(v)) return { value: '—', suffix: '' }
  let pick: 'yi' | 'wan' = unit === 'auto'
    ? (Math.abs(v) >= 1e8 ? 'yi' : 'wan')
    : unit
  const base = pick === 'yi' ? 1e8 : 1e4
  const suffix = pick === 'yi' ? '亿' : '万'
  return { value: formatNumber(v / base, decimals), suffix }
}

/** Inline string variant, when you don't need to style the suffix. */
export function formatAmountText(
  v: number | null | undefined,
  unit: AmountUnit = 'yi',
  decimals = 2,
): string {
  const { value, suffix } = formatAmount(v, unit, decimals)
  return suffix ? `${value} ${suffix}` : value
}

/** Standardized YYYY-MM-DD. Handles ISO strings, Date, dayjs, epoch ms. */
export function formatDate(v: string | number | Date | null | undefined): string {
  if (v == null) return '—'
  const d = dayjs(v)
  return d.isValid() ? d.format('YYYY-MM-DD') : '—'
}

/** YYYY-MM-DD HH:mm */
export function formatDateTime(v: string | number | Date | null | undefined): string {
  if (v == null) return '—'
  const d = dayjs(v)
  return d.isValid() ? d.format('YYYY-MM-DD HH:mm') : '—'
}
