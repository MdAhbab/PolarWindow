/**
 * U10: timestamps a person (and a screen reader) can say. ISO stays in the
 * exports, which `export.test.ts` covers.
 */
import { describe, expect, it } from 'vitest'
import {
  dateTimeWords,
  humanStamp,
  hoursPhrase,
  hoursSpoken,
  humanStampH,
  isoDateWords,
  modelHFromMs,
  msFromModelH,
  plusMinus,
  precisionWords,
  spanWords,
  wholeFigure,
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
    // Under two days, whole hours: the figure a tile shows for the same stretch.
    expect(spanWords(12.75)).toBe('13 hours')
    expect(spanWords(12.4)).toBe('12 hours')
    expect(spanWords(1)).toBe('1 hour')
    expect(spanWords(47.6)).toBe('48 hours')
    expect(spanWords(48)).toBe('2 days')
  })

  it('writes a duration in hours one way for a tile and for a sentence', () => {
    // 12.78 h (IM-2's 6 March to 7 March stay) is "13" on a tile and "13 hours" in the headline, never "12.75".
    expect(wholeFigure(12.78)).toBe('13')
    expect(hoursPhrase(12.78)).toBe('13 hours')
    expect(hoursPhrase(121.6)).toBe('122 hours')
    expect(hoursPhrase(0.6)).toBe('1 hour')
    expect(hoursSpoken(121.6)).toBe('about 122 hours')
    expect(hoursSpoken(288, true)).toBe('at least 288 hours')
    expect(hoursSpoken(1.2)).toBe('about 1 hour')
    for (const h of [0.4, 6.5, 12.75, 17.1, 121.6, 606]) expect(hoursPhrase(h)).toBe(`${wholeFigure(h)} ${wholeFigure(h) === '1' ? 'hour' : 'hours'}`)
    expect(spanWords(12.75)).not.toMatch(/\./)
  })

  it('lets a step whose tiles write hours another way give its own writer, so its headline still agrees', () => {
    // The Contact step's tiles and answer write 12.78 h as "12.8 h" (`formatValue`), so its window does too.
    const oneDecimal = (h: number) => h.toFixed(1)
    expect(spanWords(12.78, oneDecimal)).toBe('12.8 hours')
    expect(windowLine(Date.UTC(2025, 2, 6), 12.78, oneDecimal)).toBe('12.8 hours from 6 Mar 2025')
    expect(hoursPhrase(1, String)).toBe('1 hour')
    // Days are written the same everywhere.
    expect(spanWords(720, oneDecimal)).toBe('30 days')
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
