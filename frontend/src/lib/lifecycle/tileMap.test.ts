import { describe, expect, it } from 'vitest'
import viewshedSource from '../../../../backend/app/core/viewshed.py?raw'
import { TILE_STYLE, TILE_HALF_EXTENT_M, siteFrame, tileSwatch, tilesFor, toGround, zoomFor } from './tileMap'

// IM-2's landing spot as the service holds it, and the frame `core.projections.local_frame` measures
// there by stepping 100 m due north through the projection (pyproj): the grid position, the turn of
// the grid against true north (its longitude), and the scale.
const IM2 = { lat: -84.7906, lon: 29.1957 }
const MEASURED = { x0: 77108.24153038967, y0: 137993.27026503164, convergenceDeg: 29.1957, k: 1.0020708282634112 }

describe('the site frame', () => {
  it('agrees with the projection the service measures', () => {
    const f = siteFrame(IM2.lat, IM2.lon)
    expect(f.x0).toBeCloseTo(MEASURED.x0, 1)
    expect(f.y0).toBeCloseTo(MEASURED.y0, 1)
    expect(f.convergenceDeg).toBeCloseTo(MEASURED.convergenceDeg, 4)
    expect(f.k).toBeCloseTo(MEASURED.k, 5)
  })

  it('takes a point of the grid back to the ground east and north of the lander, whichever way the grid turns', () => {
    for (const lon of [0, 29.1957, 120, 200, -75]) {
      const f = siteFrame(-85, lon)
      // Forward, as `LocalFrame.local_to_grid` does it.
      const a = (f.convergenceDeg * Math.PI) / 180
      for (const [east, north] of [[100, 0], [0, 250], [-300, 120], [42, -77]]) {
        const gx = f.x0 + (east * Math.cos(a) + north * Math.sin(a)) * f.k
        const gy = f.y0 + (-east * Math.sin(a) + north * Math.cos(a)) * f.k
        const g = toGround(f, gx, gy)
        expect(g.east).toBeCloseTo(east, 6)
        expect(g.north).toBeCloseTo(north, 6)
      }
    }
  })
})

describe('the zoom', () => {
  it('puts a tile pixel nearest the metres a screen pixel covers', () => {
    // z10 tiles are 593.67 m, 2.32 m a pixel; z7 is 18.6 m.
    expect(zoomFor(2.32)).toBe(10)
    expect(zoomFor(18.6)).toBe(7)
    expect(zoomFor(9)).toBe(8)
    expect(zoomFor(0.001)).toBe(12)
    expect(zoomFor(1e6)).toBe(0)
  })
})

describe('the tiles of a map', () => {
  const f = siteFrame(IM2.lat, IM2.lon)
  // Half a cell past the last range, as the answer's cells end: 500 m, 20 ranges.
  const R = 512.5

  it('asks for exactly the tiles the service draws something in', () => {
    // From the service: at zoom 10 the line-of-sight layer of IM-2's answer has pixels in these six
    // tiles, and none in the columns and rows around them (`tile_rgba` returned None there).
    const got = tilesFor(f, 10, 1.2 * R, R).map((t) => [t.x, t.y].join(','))
    expect(new Set(got)).toEqual(new Set(['641,278', '641,279', '641,280', '642,278', '642,279', '642,280']))
  })

  it('places each tile from the lander, y down, as far as its size', () => {
    const size = (2 * TILE_HALF_EXTENT_M) / 2 ** 10
    for (const t of tilesFor(f, 10, 1.2 * R)) {
      expect(t.size).toBeCloseTo(size, 9)
      expect(t.left).toBeCloseTo(-TILE_HALF_EXTENT_M + t.x * size - f.x0, 6)
      expect(t.top).toBeCloseTo(-(TILE_HALF_EXTENT_M - t.y * size - f.y0), 6)
    }
    // The lander is inside one tile: its own corner offsets straddle it.
    const own = tilesFor(f, 10, 1.2 * R).find((t) => t.left <= 0 && t.left + t.size >= 0 && t.top <= 0 && t.top + t.size >= 0)
    expect(own).toBeDefined()
  })

  it('covers the whole visible square, turned, and no more than a ring of tiles around it', () => {
    const half = 1.2 * R
    const tiles = tilesFor(f, 10, half)
    // Sample the square on a grid and find each point in the tiles (as the grid sees it).
    const a = (f.convergenceDeg * Math.PI) / 180
    for (let east = -half; east <= half; east += half / 4) {
      for (let north = -half; north <= half; north += half / 4) {
        const gx = f.x0 + (east * Math.cos(a) + north * Math.sin(a)) * f.k
        const gy = f.y0 + (-east * Math.sin(a) + north * Math.cos(a)) * f.k
        const hit = tiles.some((t) => gx - f.x0 >= t.left && gx - f.x0 <= t.left + t.size && -(gy - f.y0) >= t.top && -(gy - f.y0) <= t.top + t.size)
        expect(hit, `${east}, ${north}`).toBe(true)
      }
    }
    expect(tiles.length).toBeLessThan(16)
  })

  it('stays inside the scheme at the top of the world', () => {
    const pole = siteFrame(-89.99, 10)
    for (const t of tilesFor(pole, 3, 5000)) {
      expect(t.x).toBeGreaterThanOrEqual(0)
      expect(t.y).toBeLessThan(8)
    }
    expect(tilesFor(pole, 0, 5000)).toHaveLength(1)
  })
})

describe('the tile style', () => {
  it('is the style the service draws, held to app/core/viewshed.py', () => {
    const src: string = viewshedSource
    const tuple = (name: string) => {
      const m = src.match(new RegExp(`${name}: Final\\[tuple\\[int, int, int, int\\]\\] = \\(([^)]*)\\)`))
      if (!m) throw new Error(`${name} not found in viewshed.py`)
      return m[1].split(',').map((x) => Number(x.trim()))
    }
    const num = (name: string) => {
      const m = src.match(new RegExp(`${name}: Final\\[int\\] = (\\d+)`))
      if (!m) throw new Error(`${name} not found in viewshed.py`)
      return Number(m[1])
    }
    expect([...TILE_STYLE.clear]).toEqual(tuple('CLEAR_RGBA'))
    expect([...TILE_STYLE.blocked]).toEqual(tuple('BLOCKED_RGBA'))
    expect([...TILE_STYLE.blockedStripe]).toEqual(tuple('BLOCKED_STRIPE_RGBA'))
    expect([...TILE_STYLE.uncertain]).toEqual(tuple('UNCERTAIN_RGBA'))
    expect([...TILE_STYLE.uncertainStripe]).toEqual(tuple('UNCERTAIN_STRIPE_RGBA'))
    expect(TILE_STYLE.periodPx).toBe(num('HATCH_PERIOD_PX'))
    expect(TILE_STYLE.blockedStripePx).toBe(num('BLOCKED_STRIPE_PX'))
    expect(TILE_STYLE.uncertainStripePx).toBe(num('UNCERTAIN_STRIPE_PX'))
  })

  it('draws a legend swatch of each state that tells them apart by pattern', () => {
    expect(tileSwatch('clear')).toBe('rgba(79, 198, 224, 0.588)')
    const blocked = tileSwatch('blocked')
    const uncertain = tileSwatch('uncertain')
    expect(blocked).toMatch(/^repeating-linear-gradient\(135deg,/)
    expect(uncertain).toMatch(/^repeating-linear-gradient\(45deg,/)
    expect(blocked).not.toBe(uncertain)
  })
})
