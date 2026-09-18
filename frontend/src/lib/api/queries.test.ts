/**
 * Cache keys, per ADR-2.
 *
 * Two properties matter and neither is visible on screen when it breaks:
 * a key that omits the engine version keeps serving the *previous* geometry
 * out of the client cache after a backend redeploy, and a key built from raw
 * instants turns one window into a new request on every pointer move.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { getEngineVersion, keys, setEngineVersion } from './queries'
import { quantiseWindow } from './adapters'

const START = Date.UTC(2027, 2, 14)
const SPAN = 709 * 3_600_000
const W = { ...quantiseWindow(START, START + SPAN, 900), stepS: 900 }

afterEach(() => setEngineVersion('unknown'))

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
