import { spanWords } from './format'

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
 *  - No verdict the API does not support. The only threshold is the survival
 *    limit, and it is named as the limit it is.
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
  silenceH: number
  silenceOpen: boolean
  silenceToleranceH: number
  silenceGrazing: boolean
  worstCompoundH: number
  survivalLimitH: number
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
  out.push(`It can call home for ${round(s.earthUpH)} hours, ${pct(s.earthFraction)}.`)

  // No gap at all is a measurement too, and says so plainly rather than as
  // "about 0 hours, 120 hours inside the limit".
  const noNight = s.nightH <= 0 && !s.nightOpen
  const over = s.nightH - s.survivalLimitH
  if (noNight) {
    out.push('The Sun did not set in this window.')
  } else {
    let night = `Longest night: ${duration(s.nightH, s.nightOpen, s.nightToleranceH, s.nightGrazing)}.`
    if (s.nightOpen) night += ' This period cut it short, so the real night is longer.'
    if (s.nightGrazing) night += ' Its start and end cannot be timed precisely.'
    out.push(night)
    if (over > 0) {
      out.push(
        `That is ${s.nightOpen ? 'at least ' : ''}${round(over)} hours over the ${s.survivalLimitH} hour survival limit.`,
      )
    } else if (s.nightOpen) {
      out.push(`It may exceed the ${s.survivalLimitH} hour survival limit.`)
    } else {
      out.push(`That is ${round(-over)} hours inside the ${s.survivalLimitH} hour survival limit.`)
    }
  }

  if (s.silenceH <= 0 && !s.silenceOpen) {
    out.push('It can call home the whole time.')
  } else {
    let silence = `Longest time it can't call home: ${duration(s.silenceH, s.silenceOpen, s.silenceToleranceH, s.silenceGrazing)}.`
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
      'Terrain is not modelled here, so these figures assume a smooth Moon, and real hills could block more.',
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
  /** What the ranking lets this site be called (lib/rank.ts). */
  label: { kind: 'best' | 'joint' | 'place' | 'over' | 'unranked'; text: string; title?: string }
  /** The ranked value, hours, as the API gave it. */
  valueH: number
  /** The ranked value is a lower bound: the window cut it short. */
  open: boolean
  overLimit: boolean
}

export interface ComparisonInput {
  /** The ranking metric's plain name: "Longest night". */
  rankedBy: string
  windowStartIso?: string
  windowHours: number
  survivalLimitH: number
  /** In the server's order. */
  sites: ComparisonSite[]
}

/**
 * The comparison, spoken. Bound-aware in the same way as the screen: a value
 * the window cut short is "at least", a site whose place cannot be stated is
 * said to be unrankable with the range it could fall in, and "best" is only
 * ever said where the screen says it.
 */
export function buildComparisonSummary(c: ComparisonInput): Summary {
  const out: string[] = []
  const when = startDate(c.windowStartIso)
  out.push(
    `Comparing ${c.sites.length} sites over ${spanWords(c.windowHours)}${when ? ` from ${when}` : ''}, by ${c.rankedBy.toLowerCase()}.`,
  )
  for (const s of c.sites) {
    const value = `${s.open ? 'at least' : 'about'} ${round(s.valueH)} hours`
    let place: string
    switch (s.label.kind) {
      case 'best':
        place = 'is best'
        break
      case 'joint':
        place = `is ${s.label.text}, tied with a site the data cannot separate it from`
        break
      case 'over':
        place = 'is first, but over the survival limit'
        break
      case 'place':
        place = `is ${s.label.text}`
        break
      case 'unranked':
        place = `can't be ranked${s.open ? ', because the window cut its value short' : ''}${
          s.label.title ? `; it ${s.label.title}` : ''
        }`
        break
    }
    out.push(`${s.name} ${place}: ${value}.`)
  }
  const over = c.sites.filter((s) => s.overLimit)
  if (over.length) {
    out.push(
      `${over.map((s) => s.name).join(' and ')} ${over.length === 1 ? 'has a night' : 'have nights'} over the ${
        c.survivalLimitH
      } hour survival limit in this window.`,
    )
  }
  out.push('These are planning estimates, not official values.')
  const text = out.join(' ')
  return { sentences: out, text, seconds: Math.round((text.split(/\s+/).length / 165) * 60) }
}
