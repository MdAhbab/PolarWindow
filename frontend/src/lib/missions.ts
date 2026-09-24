import type {
  CoordinateKind,
  MissionSource,
  InstrumentType,
  Mission,
  MissionStatus,
  PublishedDate,
} from './api/adapters'
import type { Site } from './types'
import { dateWords, shortDate } from './format'

/**
 * The words the mission surfaces use for the API's enums.
 *
 * Colour discipline (§10): a mission's status is never amber, cyan or magenta,
 * because those mean sunlight, Earth contact and "over the survival limit".
 * Status is carried by a text label and a glyph, and the glyph is always
 * accompanied by the label, so neither shape nor colour carries it alone.
 */

export const STATUS_LABEL: Record<MissionStatus, string> = {
  planned: 'Planned',
  in_transit: 'In transit',
  operating: 'Operating',
  completed: 'Completed',
  partial_success: 'Partly successful',
  landing_failed: 'Landing failed',
  lost_before_landing: 'Lost before landing',
  cancelled: 'Cancelled',
  reassigned: 'Reassigned',
}

export const STATUS_GLYPH: Record<MissionStatus, string> = {
  planned: '○',
  in_transit: '→',
  operating: '●',
  completed: '✓',
  partial_success: '◐',
  landing_failed: '✕',
  lost_before_landing: '✕',
  cancelled: '⊘',
  reassigned: '↷',
}

/** The status Segmented: All · Flown · Upcoming, as the API's repeatable `status`. */
export type StatusFilter = 'all' | 'flown' | 'upcoming'

export const STATUS_GROUPS: Record<Exclude<StatusFilter, 'all'>, MissionStatus[]> = {
  flown: ['operating', 'completed', 'partial_success', 'landing_failed', 'lost_before_landing'],
  upcoming: ['planned', 'in_transit'],
}

/** The list's three groups, in the order the handoff draws them. */
export const LIST_GROUPS: { id: string; label: string; statuses: MissionStatus[] }[] = [
  { id: 'upcoming', label: 'Upcoming', statuses: STATUS_GROUPS.upcoming },
  { id: 'flown', label: 'Flown', statuses: STATUS_GROUPS.flown },
  { id: 'cancelled', label: 'Cancelled or reassigned', statuses: ['cancelled', 'reassigned'] },
]

/**
 * Instrument types, as chip labels. This is the project's own classification
 * of each payload's sourced purpose, not a NASA taxonomy (data-sources.md).
 */
export const INSTRUMENT_LABEL: Record<InstrumentType, string> = {
  volatiles: 'Volatiles',
  geology_geophysics: 'Geology and geophysics',
  heat_flow: 'Heat flow',
  radiation_space_weather: 'Radiation and space weather',
  exosphere_dust: 'Exosphere and dust',
  imaging: 'Imaging',
  landing_navigation: 'Landing and navigation',
  communications: 'Communications',
  laser_retroreflector: 'Laser retroreflector',
  rover_mobility: 'Rover and mobility',
  technology_demo: 'Technology demonstration',
  other: 'Other',
}

export const INSTRUMENT_TYPES = Object.keys(INSTRUMENT_LABEL) as InstrumentType[]

export function isInstrumentType(v: string): v is InstrumentType {
  return v in INSTRUMENT_LABEL
}

export function coordinateKindWords(kind: CoordinateKind, featureName?: string | null): string {
  switch (kind) {
    case 'actual_landing':
      return 'actual landing point'
    case 'planned_target':
      return 'planned target'
    case 'feature_centre':
      return featureName ? `centre of ${featureName}, not a landing point` : 'feature centre, not a landing point'
  }
}

/** A source's own phrase, without the editorial brackets it carries ("[CST]"). */
export function cleanPhrase(s: string): string {
  return s.replace(/[[\]]/g, '').replace(/\s+/g, ' ').trim()
}

const hhmm = (ms: number) => {
  const d = new Date(ms)
  return `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')} UTC`
}

/**
 * A published date as the screen shows it.
 *
 * Known to the minute or the day, the date itself is written in words: "6 Mar
 * 2025, 17:30 UTC", "22 Feb 2024" (`long` spells the month, for accessible
 * names). Known only to the month, quarter or year, there is no date to write,
 * so the source's own phrase is shown with how precisely it is known: "late
 * 2027 (known to the year)". The phrase never carries its square brackets.
 */
