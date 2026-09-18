import type { Face } from './types'

/**
 * Every derived value carries the tilde. It is not decoration: these numbers
 * come from a synthetic elevation model and a mean-element ephemeris, and
 * nothing in this build should be mistaken for a flight value.
 */
export const APPROX = '≈'

export function hours(v: number, digits = 0): string {
  return `${APPROX}${v.toFixed(digits)}`
}

export function hoursWithUnit(v: number, digits = 0): string {
  return `${hours(v, digits)} h`
}

export function plusMinus(v: number, digits = 1): string {
  return `±${v.toFixed(digits)}`
}

export function percent(fraction: number): string {
  return `${Math.round(fraction * 100)}%`
}

export function degrees(v: number, digits = 2): string {
  return `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(digits)}°`
}

export function bearing(v: number): string {
  return `${Math.round(((v % 360) + 360) % 360)}°`
}

export function coords(latDeg: number, lonDeg: number): string {
  const ns = latDeg < 0 ? 'S' : 'N'
  const ew = lonDeg < 0 ? 'W' : 'E'
  return `${Math.abs(latDeg).toFixed(4)}°${ns} ${Math.abs(lonDeg).toFixed(4)}°${ew}`
}

/** Compass point for a bearing, for the public face and for alt text. */
export function compass(deg: number): string {
  const names = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
  const i = Math.round((((deg % 360) + 360) % 360) / 22.5) % 16
  return names[i]
}

const MODEL_EPOCH = Date.UTC(2027, 2, 14, 0, 0, 0)

/** Hours from the model epoch to a UTC stamp, for display only. */
export function clockUTC(tH: number): string {
  const d = new Date(MODEL_EPOCH + tH * 3600_000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:00Z`
}

export function shortDateUTC(tH: number): string {
  const d = new Date(MODEL_EPOCH + tH * 3600_000)
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${d.getUTCDate()} ${months[d.getUTCMonth()]}`
}

export function dayOf(tH: number, windowStartH: number): number {
  return Math.floor((tH - windowStartH) / 24)
}

/**
 * The public face says units in words. Same fact, different vocabulary —
 * simplifying the words never simplifies the claim.
 */
export function humanDuration(h: number, face: Face): string {
  if (face !== 'public') return hoursWithUnit(h)
  const days = h / 24
  if (days < 1.5) return `${APPROX}${Math.round(h)} hours`
  return `${APPROX}${days.toFixed(days < 10 ? 1 : 0)} days`
}

export const TERM: Record<string, Record<Face, string>> = {
  sunHours: {
    planner: 'Sunlight in window',
    educator: 'Time in sunlight',
    public: 'Time in the Sun',
  },
  earthHours: {
    planner: 'Earth contact (DTE)',
    educator: 'Time able to reach Earth',
    public: 'Time it can call home',
  },
  longestDark: {
    planner: 'Longest unbroken dark gap',
    educator: 'Longest night',
    public: 'Longest night',
  },
  longestBlackout: {
    planner: 'Longest RF blackout',
    educator: 'Longest time out of contact',
    public: "Longest time it can't call home",
  },
}
