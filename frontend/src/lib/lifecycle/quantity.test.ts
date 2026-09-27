import { describe, expect, it } from 'vitest'
import type { QuantityDTO } from '../api/lifecycle'
import { ageWords, durationMargin, formatValue, quantityText, quantityView, shareView } from './quantity'

const q = (over: Partial<QuantityDTO>): QuantityDTO => ({
  value: 12,
  unit: 'h',
  provenance: 'computed',
  pm: null,
  lo: null,
  hi: null,
  factor: null,
  open: false,
  no_margin_reason: null,
  missing_reason: null,
  source: null,
  ...over,
})

describe('quantityView: every margin form draws one way', () => {
  it('a wait in minutes reads in seconds under a minute and in hours from two hours', () => {
    expect(quantityText(q({ unit: 'min', value: 0.0208, pm: null }))).toBe('1.2 s')
    expect(quantityText(q({ unit: 'min', value: 45, pm: null }))).toBe('45 min')
    expect(quantityText(q({ unit: 'min', value: 17166.5, pm: null }))).toBe('286 h')
  })

  it('± : the value to the margin’s own precision, the margin beside it', () => {
    const v = quantityView(q({ value: 183.64, pm: 0.1 }))
    expect(v).toMatchObject({ kind: 'number', figure: '183.6', margin: '±0.1', unit: 'h' })
    expect(v.spoken).toBe('about 183.6 hours, plus or minus 0.1 hours')
    expect(quantityText(q({ value: 183.64, pm: 0.1 }))).toBe('183.6 ±0.1 h')
  })

  it('± between 1 and 3 keeps a decimal, so rounding does not move the value by most of its margin', () => {
    expect(quantityText(q({ value: 9.5, unit: 'm/s', pm: 2.1 }))).toBe('9.5 ±2.1 m/s')
    expect(quantityText(q({ value: 240, pm: 6 }))).toBe('240 ±6 h')
    expect(quantityText(q({ value: 1.2, pm: 0.02 }))).toBe('1.20 ±0.02 h')
  })

  it('a range: "12–31 h", said as "12 to 31 hours", even with no single value', () => {
    const v = quantityView(q({ value: null, lo: 12, hi: 31 }))
    expect(v).toMatchObject({ kind: 'range', figure: '12–31', lo: 12, hi: 31 })
    expect(v.spoken).toBe('12 to 31 hours')
    expect(v.missingReason).toBeUndefined()
  })

  it('a factor: ×/÷, and powers of ten written as a person writes them', () => {
    const v = quantityView(q({ value: 4.1e9, unit: 'cm^-2', factor: 2 }))
    expect(v.figure).toBe('4.1 × 10⁹')
    expect(v.margin).toBe('×/÷2')
    expect(v.spoken).toMatch(/good to a factor of 2$/)
    expect(quantityText(q({ value: 4.1e9, unit: 'cm^-2', factor: 2 }))).toBe('4.1 × 10⁹ ×/÷2 per cm²')
  })

  it('a lower bound the dates cut short: "≥", said as "at least"', () => {
    const v = quantityView(q({ value: 288, pm: 6, open: true }))
    expect(v.figure).toBe('≥288')
    expect(v.spoken).toMatch(/^at least 288 hours/)
  })

  it('no margin: the number, and the reason it has none', () => {
    const v = quantityView(q({ value: 2, unit: 'deg', no_margin_reason: 'A rule the team set, not a measurement.' }))
    expect(v.margin).toBeUndefined()
    expect(v.noMarginReason).toBe('A rule the team set, not a measurement.')
    expect(quantityText(q({ value: 2, unit: 'deg', no_margin_reason: 'x' }))).toBe('2°')
  })

  it('a unit written against the number carries into its margin: "4.1° ±0.3°"', () => {
    expect(quantityText(q({ value: 4.1, unit: 'deg', pm: 0.3 }))).toBe('4.1° ±0.3°')
  })

  it('missing: a dash and the reason, never a zero', () => {
    const v = quantityView(q({ value: null, missing_reason: 'No trajectory yet' }))
    expect(v).toMatchObject({ kind: 'missing', figure: '—', missingReason: 'No trajectory yet' })
    expect(v.spoken).toBe('Not available: No trajectory yet')
    expect(quantityText(q({ value: null, missing_reason: 'x' }))).toBe('not available')
  })

  it('a time known to the minute: the clock time, the date above it, the margin in minutes', () => {
    const t = Date.UTC(2025, 1, 27, 1, 6) / 1000
    const v = quantityView(q({ value: t, unit: 's since epoch', pm: 240 }))
    expect(v).toMatchObject({ kind: 'time', figure: '01:06', figureAbove: '27 Feb 2025 · UTC', margin: '±4 min' })
    expect(v.sentence).toBe('27 Feb 2025, 01:06 UTC ±4 min')
    expect(v.spoken).toBe('27 February 2025, 01:06 UTC, plus or minus 4 minutes')
  })

  it('a date known to a few days: the day as the figure, the year above it', () => {
    const t = Date.UTC(2026, 9, 8) / 1000
    const v = quantityView(q({ value: t, unit: 's since epoch', pm: 3 * 86400 }))
    expect(v).toMatchObject({ figure: '8 Oct', figureAbove: '2026', margin: '±3 days' })
  })

  it('a date known only to months: the span of months, never a made-up day', () => {
    const t = Date.UTC(2026, 6, 2) / 1000
    const v = quantityView(q({ value: t, unit: 's since epoch', pm: 180 * 86400 }))
    expect(v).toMatchObject({ figure: 'Jan–Dec', figureAbove: '2026' })
    expect(v.margin).toBeUndefined()
    expect(v.sentence).toBe('between January 2026 and December 2026')
  })

  it('who a number comes from travels with it (invariant 10)', () => {
    expect(quantityView(q({ provenance: 'entered', source: 'A. Rahman', pm: 1 }))).toMatchObject({
      provenance: 'entered',
      source: 'A. Rahman',
    })
  })
})

describe('formatting helpers', () => {
  it('formatValue: at most three figures, thousands grouped', () => {
    expect(formatValue(38400)).toBe('38,400')
    expect(formatValue(13.4)).toBe('13.4')
    expect(formatValue(0.3)).toBe('0.3')
    expect(formatValue(174.8)).toBe('175')
  })

  it('durationMargin: seconds, minutes, hours or days, whichever reads best', () => {
    expect(durationMargin(30)).toBe('±30 s')
    expect(durationMargin(60)).toBe('±1 min')
    expect(durationMargin(3 * 3600)).toBe('±3.0 h')
    expect(durationMargin(3 * 86400)).toBe('±3 days')
  })

  it('a share states its sample, its range and whether it was checked (invariant 12)', () => {
    const s = shareView({ k: 3, n: 31, lo: 0.02, hi: 0.26, checked: false })
    expect(s.count).toBe('3 of 31 model runs')
    expect(s.range).toBe('95% range 2 to 26%')
    expect(s.checked).toBe('not yet checked against observations')
  })

  it('ageWords', () => {
    const now = Date.UTC(2026, 8, 27, 8)
    expect(ageWords(now - 30_000, now)).toBe('just now')
    expect(ageWords(now - 40 * 60_000, now)).toBe('40 min ago')
    expect(ageWords(now - 11 * 3_600_000, now)).toBe('11 h ago')
    expect(ageWords(now - 3 * 86_400_000, now)).toBe('3 days ago')
  })
})