export function publishedWords(d: PublishedDate, long = false): string {
  const day = long ? dateWords : shortDate
  if (d.precision === 'minute') return `${day(d.startMs)}, ${hhmm(d.startMs)}`
  if (d.precision === 'day') return day(d.startMs)
  return `${cleanPhrase(d.asPublished)} (known to the ${d.precision})`
}

/** The tooltip for a date written in words: the phrase as the source published it. */
export function publishedTitle(d: PublishedDate): string | undefined {
  return d.precision === 'minute' || d.precision === 'day' ? `As published: ${cleanPhrase(d.asPublished)}` : undefined
}

/**
 * The date the list and timeline place a mission at: its landing, else its
 * launch (a mission lost before landing has only a launch). Same rule as the
 * API's `from`/`to` filters.
 */
export function missionDate(m: Mission): { which: 'landing' | 'launch'; date: PublishedDate } | null {
  if (m.landing) return { which: 'landing', date: m.landing }
  if (m.launch) return { which: 'launch', date: m.launch }
  return null
}

export function missionDateWords(m: Mission): string {
  const d = missionDate(m)
  if (!d) return 'landing date unconfirmed'
  const verb =
    d.which === 'landing'
      ? m.status === 'planned' || m.status === 'in_transit'
        ? 'landing'
        : 'landed'
      : m.status === 'planned' || m.status === 'in_transit'
        ? 'launch'
        : 'launched'
  return `${verb} ${publishedWords(d.date, true)}`
}

/**
 * The list row's accessible name, in the handoff's order: "{name}, {provider},
 * {landing date in words with its precision}, {status}, carries {instrument
 * types}". Every part comes from the record; a missing provider is said to be
 * unconfirmed, never skipped.
 */
export function missionAccessibleName(m: Mission): string {
  const parts = [
    m.name,
    m.provider ?? 'provider unconfirmed',
    missionDateWords(m),
    STATUS_LABEL[m.status],
    m.payloadTypes.length
      ? `carries ${m.payloadTypes.map((t) => INSTRUMENT_LABEL[t].toLowerCase()).join(', ')}`
      : 'payloads unconfirmed',
  ]
  if (m.unconfirmedFields.length) parts.push('some details unconfirmed')
  return parts.join(', ')
}

const DEG = Math.PI / 180

/**
 * Central angle between two points on a sphere, radians (haversine). The one
 * client-side derivation the product allows: it only *chooses* which
 * candidates to compare against, and the choice is labelled "nearest by
 * distance". No distance is ever shown as a number.
 */
export function centralAngle(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const dLat = (lat2 - lat1) * DEG
  const dLon = (lon2 - lon1) * DEG
  const a =
    Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * DEG) * Math.cos(lat2 * DEG) * Math.sin(dLon / 2) ** 2
  return 2 * Math.asin(Math.min(1, Math.sqrt(a)))
}

/** The `n` candidate sites nearest a point by great-circle distance, nearest first. */
export function nearestCandidates(
  latDeg: number,
  lonDeg: number,
  sites: Site[],
  n = 3,
  exclude?: string,
): Site[] {
  return sites
    .filter((s) => s.kind === 'candidate' && s.id !== exclude)
    .map((s) => ({ s, d: centralAngle(latDeg, lonDeg, s.latDeg, s.lonDeg) }))
    .sort((a, b) => a.d - b.d || a.s.id.localeCompare(b.s.id))
    .slice(0, n)
    .map((x) => x.s)
}

const baseDomain = (url: string): string | null => {
  try {
    return new URL(url).hostname.split('.').slice(-2).join('.')
  } catch {
    return null
  }
}

/**
 * The name a source link carries: its publisher, never "link" (§10.3). A
 * payload's page is often not itself in the mission's source list
 * (science.nasa.gov beside www.nasa.gov), so a source on the same domain
 * names it; failing that, the host name does.
 */
export function publisherFor(url: string, sources: MissionSource[]): string {
  const exact = sources.find((s) => s.url === url)
  if (exact) return exact.publisher
  const base = baseDomain(url)
  const same = base ? sources.find((s) => baseDomain(s.url) === base) : undefined
  if (same) return same.publisher
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}
