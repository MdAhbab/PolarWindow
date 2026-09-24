/**
 * Where the Sun is overhead, recovered from a site's own Sun track.
 *
 * The API's timeline gives the Sun's azimuth and elevation at a site at every
 * sample, computed with SPICE and DE440. Turning that direction back into the
 * Moon-fixed frame gives the sub-solar point exactly (the parallax of a site
 * 1,737 km from the Moon's centre, seen from 150 million km, is under a
 * thousandth of a degree). The map's shadow line is drawn from this, so it
 * shows the same Sun every number on screen was computed with.
 *
 * It replaced a mean-element model that put the Sun in the wrong hemisphere
 * for the whole of 2027: the southern summer it assumed is a southern winter.
 */
import type { TimelineDTO } from './api/client'

export interface SubPoint {
  latDeg: number
  /** Degrees east, 0–360. */
  lonDeg: number
}

const DEG = Math.PI / 180

/**
 * The sub-solar point from a site's latitude and longitude and the Sun's
 * azimuth (from true north, clockwise) and elevation there.
 */
export function subSolarFromLook(siteLatDeg: number, siteLonDeg: number, azDeg: number, elDeg: number): SubPoint {
  const lat = siteLatDeg * DEG
  const lon = siteLonDeg * DEG
  const az = azDeg * DEG
  const el = elDeg * DEG
  // Local east, north and up in the Moon-fixed frame.
  const e = [-Math.sin(lon), Math.cos(lon), 0]
  const n = [-Math.sin(lat) * Math.cos(lon), -Math.sin(lat) * Math.sin(lon), Math.cos(lat)]
  const u = [Math.cos(lat) * Math.cos(lon), Math.cos(lat) * Math.sin(lon), Math.sin(lat)]
  const ce = Math.cos(el) * Math.sin(az)
  const cn = Math.cos(el) * Math.cos(az)
  const cu = Math.sin(el)
  const v = [0, 1, 2].map((k) => ce * e[k] + cn * n[k] + cu * u[k])
  const len = Math.hypot(v[0], v[1], v[2])
  return {
    latDeg: Math.asin(v[2] / len) / DEG,
    lonDeg: ((Math.atan2(v[1], v[0]) / DEG) % 360 + 360) % 360,
  }
}

/** The sub-solar point at an instant inside a timeline's span; null outside it. */
export function subSolarAt(
  tl: Pick<TimelineDTO, 'start' | 't_s' | 'sun'>,
  siteLatDeg: number,
  siteLonDeg: number,
  atMs: number,
): SubPoint | null {
  const n = tl.t_s.length
  if (!n) return null
  const offsetS = (atMs - Date.parse(tl.start)) / 1000
  const step = n > 1 ? tl.t_s[1] - tl.t_s[0] : 1
  const i = Math.round((offsetS - tl.t_s[0]) / step)
  if (i < 0 || i >= n) return null
  return subSolarFromLook(siteLatDeg, siteLonDeg, tl.sun.az_deg[i], tl.sun.el_deg[i])
}
