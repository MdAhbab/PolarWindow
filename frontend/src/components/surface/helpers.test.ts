import { describe, expect, it } from 'vitest'
import { bandPath, linePath, linear, niceDomain, niceTicks, num, pct, quantityWords, runs, shareWords } from './helpers'
import type { QuantityDTO } from '../../lib/api/surface.types'

const q = (over: Partial<QuantityDTO>): QuantityDTO => ({ value: 1, unit: 'h', provenance: 'computed', ...over })

describe('scales', () => {
  it('maps a domain onto a range, flipped when asked', () => {
    const y = linear(0, 100, 200, 0)
    expect(y(0)).toBe(200)
    expect(y(100)).toBe(0)
    expect(y(25)).toBe(150)
  })
  it('maps a zero-width domain to the middle instead of dividing by zero', () => {
    expect(linear(5, 5, 0, 10)(5)).toBe(5)
  })
  it('gives round ticks inside the span', () => {
    expect(niceTicks(0, 600, 3)).toEqual([0, 200, 400, 600])
    expect(niceTicks(-107, 15, 3)).toEqual([-100, -50, 0])
  })
  it('pads a domain out to round numbers', () => {
    expect(niceDomain([0, 587])).toEqual([0, 600])
    expect(niceDomain([-113, 15, -40])).toEqual([-150, 50])
    expect(niceDomain([])).toEqual([0, 1])
  })
})

describe('margin formatting', () => {
  it('shows a symmetric margin as ±', () => {
    const w = quantityWords(q({ value: 5.85, unit: 'deg', pm: 1.415 }))
    expect(w.value).toBe('5.85')
    expect(w.unit).toBe('°')
    expect(w.margin).toBe('± 1.42')
  })
  it('shows a range with a true minus sign', () => {
    const w = quantityWords(q({ value: -104.2, unit: 'degC', lo: -107, hi: -101.3 }), 0)
    expect(w.value).toBe('−104')
    expect(w.unit).toBe('°C')
    expect(w.margin).toBe('range −107 to −101')
  })
  it('says so when both ends of the range agree, rather than a range of nothing', () => {
    expect(quantityWords(q({ value: 0, unit: 'Wh', lo: 0, hi: 0 }), 0).margin).toBe('0 at both ends of the range')
  })
  it('turns large watt-hours into kilowatt-hours, margin and all', () => {
    const w = quantityWords(q({ value: 334539.6, unit: 'Wh', lo: 333938.5, hi: 335140.7 }), 1)
    expect(w.unit).toBe('kWh')
    expect(w.value).toBe('334.5')
    expect(w.margin).toBe('range 333.9 to 335.1')
  })
  it('gives the stated reason when there is no margin, and the missing reason when there is no value', () => {
    const none = quantityWords(q({ value: 56.9, unit: 'deg', no_margin_reason: 'no margin was entered' }))
    expect(none.margin).toBe('no margin was entered')
    expect(none.marginIsReason).toBe(true)
    const missing = quantityWords(q({ value: null, missing_reason: 'the battery never empties in these dates' }))
    expect(missing.value).toBe('—')
    expect(missing.margin).toBe('the battery never empties in these dates')
  })
  it('marks a lower bound cut short by the dates', () => {
    expect(quantityWords(q({ value: 12, open: true, pm: 1 }), 0).value).toBe('at least 12')
  })
  it('formats numbers by size', () => {
    expect(num(1234.5)).toBe('1,235')
    expect(num(-0.25)).toBe('−0.250')
    expect(num(Number.NaN)).toBe('—')
  })
})

describe('share wording', () => {
  it('says the count and its interval', () => {
    expect(shareWords({ k: 354, n: 1000, lo: 0.3243, hi: 0.3845 })).toBe('354 of 1000 points (32–38 %)')
  })
  it('keeps one decimal for small shares so a small upper end is not rounded away', () => {
    expect(shareWords({ k: 0, n: 1000, lo: 0, hi: 0.00368 })).toBe('0 of 1000 points (0–0.4 %)')
    expect(pct(0.0654)).toBe('6.5')
  })
})

describe('paths', () => {
  it('finds runs of a condition', () => {
    expect(runs([1, 1, 0, 0, 1, 0], (v) => v === 0)).toEqual([
      [2, 3],
      [5, 5],
    ])
  })
  it('breaks a line at a gap', () => {
    expect(linePath([0, 1, 2, 3], [5, null, 7, 8])).toBe('M0.0 5.0M2.0 7.0L3.0 8.0')
  })
  it('draws a band only where both edges are known', () => {
    const d = bandPath([0, 1, 2], [1, 1, null], [3, 3, 3])
    expect(d).toBe('M0.0 3.0L1.0 3.0L1.0 1.0L0.0 1.0Z')
  })
})
