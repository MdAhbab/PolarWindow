/**
 * Cache keys, per ADR-2.
 *
 * Two properties matter and neither is visible on screen when it breaks:
 * a key that omits the engine version keeps serving the *previous* geometry
 * out of the client cache after a backend redeploy, and a key built from raw
 * instants turns one window into a new request on every pointer move.
 */
import { afterEach, describe, expect, it } from 'vitest'
import {
  getEngineVersion,
  keys,
  normaliseMissionFilters,
  resetMissionVersions,
  resetSiteDemProducts,
  setEngineVersion,
  setMissionVersions,
  setSiteDemProduct,
} from './queries'
import { quantiseWindow } from './adapters'

const START = Date.UTC(2027, 2, 14)
const SPAN = 709 * 3_600_000
const W = { ...quantiseWindow(START, START + SPAN, 900), stepS: 900 }

afterEach(() => {
  setEngineVersion('unknown')
  resetMissionVersions()
  resetSiteDemProducts()
})

describe('query keys', () => {
  it('carry the engine version everywhere a number comes from the engine', () => {
    setEngineVersion('hz-2/vis-2')
    const keyed = [
      keys.site('connecting-ridge'),
      keys.horizon('connecting-ridge'),
      keys.windows('connecting-ridge', W),
      keys.metrics('connecting-ridge', W),
      keys.timeline('connecting-ridge', W),
      keys.compare(['connecting-ridge', 'malapert-massif'], W, 'dark'),
    ]
    for (const k of keyed) expect(k).toContain('hz-2/vis-2')
  })

  it('change when the engine changes, so old geometry cannot be served', () => {
    setEngineVersion('hz-1/vis-1')
    const before = JSON.stringify(keys.metrics('connecting-ridge', W))
    setEngineVersion('hz-2/vis-2')
    expect(JSON.stringify(keys.metrics('connecting-ridge', W))).not.toBe(before)
  })

  it('leave the site list and health un-keyed on the version', () => {
    setEngineVersion('hz-2/vis-2')
    // The site list is what reports the version; keying it on the version it
    // has not delivered yet would be circular.
    expect(keys.sites({})).not.toContain(getEngineVersion())
    expect(keys.health()).toEqual(['health'])
  })

  it('collapse a drag inside one step onto one key', () => {
    const a = keys.metrics('connecting-ridge', W)
    const nudged = quantiseWindow(START + 1000, START + 1000 + SPAN, 900)
    const b = keys.metrics('connecting-ridge', { ...nudged, stepS: 900 })
    expect(b).toEqual(a)
  })

  it('separate two different windows, two different steps and two sites', () => {
    const later = quantiseWindow(START + 86_400_000, START + 86_400_000 + SPAN, 900)
    expect(keys.metrics('connecting-ridge', { ...later, stepS: 900 })).not.toEqual(
      keys.metrics('connecting-ridge', W),
    )
    expect(keys.metrics('connecting-ridge', { ...W, stepS: 3600 })).not.toEqual(
      keys.metrics('connecting-ridge', W),
    )
    expect(keys.metrics('malapert-massif', W)).not.toEqual(keys.metrics('connecting-ridge', W))
  })

  it('treat a comparison of the same sites in any order as one query', () => {
    expect(keys.compare(['b', 'a'], W, 'sun')).toEqual(keys.compare(['a', 'b'], W, 'sun'))
    expect(keys.compare(['a', 'b'], W, 'dark')).not.toEqual(keys.compare(['a', 'b'], W, 'sun'))
  })

  it('does not reorder the caller’s array while sorting the key', () => {
    const ids = ['b', 'a']
    keys.compare(ids, W, 'sun')
    expect(ids).toEqual(['b', 'a'])
  })
})

