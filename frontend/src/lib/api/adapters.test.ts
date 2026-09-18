/**
 * The adapter is the only place the wire format becomes the shape the screens
 * draw, so it is the only frontend code whose mistakes are silent: a factor of
 * 3,600 in the wrong place still renders.
 *
 * The fixtures are captured responses for Connecting Ridge over the default
 * window, at engine hz-2/vis-2 — the same numbers the backend pins in
 * `backend/app/tests/golden/data/connecting-ridge.metrics.json`. The first test
 * asserts that correspondence, so a physics change that skips the frontend
 * fails here rather than in a demo.
 */
import { describe, expect, it } from 'vitest'
import type { HorizonDTO, MetricsDTO, TimelineDTO, WindowsDTO } from './client'
import {
  DARK,
  LIT,
  PENUMBRAL,
  adaptAutonomy,
  adaptHorizon,
  adaptMeta,
  adaptSite,
  hoursFrom,
  quantiseWindow,
  toHours,
  visibilityStates,
} from './adapters'
import metricsFixture from './__fixtures__/connecting-ridge.metrics.json'
import windowsFixture from './__fixtures__/connecting-ridge.windows.json'

const metrics = metricsFixture as unknown as MetricsDTO
const windows = windowsFixture as unknown as WindowsDTO

/** The backend's golden, in seconds. Kept literal so the two must be edited
 *  together, which is the point of a golden. */
const GOLDEN_S = {
  sunlit: 2067837.7256783533,
  earthContact: 1549023.0173461216,
  longestDark: 437647.79603997123,
  longestBlackout: 1002476.9827488882,
  worstCompound: 138206.21593985753,
  survivalNeeded: 437647.79603997123,
  sunArcCount: 8,
  earthArcCount: 3,
}

const MASK = {
  elDeg: new Float32Array([0, 1, 2, 3]),
  rangeM: new Float32Array([10, 20, 30, 40]),
  tolDeg: new Float32Array([0.1, 0.1, 0.1, 0.1]),
  maxElDeg: 3,
  maxElBearingDeg: 270,
}

describe('adaptSite', () => {
  const adapted = adaptSite('connecting-ridge', windows, metrics, MASK)
  const m = adapted.metrics

  it('lands on the backend golden, converted to hours', () => {
    expect(m.sun.upHours).toBeCloseTo(GOLDEN_S.sunlit / 3600, 6)
    expect(m.earth.upHours).toBeCloseTo(GOLDEN_S.earthContact / 3600, 6)
    expect(m.sun.longestDownH).toBeCloseTo(GOLDEN_S.longestDark / 3600, 6)
    expect(m.earth.longestDownH).toBeCloseTo(GOLDEN_S.longestBlackout / 3600, 6)
    expect(m.worstCompoundH).toBeCloseTo(GOLDEN_S.worstCompound / 3600, 6)
  })

  it('keeps every arc the server sent, in window hours', () => {
    expect(m.sun.arcs).toHaveLength(GOLDEN_S.sunArcCount)
    expect(m.earth.arcs).toHaveLength(GOLDEN_S.earthArcCount)
    for (const a of [...m.sun.arcs, ...m.earth.arcs]) {
      expect(a.endH - a.startH).toBeCloseTo(a.hours, 9)
      expect(a.startH).toBeGreaterThanOrEqual(0)
      expect(a.endH).toBeLessThanOrEqual(m.windowHours + 1e-9)
    }
    // Arcs partition the window: each body's arcs are contiguous end-to-start.
    // The wire rounds `duration_s` to the millisecond while the arc instants
    // keep microseconds, so contiguity is asserted in milliseconds rather than
    // pretending to a precision the schema does not carry.
    const ms = (h: number) => h * 3_600_000
    for (const arcs of [m.sun.arcs, m.earth.arcs]) {
      for (let i = 1; i < arcs.length; i++) {
        expect(Math.abs(ms(arcs[i].startH - arcs[i - 1].endH))).toBeLessThan(1.5)
      }
      expect(arcs[0].startH).toBeCloseTo(0, 9)
      expect(Math.abs(ms(arcs[arcs.length - 1].endH - m.windowHours))).toBeLessThan(
        1.5 * arcs.length,
      )
    }
  })

  it('carries the window-edge flags rather than inferring them', () => {
    expect(m.sun.arcs[0].openStart).toBe(true)
    expect(m.sun.arcs[0].openEnd).toBe(false)
    expect(m.sun.arcs.at(-1)?.openEnd).toBe(true)
    // The longest dark stretch is inside this window, so it is not a bound.
    expect(m.sun.longestDownOpen).toBe(false)
  })

  it('picks the longest *down* arc, never the longest arc', () => {
    const longest = m.sun.longestDownArc
    expect(longest?.up).toBe(false)
    expect(longest?.hours).toBeCloseTo(m.sun.longestDownH, 6)
  })

  it('names the terrain that blocks, and omits the field when nothing does', () => {
    const blocked = m.sun.arcs.find((a) => !a.up && a.blockedByBearingDeg !== undefined)
    expect(blocked?.blockedByBearingDeg).toBeGreaterThanOrEqual(0)
    expect(blocked?.blockedByBearingDeg).toBeLessThan(360)
    const lit = m.sun.arcs.find((a) => a.up)
    expect(lit && 'blockedByBearingDeg' in lit).toBe(false)
  })

  it('leaves the samples empty when no timeline was fetched', () => {
    expect(m.sun.samples).toEqual([])
    expect(adapted.sunStates).toBeUndefined()
  })

  it('keeps the window start as an instant, for the exports', () => {
    expect(m.windowStartIso).toBe(windows.start)
    expect(m.windowHours).toBeCloseTo(hoursFrom(windows.start, windows.end), 9)
  })
})

