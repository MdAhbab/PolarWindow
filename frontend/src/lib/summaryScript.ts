import { spanWords } from './format'
import { andList, limitSpoken, nightAgainstLimit, type AgainstLimit, type BatteryLimit } from './geometry/metrics'
import type { RankLabel } from './rank'

/**
 * The words the summary speaker says, built only from numbers the API returned.
 *
 * One source, two outputs: the same sentences are spoken aloud and rendered as
 * a visible transcript, so a screen-reader user, a deaf user and a user in a
 * quiet room all get the identical summary.
 *
 * Rules, each one a reason the text is shaped the way it is:
 *  - Units are words ("hours", "percent"), never symbols: speech engines read
 *    "≈", "±" and "%" inconsistently, and a transcript full of symbols is the
 *    bloat this feature exists to remove.
 *  - A window-censored figure is spoken as "at least", never "about".
 *  - An untimeable edge is said in words, never given a fake ±.
 *  - No verdict the API does not support. The only threshold is the battery
 *    limit, and it is named as the limit it is: the one the team entered, or
 *    120 hours said to be assumed. A night within its margin of the limit is
 *    said to be, never called over or inside.
 *  - ~90 words: about 35 seconds at a normal speaking rate.
 */

export interface SummaryInput {
  siteName: string
  latDeg: number
  windowStartIso?: string
  windowHours: number
  sunUpH: number
  sunFraction: number
  earthUpH: number
  earthFraction: number
  nightH: number
  nightOpen: boolean
  nightToleranceH: number
  nightGrazing: boolean
  /** The night's margin for the comparison with the limit, as the tile shows it (`nightMargin`); none when it cannot be stated. */
  nightMarginH?: number
  silenceH: number
  silenceOpen: boolean
  silenceToleranceH: number
  silenceGrazing: boolean
  worstCompoundH: number
  batteryLimit: BatteryLimit
  coverage: number
  /** False outside 80°S: the skyline is a smooth sphere, so the figures are upper bounds on light. */
  terrainModelled?: boolean
}

export interface Summary {
  /** One sentence per spoken phrase; the caption highlights the current one. */
  sentences: string[]
  text: string
  /** Rough length at 165 words per minute, for the button's accessible description. */
  seconds: number
}

const round = (v: number) => Math.round(v)
const pct = (f: number) => `${Math.round(f * 100)} percent`

function giveOrTake(h: number): string {
  if (h < 0.5) return ''
  const v = h >= 2 ? `${round(h)}` : h.toFixed(1)
  return `, give or take ${v} ${v === '1' ? 'hour' : 'hours'}`
}

function duration(h: number, open: boolean, tolH: number, grazing: boolean): string {
  const lead = open ? 'at least' : 'about'
  const tail = grazing ? '' : open ? '' : giveOrTake(tolH)
  return `${lead} ${round(h)} hours${tail}`
}

function startDate(iso?: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' })
}

export function buildSiteSummary(s: SummaryInput): Summary {
  const out: string[] = []
  const when = startDate(s.windowStartIso)
  const lat = `${Math.abs(s.latDeg).toFixed(1)} degrees ${s.latDeg < 0 ? 'south' : 'north'}`

  out.push(`${s.siteName}, at ${lat}. Over ${spanWords(s.windowHours)}${when ? ` from ${when}` : ''}:`)
  out.push(`Sunlight ${round(s.sunUpH)} hours, ${pct(s.sunFraction)} of the time.`)
  out.push(`It is in contact with Earth for ${round(s.earthUpH)} hours, ${pct(s.earthFraction)}.`)

  // No gap at all is a measurement too, and says so plainly rather than as
  // "about 0 hours, 120 hours inside the limit".
  const noNight = s.nightH <= 0 && !s.nightOpen
  if (noNight) {
    out.push('The Sun did not set on these dates.')
  } else {
    let night = `Longest night: ${duration(s.nightH, s.nightOpen, s.nightToleranceH, s.nightGrazing)}.`
    if (s.nightOpen) night += ' These dates cut it short, so the real night is longer.'
    if (s.nightGrazing) night += ' Its start and end cannot be timed precisely.'
    out.push(night)
    const limit = limitSpoken(s.batteryLimit)
    const a = nightAgainstLimit({ h: s.nightH, open: s.nightOpen, marginH: s.nightMarginH }, s.batteryLimit.h)
    switch (a.kind) {
      case 'past':
        out.push(`That is ${a.atLeast ? 'at least ' : ''}${round(a.byH)} hours past ${limit}.`)
        break
      case 'within-margin':
        out.push(`That is within the margin of ${limit}.`)
        break
      case 'cut-short':
        out.push(`It may run past ${limit}.`)
        break
      case 'inside':
        out.push(`That is ${round(a.byH)} hours inside ${limit}.`)
        break
    }
  }

  if (s.silenceH <= 0 && !s.silenceOpen) {
    out.push('It stays in contact with Earth the whole time.')
  } else {
    let silence = `Longest time without contact: ${duration(s.silenceH, s.silenceOpen, s.silenceToleranceH, s.silenceGrazing)}.`
    if (s.silenceOpen) silence += ' The real one is longer.'
    out.push(silence)
  }

  out.push(
    s.worstCompoundH >= 0.25
      ? `Longest time with neither sunlight nor Earth: about ${round(s.worstCompoundH)} hours.`
      : 'Sunlight and Earth are never lost together for more than a few minutes.',
  )

  if (s.terrainModelled === false) {
    out.push(
      'There is no terrain data here, so these figures assume flat ground, and real hills could block more.',
    )
  } else if (s.coverage < 0.999) {
    out.push(
      `Terrain data covers ${pct(s.coverage)} of the view, so these figures may be too optimistic.`,
    )
  }
  out.push('These are planning estimates, not official values.')

  const text = out.join(' ')
  const words = text.split(/\s+/).length
  return { sentences: out, text, seconds: Math.round((words / 165) * 60) }
}

