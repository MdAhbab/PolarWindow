/**
 * A map of the ground around one spot, drawn from the service's tiles.
 *
 * The tile scheme is the one the terrain tiles use: a quadtree over the regional
 * elevation model's extent in the lunar south polar stereographic grid (x east,
 * y north in the grid, so tile row 0 is the top). A rover's map is a small piece of
 * it, north up, so this works in the lander's own frame: metres east and north of
 * it, with the tiles turned by the grid's convergence (the grid's north is not true
 * north; at 120°E it is 120° off) and shrunk by its scale (1.002 at 85°S).
 * Nothing here draws; `SiteTileMap` does.
 */

/** Lunar radius, metres: the sphere the LOLA polar products are projected from. */
export const R_MOON_M = 1_737_400

/** Half the side of the tile scheme, metres: the regional model's own extent (as in `PolarMap`). */
export const TILE_HALF_EXTENT_M = 303_960

export const TILE_PX = 256

/** The deepest zoom the rover tiles go to (the terrain tiles stop at 7). */
export const MAX_TILE_ZOOM = 12

const DEG = Math.PI / 180

/** Where the lander is in the tile grid, and how the grid sits against true north at that spot. */
export interface SiteFrame {
  /** Grid metres east and north of the pole. */
  x0: number
  y0: number
  /** Degrees clockwise from the grid's north to true north (the site's longitude, in a polar grid). */
  convergenceDeg: number
  /** Grid metres per ground metre. */
  k: number
}

/**
 * The frame of a spot, from south polar stereographic with scale true at the pole
 * (what the LOLA products and the service use): distance from the pole 2R tan(c/2)
 * for colatitude c, longitude 0 up the grid's +y and east clockwise, scale 1 / cos²(c/2).
 */
export function siteFrame(latDeg: number, lonDeg: number): SiteFrame {
  const c = (90 + latDeg) * DEG
  const rho = 2 * R_MOON_M * Math.tan(c / 2)
  const lon = lonDeg * DEG
  return {
    x0: rho * Math.sin(lon),
    y0: rho * Math.cos(lon),
    convergenceDeg: lonDeg,
    k: 1 / Math.cos(c / 2) ** 2,
  }
}

/** Ground metres east and north of the lander for a point of the grid, as the service reads a tile pixel. */
export function toGround(f: SiteFrame, gx: number, gy: number): { east: number; north: number } {
  const dx = gx - f.x0
  const dy = gy - f.y0
  const a = f.convergenceDeg * DEG
  return {
    east: (dx * Math.cos(a) - dy * Math.sin(a)) / f.k,
    north: (dx * Math.sin(a) + dy * Math.cos(a)) / f.k,
  }
}

/** What a map shows of the answer: the line of sight, or the radio path (which also needs the first Fresnel zone clear). */
export type SightLayer = 'sight' | 'radio'

/**
 * Where each range cell ends: half way between the sampled ranges, the first cell starting
 * at the lander and the last reaching half a step past the largest range. The service draws
 * its tiles from the same edges, so the sectors, the tiles and the table agree.
 */
export function cellEdges(ranges: number[]): number[] {
  const e = [0]
  for (let j = 1; j < ranges.length; j++) e.push((ranges[j - 1] + ranges[j]) / 2)
  const last = ranges[ranges.length - 1]
  e.push(last + (ranges.length > 1 ? (last - ranges[ranges.length - 2]) / 2 : last))
  return e
}

/** The zoom whose tile pixel is nearest `metresPerPixel`, within the rover tiles' scheme. */
export function zoomFor(metresPerPixel: number, max = MAX_TILE_ZOOM): number {
  const z = Math.round(Math.log2((2 * TILE_HALF_EXTENT_M) / (TILE_PX * metresPerPixel)))
  return Math.max(0, Math.min(max, z))
}

/** One tile, placed in the map's own units: grid metres from the lander, the y axis down. */
export interface PlacedTile {
  z: number
  x: number
  y: number
  key: string
  left: number
  top: number
  size: number
}