describe('adaptAutonomy', () => {
  it('converts the server packet and recomputes nothing', () => {
    const a = adaptAutonomy(metrics)
    expect(a.survivalNeededH).toBeCloseTo(GOLDEN_S.survivalNeeded / 3600, 6)
    expect(a.worstCompoundH).toBeCloseTo(GOLDEN_S.worstCompound / 3600, 6)
    // The margin is the server's, applied to the server's compound event.
    expect(a.requiredAutonomyH).toBeCloseTo(a.worstCompoundH * (1 + a.marginFraction), 4)
    expect(a.compoundInsideDark).toBe(true)
  })
})

describe('adaptMeta', () => {
  const meta = adaptMeta(metrics.meta)

  it('converts the timing margin to hours and keeps null as null', () => {
    expect(meta.uncertainty.edgeTimingH).toBeCloseTo(
      (metrics.meta.uncertainty.edge_timing_s as number) / 3600,
      9,
    )
    const grazing = adaptMeta({
      ...metrics.meta,
      uncertainty: { ...metrics.meta.uncertainty, edge_timing_s: null, grazing: true },
    })
    expect(grazing.uncertainty.edgeTimingH).toBeNull()
    expect(grazing.uncertainty.grazing).toBe(true)
  })

  it('keeps grazing and partial coverage as separate claims', () => {
    expect(meta.uncertainty.grazing).toBe(false)
    expect(meta.uncertainty.partialCoverage).toBe(false)
    const partial = adaptMeta({
      ...metrics.meta,
      uncertainty: { ...metrics.meta.uncertainty, coverage: 0.42 },
    })
    expect(partial.uncertainty.partialCoverage).toBe(true)
    expect(partial.uncertainty.grazing).toBe(false)
  })
})

describe('adaptHorizon', () => {
  it('rebuilds the mask as typed arrays', () => {
    const dto = {
      site_id: 's',
      step_deg: 90,
      el_deg: [0, -1, 2, 0.5],
      range_m: [1, 2, 3, 4],
      tol_deg: [0.01, 0.02, 0.03, 0.04],
      max_el_deg: 2,
      max_el_bearing_deg: 180,
    } as unknown as HorizonDTO
    const mask = adaptHorizon(dto)
    expect(mask.elDeg).toBeInstanceOf(Float32Array)
    expect(Array.from(mask.elDeg)).toEqual([0, -1, 2, 0.5])
    // Negative elevations are the whole point of a ridge site: never clamped.
    expect(Math.min(...mask.elDeg)).toBeLessThan(0)
    expect(mask.maxElBearingDeg).toBe(180)
  })
})

