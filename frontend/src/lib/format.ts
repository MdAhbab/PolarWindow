
/**
 * The one line per screen that replaces the "≈" once printed before every
 * value (U13): seven per screen was noise, and at 375 px it pushed the 64 px
 * numbers against the tile edge. The marks that make a real claim stay: "≥"
 * for a lower bound and "±" for a timing margin.
 */
export const ESTIMATES =
  'Estimates from a terrain map and calculated Sun and Earth positions, not lander readings. “≥” means the dates cut the value short; “±” is how far the timing could be off.'

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

/** The same compass point in words, for sentences: "south-south-east". */
export function compassWords(deg: number): string {
  const words: Record<string, string> = { N: 'north', E: 'east', S: 'south', W: 'west' }
  const p = compass(deg)
  // "SSE" -> "south-south-east"; "NE" -> "north-east"; "S" -> "south".
  return p.length === 3
    ? `${words[p[0]]}-${words[p[1]]}${words[p[2]]}`.replace(/(north|south)(east|west)$/, '$1-$2')
    : p.split('').map((c) => words[c]).join('-')
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
export function precisionWords(p: 'second' | 'minute' | 'day' | 'month' | 'quarter' | 'year'): string {
  switch (p) {
    case 'second':
      return 'to the second'
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

/**
 * What each of the four numbers is called, what it means in one sentence, and
 * the professional term where there is one. The plain name is the only label
 * on screen; the meaning and the other name open from the number itself.
 */
export const TERM: Record<string, { label: string; means: string; also?: string }> = {
  sunHours: {
    label: 'Time in sunlight',
    means: 'Hours the Sun is above this spot’s own skyline on the chosen dates: the time the solar panels can charge.',
  },
  earthHours: {
    label: 'Time in contact with Earth',
    means: 'Hours Earth is above the skyline, so the lander can radio home directly.',
    also: 'Direct-to-Earth (DTE) contact',
  },
  longestDark: {
    label: 'Longest night',
    means: 'The longest single stretch without sunlight. The lander lives on its batteries until the Sun returns.',
  },
  longestBlackout: {
    label: 'Longest time without contact',
    means: 'The longest single stretch with Earth out of sight. The lander has to work alone until Earth rises again.',
    also: 'radio (RF) blackout',
  },
}

/**
 * The lifecycle sections' key numbers, in the same form: the plain name on
 * screen, the meaning and the professional name when the label is pressed.
 */
Object.assign(TERM, {
  itemsReady: {
    label: 'Items ready',
    means: 'Items that have reached the last step, ready, out of every item entered for this mission. A count, not a score.',
  },
  blocked: {
    label: 'Blocked',
    means: 'Items that cannot move on until something outside them changes. Each one says why.',
  },
  nextMilestone: {
    label: 'Next milestone',
    means: 'The next review or delivery still to come, and how far its date could move.',
  },
  spares: {
    label: 'Spare parts',
    means: 'Flight spares still on hand to replace a part that is lost, damaged or fails.',
  },
  launchTime: {
    label: 'Launch time',
    means: 'When this launch opportunity opens, worked out from where the Moon will be and where the pad is.',
    also: 'T-0',
  },
  flightTime: {
    label: 'Flight time',
    means: 'Days from launch to landing on this opportunity, including the wait in orbit around the Moon.',
    also: 'time of flight',
  },
  sunAtLanding: {
    label: 'Sun height at landing',
    means: 'How high the Sun stands above the landing spot’s horizon at touchdown. A low Sun casts long shadows that hide hazards from the landing cameras.',
    also: 'solar elevation angle',
  },
  sunlightAfterLanding: {
    label: 'Sunlight after landing',
    means: 'Hours of sunlight at the landing spot from touchdown until the Sun first sets.',
  },
  tripSunlight: {
    label: 'Time in sunlight',
    means: 'Hours of the trip with the Sun not hidden by Earth or the Moon: the time the solar panels can charge.',
  },
  tripHeard: {
    label: 'Time a ground station can hear it',
    means: 'Hours of the trip when at least one ground station has the spacecraft above its own horizon.',
    also: 'ground-station coverage',
  },
  tripShadow: {
    label: 'Longest time in shadow',
    means: 'The longest single stretch in Earth’s or the Moon’s shadow, running on batteries.',
    also: 'longest eclipse',
  },
  tripUnheard: {
    label: 'Longest time without contact',
    means: 'The longest single stretch of the trip that no ground station can hear.',
    also: 'radio (RF) blackout',
  },
  stationHears: {
    label: 'Time a ground station can hear the lander',
    means: 'Hours when Earth is above the lander’s skyline and the Moon is above a ground station’s own horizon, both at once.',
    also: 'view period',
  },
  viaRelay: {
    label: 'Through a relay',
    means: 'Hours the lander could reach Earth through a relay satellite: the relay in view of the lander and of Earth at once. A range, because the relay has no published position in its orbit yet.',
    also: 'relayed contact',
  },
  contactUnheard: {
    label: 'Longest time without contact',
    means: 'The longest single stretch with no way to reach Earth, directly or through a relay.',
    also: 'radio (RF) blackout',
  },
  messageWait: {
    label: 'Longest message wait',
    means: 'The longest a message from the lander waits before some path can carry it to Earth.',
    also: 'end-to-end latency',
  },
  boosterWaves: {
    label: 'Waves at the booster landing zone',
    means: 'Forecast wave height where the booster comes down, to set beside the team’s limit.',
    also: 'significant wave height',
  },
  boosterWind: {
    label: 'Wind at the booster landing zone',
    means: 'Forecast wind speed where the booster comes down, to set beside the team’s limit.',
  },
  capsuleWaves: {
    label: 'Waves at the splashdown zone',
    means: 'Forecast wave height where a returning capsule comes down, to set beside the team’s limit.',
    also: 'significant wave height',
  },
  capsuleWind: {
    label: 'Wind at the splashdown zone',
    means: 'Forecast wind speed where a returning capsule comes down, to set beside the team’s limit.',
  },
} satisfies Record<string, { label: string; means: string; also?: string }>)

export function termLabel(key: string): { label: string; means: string; also?: string } {
  return TERM[key]
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
  if (!arc) return 'no margin: there is no gap in these dates'
  if (!terrainModelled) return 'no margin that can be stated, because there is no terrain data here'
  if (arc.startToleranceH === undefined && arc.endToleranceH === undefined)
    return 'no margin: it starts and ends at the edges of the chosen dates'
  return `${plusMinus(arc.toleranceH, 2)} h`
}
