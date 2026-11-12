import type { SiteMetrics } from '../types'

/**
 * The battery limit, hours, when the team has not entered one: the longest
 * night a lander is assumed to last on its battery. It is assumed, not
 * published or measured. The team's own value is the `battery_limit_h`
 * parameter (Settings, Parameters), which the backend returns empty, with
 * its reason, until someone enters it.
 *
 * No screen imports this. Screens read `useBatteryLimit()`
 * (lib/api/lifecycleQueries.ts), which gives the entered value when there is
 * one and this one, marked assumed, when there is not; the words come from
 * `limitWords` here and `LimitPhrase` in components/KeyNumbers.tsx, which
 * say "(assumed)" and draw the scenario hatch.
 */
export const ASSUMED_BATTERY_LIMIT_H = 120

/**
 * @deprecated The old name, kept only so the two screens outside this
 * package still build (`MapScreen.tsx`, `MissionDetailScreen.tsx`). They move
 * to `useBatteryLimit()`; nothing new reads this.
 */
export const SURVIVAL_LIMIT_H = ASSUMED_BATTERY_LIMIT_H

/** The battery limit a night is compared with, and where it comes from. */
export interface BatteryLimit {
  /** Hours. */
  h: number
  /** Entered by the team (Settings, Parameters), or assumed because none is entered or it could not be read. */
  basis: 'entered' | 'assumed'
  /** Who entered it, when the service says. */
  by?: string
  /** Why it is assumed, in the service's words when it gave them. */
  why?: string
  /** The parameters have not answered yet: nothing should be said about the limit. */
  pending?: boolean
}

/** "96", "96.5": an entered limit as the team typed it, to a tenth of an hour. */
export const limitHours = (h: number): string => String(Math.round(h * 10) / 10)

export const ASSUMED_LIMIT: BatteryLimit = {
  h: ASSUMED_BATTERY_LIMIT_H,
  basis: 'assumed',
  why: `No battery limit has been entered, so ${limitHours(ASSUMED_BATTERY_LIMIT_H)} h is assumed.`,
}

/** A figure never parts from its unit or its margin at a line end. */
const NBSP = ' '

/** "the 96 h battery limit your team entered" or "the 120 h battery limit (assumed)". */
export function limitWords(l: BatteryLimit): string {
  return l.basis === 'entered'
    ? `the ${limitHours(l.h)}${NBSP}h battery limit your team entered`
    : `the ${limitHours(l.h)}${NBSP}h battery limit (assumed)`
}

/** Spoken: units as words, and "assumed" said, not bracketed. */
export function limitSpoken(l: BatteryLimit): string {
  const h = limitHours(l.h)
  return l.basis === 'entered'
    ? `the ${h} hour battery limit your team entered`
    : `the ${h} hour battery limit, which is assumed`
}

/** A night, as the comparison with the limit needs it. */
export interface Night {
  /** Hours; a lower bound when `open`. */
  h: number
  /** The chosen dates cut it short: the real night is longer. */
  open: boolean
  /** Its margin (±), hours, when one can be stated; none for a grazing edge or a night with no timed edge. */
  marginH?: number
  /** There was no night on these dates. */
  none?: boolean
}

/**
 * Where a night stands against the battery limit, using the night's margin.
 * Only `past` is over the limit (magenta); `within-margin` is neither over
 * nor inside, and says so.
 */
export type AgainstLimit =
  | { kind: 'no-night' }
  /** Longer than the limit by more than its margin. `atLeast`: the dates cut it short, so by at least this. */
  | { kind: 'past'; byH: number; marginH?: number; atLeast: boolean }
  /** Shorter than the limit by more than its margin, and not cut short. */
  | { kind: 'inside'; byH: number; marginH?: number }
  /** The difference from the limit is no larger than the night's margin. */
  | { kind: 'within-margin'; byH: number; marginH: number }
  /** Cut short by the dates and shorter than the limit: the real night may run past it. */
  | { kind: 'cut-short' }

