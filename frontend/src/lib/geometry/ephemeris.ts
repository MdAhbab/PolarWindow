/**
 * A mean-element lunar ephemeris, retained for ONE purpose: the schematic
 * terminator drawn across the polar map.
 *
 * Every number the product reports now comes from the API, which uses SPICE
 * and de440. This file is not that, and must not become that again. It survives
 * because the terminator overlay needs a sub-solar longitude for the whole
 * globe rather than a look angle at one site, and the map is already documented
 * as schematic -- its hillshade covers ~300 km at a different resolution than
 * the per-site 20 km DEM.
 *
 * If the terminator ever needs to be accurate, the right fix is a sub-solar
 * point on the timeline response, not a better model here.
 */

const DEG = Math.PI / 180
const RAD = 180 / Math.PI
const TAU = Math.PI * 2

/** Synodic month — one lunar day, the period of the Sun's azimuth sweep. */
export const SYNODIC_HOURS = 708.734

/** The Moon's axial tilt to the ecliptic. The whole reason the poles are strange. */
const OBLIQUITY_DEG = 1.5424

/** The Moon goes round the Sun with the Earth, so the seasons take a year. */
const SOLAR_YEAR_HOURS = 8766.0

/** Optical libration in latitude — draconic month. */
const LIB_LAT_AMP_DEG = 6.69
const LIB_LAT_PERIOD_H = 27.212 * 24

/** Optical libration in longitude — anomalistic month. */
const LIB_LON_AMP_DEG = 7.9
const LIB_LON_PERIOD_H = 27.554 * 24

/**
 * Model epoch offset, hours. Chosen so the default window sits in southern
 * summer, where the Sun stays a degree or two ABOVE the flat horizon all month
 * and terrain alone decides who is lit. That is the interesting case, and the
 * one the whole product is about.
 */
export const EPOCH_OFFSET_H = SOLAR_YEAR_HOURS * 0.75

export interface SubPoint {
  latDeg: number
  lonDeg: number
}

export function subSolarPoint(tH: number): SubPoint {
  const t = tH + EPOCH_OFFSET_H
  return {
    latDeg: OBLIQUITY_DEG * Math.sin((TAU * t) / SOLAR_YEAR_HOURS),
    lonDeg: wrap180(180 - (360 * t) / SYNODIC_HOURS),
  }
}

export function subEarthPoint(tH: number): SubPoint {
  const t = tH + EPOCH_OFFSET_H
  return {
    latDeg: LIB_LAT_AMP_DEG * Math.sin((TAU * t) / LIB_LAT_PERIOD_H + 0.62),
    lonDeg: LIB_LON_AMP_DEG * Math.sin((TAU * t) / LIB_LON_PERIOD_H + 1.31),
  }
}

export interface LookAngles {
  azDeg: number
  elDeg: number
}

/**
 * Azimuth and elevation of a sub-point, seen from a site, both in degrees.
 *
 * Built from unit vectors rather than the usual spherical trig, because near
 * the pole cos(latitude) goes to zero and the textbook azimuth formula loses
 * all its precision exactly where this product needs it.
 */
export function lookAngles(
  siteLatDeg: number,
  siteLonDeg: number,
  target: SubPoint,
): LookAngles {
  const phi = siteLatDeg * DEG
  const lam = siteLonDeg * DEG
  const cphi = Math.cos(phi)
  const sphi = Math.sin(phi)
  const clam = Math.cos(lam)
  const slam = Math.sin(lam)

  // Site's outward normal, and its local east/north basis.
  const upX = cphi * clam
  const upY = cphi * slam
  const upZ = sphi
  const eastX = -slam
  const eastY = clam
  // north = up x east
  const northX = -sphi * clam
  const northY = -sphi * slam
  const northZ = cphi

  const tphi = target.latDeg * DEG
  const tlam = target.lonDeg * DEG
  const ctphi = Math.cos(tphi)
  const sx = ctphi * Math.cos(tlam)
  const sy = ctphi * Math.sin(tlam)
  const sz = Math.sin(tphi)

  const e = sx * eastX + sy * eastY
  const n = sx * northX + sy * northY + sz * northZ
  const u = sx * upX + sy * upY + sz * upZ

  return {
    azDeg: wrap360(Math.atan2(e, n) * RAD),
    elDeg: Math.asin(Math.max(-1, Math.min(1, u))) * RAD,
  }
}

export function bodyLookAngles(
  body: 'sun' | 'earth',
  siteLatDeg: number,
  siteLonDeg: number,
  tH: number,
): LookAngles {
  const sub = body === 'sun' ? subSolarPoint(tH) : subEarthPoint(tH)
  return lookAngles(siteLatDeg, siteLonDeg, sub)
}

export function wrap360(d: number): number {
  const r = d % 360
  return r < 0 ? r + 360 : r
}

export function wrap180(d: number): number {
  const r = wrap360(d)
  return r > 180 ? r - 360 : r
}