describe('mission and calendar keys (contract v2)', () => {
  it('carry the engine version', () => {
    setEngineVersion('hz-2/vis-2')
    expect(keys.missions({})).toContain('hz-2/vis-2')
    expect(keys.mission('im-2')).toContain('hz-2/vis-2')
    expect(keys.calendar('connecting-ridge', { start: W.start, end: W.end }, 'month')).toContain('hz-2/vis-2')
  })

  it('treat the same filters in any order as one query', () => {
    const a = keys.missions({ payloadType: ['volatiles', 'imaging'], status: ['planned', 'in_transit'] })
    const b = keys.missions({ status: ['in_transit', 'planned', 'planned'], payloadType: ['imaging', 'volatiles'] })
    expect(JSON.stringify(b)).toBe(JSON.stringify(a))
  })

  it('drop empty filters, so "no filter" is one key however it was expressed', () => {
    expect(keys.missions({ payloadType: [], provider: '  ', q: '' })).toEqual(keys.missions({}))
    expect(normaliseMissionFilters({ provider: ' Astrobotic ' })).toEqual({ provider: 'Astrobotic' })
  })

  it('separate different filter sets', () => {
    expect(keys.missions({ payloadType: ['volatiles'] })).not.toEqual(keys.missions({}))
    expect(keys.missions({ provider: 'Astrobotic' })).not.toEqual(keys.missions({ provider: 'Blue Origin' }))
  })

  it('fold the record\'s data_version into the detail key once the list reports it', () => {
    const before = keys.mission('im-2')
    expect(before.at(-1)).toBeNull()
    setMissionVersions([{ id: 'im-2', dataVersion: 'aaaa' }])
    const v1 = keys.mission('im-2')
    expect(v1).toContain('aaaa')
    setMissionVersions([{ id: 'im-2', dataVersion: 'bbbb' }])
    // A changed record is a new key: the cached detail cannot be served for it.
    expect(keys.mission('im-2')).not.toEqual(v1)
    expect(keys.mission('im-1').at(-1)).toBeNull()
  })

  it('key the calendar on site, span and bucket', () => {
    const span = { start: '2027-03-01T00:00:00Z', end: '2028-03-01T00:00:00Z' }
    const later = { start: '2027-04-01T00:00:00Z', end: '2028-04-01T00:00:00Z' }
    expect(keys.calendar('a', span, 'month')).not.toEqual(keys.calendar('b', span, 'month'))
    expect(keys.calendar('a', span, 'month')).not.toEqual(keys.calendar('a', later, 'month'))
    expect(keys.calendar('a', span, 'month')).not.toEqual(keys.calendar('a', span, 'day'))
    expect(keys.calendar('a', span, 'month')).toEqual(keys.calendar('a', { ...span }, 'month'))
  })

  it('leave the run log un-keyed on the engine: a run is a record, not geometry', () => {
    expect(keys.agentRuns()).toEqual(['agentRuns'])
  })
})

describe('site dem_product in query keys', () => {
  it('folds dem_product into horizon, windows, metrics, timeline, and compare keys', () => {
    const siteId = 'mission-blue-ghost-m1'
    const beforeHorizon = keys.horizon(siteId)
    const beforeWindows = keys.windows(siteId, W)
    const beforeMetrics = keys.metrics(siteId, W)
    const beforeTimeline = keys.timeline(siteId, W)
    const beforeCompare = keys.compare([siteId, 'connecting-ridge'], W, 'sun')

    expect(beforeHorizon).toContain(null)
    expect(beforeWindows).toContain(null)
    expect(beforeMetrics).toContain(null)
    expect(beforeTimeline).toContain(null)

    setSiteDemProduct(siteId, 'SLDEM2015 (LOLA + SELENE TC), 59 m')

    const afterHorizon = keys.horizon(siteId)
    const afterWindows = keys.windows(siteId, W)
    const afterMetrics = keys.metrics(siteId, W)
    const afterTimeline = keys.timeline(siteId, W)
    const afterCompare = keys.compare([siteId, 'connecting-ridge'], W, 'sun')

    expect(afterHorizon).toContain('SLDEM2015 (LOLA + SELENE TC), 59 m')
    expect(afterWindows).toContain('SLDEM2015 (LOLA + SELENE TC), 59 m')
    expect(afterMetrics).toContain('SLDEM2015 (LOLA + SELENE TC), 59 m')
    expect(afterTimeline).toContain('SLDEM2015 (LOLA + SELENE TC), 59 m')
    expect(JSON.stringify(afterCompare)).not.toEqual(JSON.stringify(beforeCompare))

    resetSiteDemProducts()
    expect(keys.horizon(siteId)).toEqual(beforeHorizon)
  })
})
