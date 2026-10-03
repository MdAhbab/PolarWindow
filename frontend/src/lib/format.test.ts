/**
 * U10: timestamps a person (and a screen reader) can say. ISO stays in the
 * exports, which `export.test.ts` covers.
 */
import { describe, expect, it } from 'vitest'
import {
  dateTimeWords,
  humanStamp,
  humanStampH,
  isoDateWords,
  modelHFromMs,
  msFromModelH,
  plusMinus,
  precisionWords,
  spanWords,
  windowLine,
} from './format'

const EPOCH = Date.UTC(2027, 2, 14)

describe('humanStamp', () => {
  it('reads the handoff example exactly', () => {
    // 12 days and 9 hours into a window that opens 14 March 2027.
    expect(humanStamp(EPOCH, 12 * 24 + 9)).toBe('Day 12, 26 March, 09:00 UTC')
  })

  it('shows minutes, since windows are sampled every 15 minutes', () => {
    expect(humanStamp(EPOCH, 0.25)).toBe('Day 0, 14 March, 00:15 UTC')
  })

  it('adds the year only when the moment is in a different year from the window start', () => {
    expect(humanStamp(Date.UTC(2027, 11, 20), 15 * 24)).toBe('Day 15, 4 January 2028, 00:00 UTC')
    expect(humanStamp(Date.UTC(2027, 11, 20), 24)).toBe('Day 1, 21 December, 00:00 UTC')
  })

  it('never contains an ISO stamp', () => {
    expect(humanStamp(EPOCH, 100)).not.toMatch(/\d{4}-\d{2}-\d{2}|Z$/)
  })

  it('counts days from the window start, wherever the window is', () => {
    const startH = modelHFromMs(Date.UTC(2025, 2, 6, 17, 30))
    expect(humanStampH(startH + 13, startH)).toBe('Day 0, 7 March, 06:30 UTC')
  })
})

describe('model hours', () => {
  it('round-trips between the store unit and instants, including before the epoch', () => {
    const ms = Date.UTC(2025, 2, 6, 17, 30)
    expect(msFromModelH(modelHFromMs(ms))).toBe(ms)
    expect(modelHFromMs(ms)).toBeLessThan(0)
  })
})

describe('window and date words', () => {
  it('states a window as "N days from D Mon YYYY"', () => {
    expect(windowLine(EPOCH, 30 * 24)).toBe('30 days from 14 Mar 2027')
    expect(windowLine(EPOCH, 708.734)).toBe('29.5 days from 14 Mar 2027')
    expect(spanWords(12.75)).toBe('12.75 hours')
  })

  it('says how precisely a date is known', () => {
    expect(precisionWords('year')).toBe('to the year')
    expect(precisionWords('minute')).toBe('to the minute')
    expect(precisionWords('second')).toBe('to the second')
  })

  it('writes dates and times in words, leaving midnight off', () => {
    expect(dateTimeWords(Date.UTC(2025, 2, 6, 17, 30))).toBe('6 March 2025, 17:30 UTC')
    expect(dateTimeWords(Date.UTC(2025, 2, 17))).toBe('17 March 2025')
    expect(isoDateWords('2026-09-23')).toBe('23 September 2026')
  })
})

describe('plusMinus', () => {
  it('never prints a zero margin', () => {
    expect(plusMinus(17.09)).toBe('±17.1')
    expect(plusMinus(0.02)).toBe('±<0.1')
    expect(plusMinus(0.004, 2)).toBe('±<0.01')
  })
})
