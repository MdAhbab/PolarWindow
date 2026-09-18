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
 *
 * Only the sub-solar point remains. The sub-Earth point and the site look
 * angles that used to sit beside it were unused once every number moved to
 * the API, and client-side astronomy that nothing calls is an invitation to
 * start calling it.
 */

const TAU = Math.PI * 2

/** Synodic month — one lunar day, the period of the Sun's azimuth sweep. */
export const SYNODIC_HOURS = 708.734

/** The Moon's axial tilt to the ecliptic. The whole reason the poles are strange. */
const OBLIQUITY_DEG = 1.5424

/** The Moon goes round the Sun with the Earth, so the seasons take a year. */
const SOLAR_YEAR_HOURS = 8766.0

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

export function wrap180(d: number): number {
  const r = ((d % 360) + 360) % 360
  return r > 180 ? r - 360 : r
}
