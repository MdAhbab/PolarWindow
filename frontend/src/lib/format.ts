import type { Face } from './types'

/**
 * Every derived value carries the tilde. It is not decoration: the numbers are
 * computed from a 20 m elevation model with metres of vertical error, and
 * nothing in this build should be mistaken for a flight value.
 */
export const APPROX = '≈'

/**
 * A value the window cut short. The night (or blackout) began before the window
 * opened or runs on after it closes, so the figure is a lower bound — and "≈"
 * would claim it is the stretch itself.
 */
export const AT_LEAST = '≥'

export const bound = (open?: boolean): string => (open ? AT_LEAST : APPROX)

export function hours(v: number, digits = 0, open?: boolean): string {
  return `${bound(open)}${v.toFixed(digits)}`
}

export function hoursWithUnit(v: number, digits = 0, open?: boolean): string {
  return `${hours(v, digits, open)} h`
}

/** The same value, spoken: "about 122 hours", "at least 288 hours". */
export function hoursSpoken(v: number, open?: boolean): string {
  return `${open ? 'at least' : 'about'} ${Math.round(v)} hours`
}

export function plusMinus(v: number, digits = 1): string {
  return `±${v.toFixed(digits)}`
}

export function percent(fraction: number): string {
  return `${APPROX}${Math.round(fraction * 100)}%`
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
export function humanDuration(h: number, face: Face, open?: boolean): string {
  if (face !== 'public') return hoursWithUnit(h, 0, open)
  const days = h / 24
  const lead = open ? 'at least ' : APPROX
  if (days < 1.5) return `${lead}${Math.round(h)} hours`
  return `${lead}${days.toFixed(days < 10 ? 1 : 0)} days`
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
