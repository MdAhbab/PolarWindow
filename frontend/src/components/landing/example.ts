import type { MetricsDTO } from '../../lib/api/client'
import type { AdaptedSiteBrief } from '../../lib/api/adapters'
import { bound, hoursSpoken, percent, plusMinus, windowLine } from '../../lib/format'

/**
 * The one real example under three of the idea cards: a figure the service
 * worked out for one named site and its own default dates, printed the way the
 * dashboard prints it (the value in whole hours, its margin, the unit), with
 * the tag that says where it came from. The page types no number: everything
 * here is read off the answers, and a figure the dashboard itself would not
 * print with a margin (a night that skims the skyline, one the dates cut
 * short at both ends, a site outside the terrain model) is left out.
 */
export type ExampleKind = 'sunlight' | 'night' | 'contact'

export interface ExampleSite {
  id: string
  name: string
  /** The service's own default dates for the site list: the same ones its summaries are worked out over. */
  start: string
  end: string
}

/**
 * Which site to show: the first candidate the service lists that has a
 * summary over its default dates and is inside the terrain model. The order is
 * the service's; nothing about a site's figures is looked at, so the choice
 * says nothing about the site.
 */
export function pickExampleSite(items: readonly AdaptedSiteBrief[] | undefined): ExampleSite | null {
  const hit = items?.find(
    (i) => i.site.kind === 'candidate' && i.site.terrainModelled && i.summary && !i.summary.grazing,
  )
  if (!hit?.summary) return null
  return {
    id: hit.site.id,
    name: hit.site.name,
    start: hit.summary.referenceWindowStart,
    end: hit.summary.referenceWindowEnd,
  }
}

export interface ExampleLine {
  kind: ExampleKind
  /** "Longest night at Shackleton rim, east shoulder". */
  label: string
  /** "206" (with "≥" when the dates cut it short). */
  figure: string
  /** "±0.2". */
  margin: string
  unit: 'h'
  /** "47% of the time", for the share of sunlight. */
  note: string | null
  /** "29.5 days from 14 Mar 2027". */
  dates: string
  /** Where it comes from, as the dashboard's tag says it. */
  tag: 'worked out'
  /** The whole line as a screen reader should hear it. */
  spoken: string
}

const toH = (s: number) => s / 3600

const LABEL: Record<ExampleKind, string> = {
  sunlight: 'Time in sunlight',
  night: 'Longest night',
  contact: 'Longest time without contact',
}

/**
 * The line for one card, or null when the answer cannot honestly give it: no
 * answer, a site outside the terrain model, a measure with no margin to print
 * (the answer says null), nothing to measure (no night in these dates), or a
 * figure that is not a number.
 */
export function exampleLine(kind: ExampleKind, site: ExampleSite, m: MetricsDTO | null | undefined): ExampleLine | null {
  if (!m) return null
  if (m.meta?.uncertainty?.terrain_modelled === false) return null

  let seconds: number
  let tolerance: number | null | undefined
  let open = false
  let note: string | null = null
  switch (kind) {
    case 'sunlight':
      seconds = m.sunlit_s
      tolerance = m.sunlit_tolerance_s
      note = Number.isFinite(m.sun_fraction_up) ? `${percent(m.sun_fraction_up)} of the time` : null
      break
    case 'night':
      if (m.longest_dark_grazing) return null
      seconds = m.longest_dark_s
      tolerance = m.longest_dark_tolerance_s
      open = m.longest_dark_open
      break
    case 'contact':
      if (m.longest_blackout_grazing) return null
      seconds = m.longest_blackout_s
      tolerance = m.longest_blackout_tolerance_s
      open = m.longest_blackout_open
      break
  }
  if (!Number.isFinite(seconds) || seconds <= 0) return null
  if (tolerance === null || tolerance === undefined || !Number.isFinite(tolerance) || tolerance < 0) return null

  const startMs = Date.parse(site.start)
  const endMs = Date.parse(site.end)
  if (Number.isNaN(startMs) || Number.isNaN(endMs) || endMs <= startMs) return null

  const hours = toH(seconds)
  const margin = plusMinus(toH(tolerance))
  const figure = `${bound(open)}${Math.round(hours)}`
  const dates = windowLine(startMs, toH((endMs - startMs) / 1000))
  const label = `${LABEL[kind]} at ${site.name}`
  const marginSpoken = toH(tolerance) < 0.05 ? 'timed to within a few minutes' : `plus or minus ${toH(tolerance).toFixed(1)} hours`
  return {
    kind,
    label,
    figure,
    margin,
    unit: 'h',
    note,
    dates,
    tag: 'worked out',
    spoken: `${label}: ${hoursSpoken(hours, open)}, ${marginSpoken}${note ? `, ${note}` : ''}. ${dates}. Worked out.`,
  }
}