/**
 * The tiles of zoom `z` that reach the map, and (for a layer that draws only within
 * `discRadiusM` of the lander) only the ones that reach into that disc by a pixel or more,
 * so no tile is asked for that has nothing in it.
 *
 * The map shows the ground within `halfWidthM` east, west, north and south, north up;
 * in the grid that square is turned, so a tile is kept when its circumscribed circle
 * reaches the square.
 */
export function tilesFor(f: SiteFrame, z: number, halfWidthM: number, discRadiusM?: number): PlacedTile[] {
  const n = 2 ** z
  const size = (2 * TILE_HALF_EXTENT_M) / n
  const reach = halfWidthM * f.k * Math.SQRT2
  // Column x spans grid x from -HALF + x size; row y from HALF - y size (its top) down.
  const col = (gx: number) => Math.floor((gx + TILE_HALF_EXTENT_M) / size)
  const row = (gy: number) => Math.floor((TILE_HALF_EXTENT_M - gy) / size)
  const inside = (i: number) => Math.max(0, Math.min(n - 1, i))
  const out: PlacedTile[] = []
  for (let x = inside(col(f.x0 - reach)); x <= inside(col(f.x0 + reach)); x++) {
    for (let y = inside(row(f.y0 + reach)); y <= inside(row(f.y0 - reach)); y++) {
      const xMin = -TILE_HALF_EXTENT_M + x * size
      const yMax = TILE_HALF_EXTENT_M - y * size
      const c = toGround(f, xMin + size / 2, yMax - size / 2)
      const rt = (size * Math.SQRT1_2) / f.k
      if (Math.abs(c.east) > halfWidthM + rt || Math.abs(c.north) > halfWidthM + rt) continue
      if (discRadiusM !== undefined) {
        const gap = (lo: number, hi: number) => (lo <= 0 && hi >= 0 ? 0 : Math.min(Math.abs(lo), Math.abs(hi)))
        const d = Math.hypot(gap(xMin - f.x0, xMin + size - f.x0), gap(yMax - size - f.y0, yMax - f.y0)) / f.k
        // A tile the disc only grazes, by less than one of its pixels, has nothing drawn in it (the
        // service answers 204, which a browser reads as a failed image), so it is left out.
        if (d > discRadiusM - size / TILE_PX / f.k) continue
      }
      out.push({ z, x, y, key: `${z}/${x}/${y}`, left: xMin - f.x0, top: -(yMax - f.y0), size })
    }
  }
  return out
}

/**
 * The tile style of the service's `sight` and `radio` layers (RGBA, 0 to 255), the same in
 * both themes: translucent, and the states told apart by pattern as well as tone, so a
 * legend swatch can be drawn to match. A test holds these to `app/core/viewshed.py`.
 */
export const TILE_STYLE = {
  clear: [79, 198, 224, 150],
  blocked: [20, 24, 29, 225],
  blockedStripe: [138, 149, 161, 255],
  uncertain: [200, 208, 216, 95],
  uncertainStripe: [20, 24, 29, 235],
  periodPx: 8,
  blockedStripePx: 3,
  uncertainStripePx: 2,
} as const

const css = (c: readonly number[]) => `rgba(${c[0]}, ${c[1]}, ${c[2]}, ${(c[3] / 255).toFixed(3)})`

/**
 * A CSS background that looks like a state's tiles: "in sight" filled, "blocked" dark with
 * 45° stripes, "uncertain" a light wash with −45° stripes. The stripes are `period / √2`
 * apart across, as the tiles' are in pixels along a row.
 */
export function tileSwatch(state: 'clear' | 'blocked' | 'uncertain'): string {
  const s = TILE_STYLE
  if (state === 'clear') return css(s.clear)
  const across = s.periodPx / Math.SQRT2
  const [base, stripe, width, angle] =
    state === 'blocked'
      ? ([s.blocked, s.blockedStripe, s.blockedStripePx, 135] as const)
      : ([s.uncertain, s.uncertainStripe, s.uncertainStripePx, 45] as const)
  const w = (width / Math.SQRT2).toFixed(2)
  return `repeating-linear-gradient(${angle}deg, ${css(stripe)} 0 ${w}px, ${css(base)} ${w}px ${across.toFixed(2)}px)`
}