describe('visibilityStates', () => {
  it('passes the three states through unflattened', () => {
    const dto = {
      sun: { state: [DARK, PENUMBRAL, LIT, PENUMBRAL] },
      earth: { state: [LIT, LIT, DARK, DARK] },
    } as unknown as TimelineDTO
    expect(Array.from(visibilityStates(dto, 'sun'))).toEqual([0, 1, 2, 1])
    expect(Array.from(visibilityStates(dto, 'earth'))).toEqual([2, 2, 0, 0])
  })
})

describe('quantiseWindow', () => {
  // The server's rule, transcribed: floor the start onto a grid anchored at
  // 2000-01-01T00:00Z, then round the *length* to a whole number of steps.
  const serverRule = (startMs: number, endMs: number, stepS: number) => {
    const stepMs = stepS * 1000
    const anchor = Date.UTC(2000, 0, 1)
    const s = anchor + Math.floor((startMs - anchor) / stepMs) * stepMs
    const steps = Math.max(1, Math.round((endMs - startMs) / stepMs))
    return { start: s, end: s + steps * stepMs }
  }

  it('agrees with the server rule, including on a grid the Unix epoch misses', () => {
    // 1,100 s does not divide the seconds between the two epochs, so a client
    // that anchored on 1970 would key one step away from the server here.
    for (const stepS of [300, 900, 1100, 3600, 7200]) {
      for (const offsetMs of [0, 61_000, 899_000, 1_234_567]) {
        const startMs = Date.UTC(2027, 2, 14, 0, 0, 0) + offsetMs
        const endMs = startMs + 709 * 3_600_000
        const got = quantiseWindow(startMs, endMs, stepS)
        const want = serverRule(startMs, endMs, stepS)
        expect(Date.parse(got.start)).toBe(want.start)
        expect(Date.parse(got.end)).toBe(want.end)
      }
    }
  })

  it('collapses a drag within one step onto a single window', () => {
    const base = Date.UTC(2027, 2, 14, 0, 0, 0)
    const span = 709 * 3_600_000
    const a = quantiseWindow(base, base + span, 900)
    const b = quantiseWindow(base + 1000, base + 1000 + span, 900)
    expect(b).toEqual(a)
  })

  it('keeps a fixed-length window one fixed number of steps as it slides', () => {
    // Flooring both ends independently made this alternate between 2,834 and
    // 2,835 steps, so the totals wobbled for no visible reason.
    const span = 709 * 3_600_000
    const lengths = new Set<number>()
    for (let i = 0; i < 24; i++) {
      const start = Date.UTC(2027, 2, 14, 0, 0, 0) + i * 137_000
      const w = quantiseWindow(start, start + span, 900)
      lengths.add(Date.parse(w.end) - Date.parse(w.start))
    }
    expect(lengths.size).toBe(1)
  })

  it('never produces an empty window', () => {
    const t = Date.UTC(2027, 2, 14)
    const w = quantiseWindow(t, t + 1, 900)
    expect(Date.parse(w.end) - Date.parse(w.start)).toBe(900_000)
  })
})

describe('unit helpers', () => {
  it('converts seconds to hours', () => {
    expect(toHours(3600)).toBe(1)
    expect(toHours(0)).toBe(0)
  })

  it('measures hours from the window start, including before it', () => {
    expect(hoursFrom('2027-03-14T00:00:00Z', '2027-03-14T06:00:00Z')).toBe(6)
    expect(hoursFrom('2027-03-14T00:00:00Z', '2027-03-13T23:00:00Z')).toBe(-1)
  })
})
