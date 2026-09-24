import type { Face } from './types'

/**
 * The approximation mark. It is no longer printed before every value (U13):
 * seven per screen was noise, and at 375 px it pushed the 64 px numbers
 * against the tile edge. Instead each screen carries one line, `ESTIMATES`,
 * and the marks that make a real claim stay: "≥" for a lower bound and "±"
 * for a timing margin.
 */
export const APPROX = '≈'

/** The one line per screen that replaces the per-value "≈" (U13). */
export const ESTIMATES =
  'All figures are estimates from the lunar elevation model and the ephemeris, not flight values. “≥” marks a value the window cut short; “±” is its timing margin.'

/**
 * A value the window cut short. The night (or blackout) began before the window
 * opened or runs on after it closes, so the figure is a lower bound — and "≈"
 * would claim it is the stretch itself.
 */
export const AT_LEAST = '≥'

export const bound = (open?: boolean): string => (open ? AT_LEAST : '')

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

/** A timing margin. Below what the digits can show it reads "±<0.1", never "±0.0". */
export function plusMinus(v: number, digits = 1): string {
  const floor = 0.5 * 10 ** -digits
  return v < floor ? `±<${(2 * floor).toFixed(digits)}` : `±${v.toFixed(digits)}`
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

const MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
]
const pad2 = (n: number) => String(n).padStart(2, '0')

/** "14 March 2027": a date in words, UTC. */
export function dateWords(ms: number): string {
  const d = new Date(ms)
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`
}

/** "14 Mar 2027": the same, short, for dense lines. */
export function shortDate(ms: number): string {
  const d = new Date(ms)
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()].slice(0, 3)} ${d.getUTCFullYear()}`
}

/** "6 March 2025, 17:30 UTC"; the time is left off at midnight. */
export function dateTimeWords(ms: number): string {
  const d = new Date(ms)
  const t = d.getUTCHours() || d.getUTCMinutes() ? `, ${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())} UTC` : ''
  return `${dateWords(ms)}${t}`
}

/** "March 2027". */
export function monthWords(ms: number): string {
  const d = new Date(ms)
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`
}

/**
 * A moment inside a window, the way a person says it (U10):
 * "Day 12, 26 March, 09:00 UTC".
 *
 * Screen readers read an ISO stamp ("2027-03-26 09:00Z") character by
 * character, so this is what the screen shows and what `aria-valuetext`
 * speaks; ISO stays in the exports. The day counts whole days elapsed since
 * the window opened, as the ring's "DAY n OF m" dial does. The year is added
 * only when the moment falls in a different year from the window's start,
 * which is the one case where "26 March" alone would be ambiguous.
 */
export function humanStamp(originMs: number, hFromOrigin: number): string {
  const ms = originMs + Math.round(hFromOrigin * 3600) * 1000
  const d = new Date(ms)
  const day = Math.floor(hFromOrigin / 24)
  const year = d.getUTCFullYear() !== new Date(originMs).getUTCFullYear() ? ` ${d.getUTCFullYear()}` : ''
  return `Day ${day}, ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}${year}, ${pad2(d.getUTCHours())}:${pad2(
    d.getUTCMinutes(),
  )} UTC`
}

/** `humanStamp` for a moment given in model hours, inside a window that opens at `windowStartH`. */
export function humanStampH(tH: number, windowStartH: number): string {
  return humanStamp(MODEL_EPOCH + windowStartH * 3_600_000, tH - windowStartH)
}

/** Model hours (hours from the model epoch) to epoch milliseconds. */
export function msFromModelH(tH: number): number {
  return MODEL_EPOCH + tH * 3_600_000
}

/** Epoch milliseconds to model hours: the unit the store keeps the window in. */
export function modelHFromMs(ms: number): number {
  return (ms - MODEL_EPOCH) / 3_600_000
}

/** A window's length in words: "30 days", "29.5 days", "13 hours". */
export function spanWords(hours: number): string {
  if (hours < 48) {
    const h = Math.round(hours * 4) / 4
    return `${h} ${h === 1 ? 'hour' : 'hours'}`
  }
  const days = hours / 24
  const shown = Math.abs(days - Math.round(days)) < 0.05 ? String(Math.round(days)) : days.toFixed(1)
  return `${shown} days`
}

/** "30 days from 14 Mar 2027" (§10.4). */
export function windowLine(startMs: number, hours: number): string {
  return `${spanWords(hours)} from ${shortDate(startMs)}`
}

/** A published date's precision, in words that say how much is known. */
export function precisionWords(p: 'minute' | 'day' | 'month' | 'quarter' | 'year'): string {
  switch (p) {
    case 'minute':
      return 'to the minute'
    case 'day':
      return 'to the day'
    case 'month':
      return 'to the month'
    case 'quarter':
      return 'to the quarter'
    case 'year':
      return 'to the year'
  }
}

/** "23 September 2026" from an ISO date ("2026-09-23"). */
export function isoDateWords(iso: string): string {
  const ms = Date.parse(iso.length === 10 ? `${iso}T00:00:00Z` : iso)
  return Number.isNaN(ms) ? iso : dateWords(ms)
}

/** Hours from the model epoch to a UTC stamp, ISO-like. Exports and logs only (U10). */
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
  const lead = open ? 'at least ' : 'about '
  if (days < 1.5) return `${lead}${Math.round(h)} hours`
  return `${lead}${days.toFixed(days < 10 ? 1 : 0)} days`
}

/**
 * The label a number carries (U14): the plain words by default, on every
 * face, and the expert term as a second line in Expert only. One
 * concept, one name, wherever it appears.
 */
export function termLabel(key: string, face: Face): { label: string; expert?: string } {
  const t = TERM[key]
  return { label: t.public, expert: face === 'planner' ? t.planner : undefined }
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

/**
 * The timing margin of a gap's edges, in words, for the sentences that quote
 * it. A smooth-Moon skyline (outside the terrain model) has no height error,
 * so its zero is not a margin, and a gap whose ends are both the window's has
 * no edge to time; both say so instead of printing "±0.00 h".
 */
export function edgeMargin(
  arc: { toleranceH: number; startToleranceH?: number; endToleranceH?: number } | undefined,
  terrainModelled: boolean,
): string {
  if (!arc) return 'no margin: there is no gap in this window'
  if (!terrainModelled) return 'no margin that can be stated, because terrain is not modelled here'
  if (arc.startToleranceH === undefined && arc.endToleranceH === undefined)
    return 'no margin: both of its ends are the window’s own edges'
  return `${plusMinus(arc.toleranceH, 2)} h`
}