export function nightAgainstLimit(n: Night, limitH: number): AgainstLimit {
  if (n.none || (n.h <= 0 && !n.open)) return { kind: 'no-night' }
  const d = n.h - limitH
  const margin = n.marginH !== undefined && n.marginH > 0 ? n.marginH : undefined
  if (margin !== undefined && Math.abs(d) <= margin) return { kind: 'within-margin', byH: Math.abs(d), marginH: margin }
  if (d > 0) return { kind: 'past', byH: d, marginH: margin, atLeast: n.open }
  if (n.open) return { kind: 'cut-short' }
  return { kind: 'inside', byH: -d, marginH: margin }
}

/**
 * The longest night's margin as the screens show it: none for a grazing edge
 * (it cannot be timed), none for a night whose ends are both the dates' own,
 * and none where the skyline is a smooth sphere (the tolerance there is zero
 * by construction, not a measured margin).
 */
export function nightMargin(m: SiteMetrics, terrainModelled = true): number | undefined {
  const arc = m.sun.longestDownArc
  if (!arc || arc.grazing || !terrainModelled) return undefined
  if (arc.startToleranceH === undefined && arc.endToleranceH === undefined) return undefined
  return m.sun.longestDownToleranceH
}

/** A site's longest night, ready for `nightAgainstLimit`. */
export function longestNight(m: SiteMetrics, terrainModelled = true): Night {
  return {
    h: m.sun.longestDownH,
    open: Boolean(m.sun.longestDownOpen),
    marginH: nightMargin(m, terrainModelled),
    none: !m.sun.longestDownArc && !m.sun.longestDownOpen,
  }
}

/** "56 ±2.3 h", "606 h": a difference with the night's margin, as the tiles write a value. */
export function hoursWithMargin(h: number, marginH?: number): string {
  if (marginH === undefined || marginH <= 0) return `${Math.round(h)}${NBSP}h`
  const pm = marginH < 0.05 ? '±<0.1' : `±${marginH.toFixed(1)}`
  return `${Math.round(h)}${NBSP}${pm}${NBSP}h`
}

/**
 * The words before the limit's phrase, lower case: "56 ±2.3 h inside ",
 * "at least 168 h past ", "within the margin of ". Null when there was no
 * night, which says so in its own words.
 */
export function againstLimitLead(a: AgainstLimit): string | null {
  switch (a.kind) {
    case 'no-night':
      return null
    case 'past':
      return `${a.atLeast ? 'at least ' : ''}${hoursWithMargin(a.byH, a.marginH)} past `
    case 'inside':
      return `${hoursWithMargin(a.byH, a.marginH)} inside `
    case 'within-margin':
      return 'within the margin of '
    case 'cut-short':
      return 'these dates cut this night short; it may run past '
  }
}

/** The whole comparison as plain text: "56 ±2.3 h inside the 120 h battery limit (assumed)". */
export function againstLimitText(a: AgainstLimit, l: BatteryLimit): string | null {
  const lead = againstLimitLead(a)
  return lead === null ? null : `${lead}${limitWords(l)}`
}

/** The sites of a comparison, grouped by where each one's longest night stands against the limit. */
export interface LimitTally<T> {
  past: T[]
  withinMargin: T[]
  inside: T[]
  cutShort: T[]
  noNight: T[]
}

export function tallyAgainstLimit<T>(items: T[], against: (t: T) => AgainstLimit): LimitTally<T> {
  const out: LimitTally<T> = { past: [], withinMargin: [], inside: [], cutShort: [], noNight: [] }
  for (const t of items) {
    const k = against(t).kind
    if (k === 'past') out.past.push(t)
    else if (k === 'within-margin') out.withinMargin.push(t)
    else if (k === 'inside') out.inside.push(t)
    else if (k === 'cut-short') out.cutShort.push(t)
    else out.noNight.push(t)
  }
  return out
}

/** "A", "A and B", "A, B and C". */
export function andList(names: string[]): string {
  return names.length <= 1 ? (names[0] ?? '') : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
}

/**
 * The value of one of the four numbers, for display.
 *
 * Ranking is not done here: order, ranks and ties come from `POST /compare`,
 * so the screen and the API cannot disagree about which site comes first.
 */
export function metricValue(m: SiteMetrics, key: string): number {
  switch (key) {
    case 'sunHours':
      return m.sun.upHours
    case 'earthHours':
      return m.earth.upHours
    case 'longestDark':
      return m.sun.longestDownH
    case 'longestBlackout':
      return m.earth.longestDownH
    default:
      return 0
  }
}
