import { describe, expect, it } from 'vitest'

import {
  formatCompact,
  formatDate,
  formatInterval,
  formatK,
  formatMetric,
  formatMs,
  formatNumber,
  formatP,
  formatRate,
  formatValue,
  shortRevision,
} from './format'

describe('formatNumber', () => {
  it('uses fixed decimals and a typographic minus', () => {
    expect(formatNumber(12.345, 1)).toBe('12.3')
    expect(formatNumber(-3.25, 2)).toBe('−3.25')
    expect(formatNumber(0, 1)).toBe('0.0')
  })

  it('does not print a negative zero', () => {
    expect(formatNumber(-0.04, 1)).toBe('0.0')
  })

  it('shows a dash for missing values', () => {
    expect(formatNumber(undefined)).toBe('—')
    expect(formatNumber(null)).toBe('—')
    expect(formatNumber(Number.NaN)).toBe('—')
  })
})

describe('formatCompact', () => {
  it('trims trailing zeros', () => {
    expect(formatCompact(118.2)).toBe('118.2')
    expect(formatCompact(2)).toBe('2')
    expect(formatCompact(0.9167)).toBe('0.92')
    expect(formatCompact(-20.6667)).toBe('−20.67')
  })
})

describe('score formatting', () => {
  it('shows normalised scores on the 0-100 scale', () => {
    expect(formatK(0.4567)).toBe('45.7')
    expect(formatK(null)).toBe('—')
  })

  it('formats intervals with an optional scale', () => {
    expect(formatInterval([0.3, 0.5], 1, 100)).toBe('30.0 to 50.0')
    expect(formatInterval(null)).toBe('—')
  })

  it('formats latency, p-values and rates', () => {
    expect(formatMs(41.6)).toBe('42 ms')
    expect(formatMs(6.25)).toBe('6.3 ms')
    expect(formatMs(1534)).toBe('1.53 s')
    expect(formatP(0.0004)).toBe('<0.001')
    expect(formatP(0.0412)).toBe('0.041')
    expect(formatRate(0.444)).toBe('44%')
  })

  it('formats metrics: means and category counts (largest first)', () => {
    expect(formatMetric(1.3333)).toBe('1.33')
    expect(formatMetric({ win: 1, loss: 5 })).toBe('loss 5 · win 1')
  })

  it('shortens revisions and dates', () => {
    expect(shortRevision('ed3eed331870db2eff4b0db01237128ede8a00ce')).toBe('ed3eed331870')
    expect(shortRevision(null)).toBe('unpinned')
    expect(formatDate('2026-10-08T00:09:35+00:00')).toBe('2026-10-08 00:09 UTC')
  })
})

describe('formatValue', () => {
  it('formats replay metrics of any JSON type', () => {
    expect(formatValue(true)).toBe('yes')
    expect(formatValue(false)).toBe('no')
    expect(formatValue(1.3333)).toBe('1.33')
    expect(formatValue('win-block')).toBe('win-block')
    expect(formatValue(null)).toBe('null')
  })
})
