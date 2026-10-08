import type { Interval, MetricValue } from './types'

const MINUS = '−'
const DASH = '—'

/** Fixed decimals with a typographic minus; '—' for missing values. */
export function formatNumber(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return DASH
  const fixed = Math.abs(value).toFixed(digits)
  const isZero = Number(fixed) === 0
  return value < 0 && !isZero ? `${MINUS}${fixed}` : fixed
}

/** Up to `digits` decimals with trailing zeros removed ("2", "0.92", "118.2"). */
export function formatCompact(value: number | null | undefined, digits = 2): string {
  const fixed = formatNumber(value, digits)
  if (fixed === DASH || !fixed.includes('.')) return fixed
  return fixed.replace(/\.?0+$/, '')
}

export function formatInterval(interval: Interval | null | undefined, digits = 1, scale = 1): string {
  if (!interval) return DASH
  return `${formatNumber(interval[0] * scale, digits)} to ${formatNumber(interval[1] * scale, digits)}`
}

/** A normalised score k in [0, 1] shown on the 0-100 scale. */
export function formatK(k: number | null | undefined): string {
  return k === null || k === undefined ? DASH : formatNumber(k * 100, 1)
}

export function formatMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return DASH
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)} s`
  return `${ms.toFixed(ms < 10 ? 1 : 0)} ms`
}

export function formatP(p: number | null | undefined): string {
  if (p === null || p === undefined || !Number.isFinite(p)) return DASH
  return p < 0.001 ? '<0.001' : p.toFixed(3)
}

export function formatRate(rate: number | null | undefined): string {
  if (rate === null || rate === undefined || !Number.isFinite(rate)) return DASH
  return `${(rate * 100).toFixed(0)}%`
}

export function shortRevision(revision: string | null | undefined): string {
  return revision ? revision.slice(0, 12) : 'unpinned'
}

export function metricLabel(name: string): string {
  return name.replaceAll('_', ' ')
}

/** "0.33" for a mean, "win 5 · draw 1" for counts. */
export function formatMetric(value: MetricValue): string {
  if (typeof value === 'number') return formatCompact(value, 2)
  return Object.entries(value)
    .sort(([, a], [, b]) => b - a)
    .map(([label, count]) => `${label} ${count}`)
    .join(' · ')
}

/** A replay metric of any JSON type: numbers compact, booleans as yes/no. */
export function formatValue(value: unknown): string {
  if (typeof value === 'number') return formatCompact(value, 2)
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  if (typeof value === 'string') return value
  return JSON.stringify(value)
}

export function formatDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toISOString().slice(0, 16).replace('T', ' ') + ' UTC'
}
