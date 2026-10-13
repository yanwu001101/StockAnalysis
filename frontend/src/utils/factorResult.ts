import type { FactorLabResult } from '@/types'

export const isFiniteNumber = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value)

export function percent(value: number | null | undefined, digits = 2, signed = true): string {
  if (!isFiniteNumber(value)) return '—'
  return `${signed && value > 0 ? '+' : ''}${(value * 100).toFixed(digits)}%`
}

export function metric(value: number | null | undefined, digits = 4): string {
  return value == null || !Number.isFinite(value) ? '—' : value.toFixed(digits)
}

export function factorStatus(result: Partial<FactorLabResult> | null | undefined) {
  const code = result?.status ?? result?.rating?.status_code
  if (code === 'FAILED' || result?.error_kind === 'compute' || result?.error_kind === 'expression')
    return { text: '计算失败', cls: 'st-compute', emoji: '' }
  if (code === 'INSUFFICIENT_DATA' || result?.error_kind === 'coverage')
    return { text: '样本不足', cls: 'st-coverage', emoji: '' }
  if (code === 'VALID') return { text: '有效', cls: 'st-good', emoji: '' }
  if (code === 'CANDIDATE') return { text: '候选', cls: 'st-candidate', emoji: '' }
  return { text: '不显著', cls: 'st-insig', emoji: '' }
}
