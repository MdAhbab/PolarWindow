import { describe, expect, it } from 'vitest'
import { MIN_FRAME_GAPS, SLOW_FRAME_MS, frameGaps, framesTooSlow, median } from './frameBudget'

/** Timestamps `n + 1` frames apart by `gap` ms each. */
const steady = (n: number, gap: number) => Array.from({ length: n + 1 }, (_, i) => i * gap)

describe('frameGaps', () => {
  it('is the difference between neighbours', () => {
    expect(frameGaps([0, 16, 33, 50])).toEqual([16, 17, 17])
  })
  it('is empty for fewer than two stamps and drops a backwards or non-finite step', () => {
    expect(frameGaps([])).toEqual([])
    expect(frameGaps([5])).toEqual([])
    expect(frameGaps([10, 5, 20])).toEqual([15])
    expect(frameGaps([0, Number.NaN, 30])).toEqual([])
  })
})

describe('median', () => {
  it('takes the middle, or the mean of the two middle ones', () => {
    expect(median([3, 1, 2])).toBe(2)
    expect(median([4, 1, 3, 2])).toBe(2.5)
    expect(Number.isNaN(median([]))).toBe(true)
  })
})

describe('framesTooSlow', () => {
  it('keeps up at 60 Hz, 90 Hz and 120 Hz', () => {
    for (const gap of [16.7, 11.1, 8.3]) expect(framesTooSlow(frameGaps(steady(12, gap)))).toBe(false)
  })
  it('is too slow at the 50 ms a frame that software drawing gave', () => {
    expect(framesTooSlow(frameGaps(steady(12, 50)))).toBe(true)
  })
  it('puts the line at 30 ms: at it is fine, over it is slow', () => {
    expect(SLOW_FRAME_MS).toBe(30)
    expect(framesTooSlow(frameGaps(steady(12, 30)))).toBe(false)
    expect(framesTooSlow(frameGaps(steady(12, 31)))).toBe(true)
  })
  it('judges by the median: a few long frames in a quick run do not count, a few quick ones in a slow run do not save it', () => {
    expect(framesTooSlow([16, 16, 120, 16, 16, 90, 16, 16, 16, 16])).toBe(false)
    expect(framesTooSlow([60, 60, 16, 60, 60, 16, 60, 60, 60, 60])).toBe(true)
  })
  it('leaves out a stall of a second or more (a hidden tab) rather than reading it as slowness', () => {
    expect(framesTooSlow([16, 16, 16, 16, 16, 16, 4000, 16, 16, 16])).toBe(false)
    // Only stalls and too few real frames left: no verdict.
    expect(framesTooSlow([2000, 3000, 2500, 16, 16, 16])).toBe(false)
  })
  it('gives no verdict on a sample too short to mean anything', () => {
    expect(framesTooSlow([])).toBe(false)
    expect(framesTooSlow(Array.from({ length: MIN_FRAME_GAPS - 1 }, () => 200))).toBe(false)
    expect(framesTooSlow(Array.from({ length: MIN_FRAME_GAPS }, () => 200))).toBe(true)
  })
  it('takes a different limit when given one', () => {
    expect(framesTooSlow(frameGaps(steady(12, 20)), 18)).toBe(true)
    expect(framesTooSlow(frameGaps(steady(12, 20)), 25)).toBe(false)
  })
})