export interface ComparisonSite {
  name: string
  /** What the order lets this site's place be called (lib/rank.ts). */
  label: Pick<RankLabel, 'kind' | 'text' | 'title' | 'why'>
  /** The ranked value, hours, as the API gave it. */
  valueH: number
  /** The ranked value is a lower bound: the window cut it short. */
  open: boolean
  /** Where its longest night stands against the battery limit, with the night's margin. */
  against: AgainstLimit['kind']
}

export interface ComparisonInput {
  /** The ranking metric's plain name: "Longest night". */
  rankedBy: string
  /** Which end is 1st: "shortest first", "most first" (lib/rank.ts `firstEnd`). */
  firstEnd: string
  windowStartIso?: string
  windowHours: number
  batteryLimit: BatteryLimit
  /** In the server's order. */
  sites: ComparisonSite[]
}

/**
 * The comparison, spoken. Bound-aware in the same way as the screen: a value
 * the window cut short is "at least", a site whose place cannot be stated is
 * said to be too close to call with the reason and the places it could take,
 * and a place is a place ("1st"), never a verdict.
 */
export function buildComparisonSummary(c: ComparisonInput): Summary {
  const out: string[] = []
  const when = startDate(c.windowStartIso)
  out.push(
    `Comparing ${c.sites.length} sites over ${spanWords(c.windowHours)}${when ? ` from ${when}` : ''}, in order of ${c.rankedBy.toLowerCase()}, ${c.firstEnd}.`,
  )
  for (const s of c.sites) {
    const value = `${s.open ? 'at least' : 'about'} ${round(s.valueH)} hours`
    let place: string
    switch (s.label.kind) {
      case 'joint':
        place = `is ${s.label.text}, tied with a site the data cannot separate it from`
        break
      case 'first':
      case 'place':
        place = `is ${s.label.text}`
        break
      case 'unranked':
        // The card's "too close to call", said with its reason and the places it could take.
        place = `can't be ranked${s.label.why ? `, because ${s.label.why}` : ''}${s.label.title ? `; it ${s.label.title}` : ''}`
        break
    }
    out.push(`${s.name} ${place}: ${value}.`)
  }
  const limit = limitSpoken(c.batteryLimit)
  const past = c.sites.filter((s) => s.against === 'past')
  const close = c.sites.filter((s) => s.against === 'within-margin')
  if (past.length) {
    out.push(`On these dates, ${andList(past.map((s) => s.name))} ${past.length === 1 ? 'has a night' : 'have nights'} past ${limit}.`)
  }
  if (close.length) {
    out.push(
      `${andList(close.map((s) => s.name))} ${close.length === 1 ? 'has a longest night' : 'have longest nights'} within the margin of ${
        past.length ? 'the limit' : limit
      }.`,
    )
  }
  out.push('These are planning estimates, not official values.')
  const text = out.join(' ')
  return { sentences: out, text, seconds: Math.round((text.split(/\s+/).length / 165) * 60) }
}
