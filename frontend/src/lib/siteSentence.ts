import { percent, spanWords } from './format'
import type { SiteMetrics } from './types'

/** The answer on Surface and on a site's page: the share of time in sunlight and in contact, and the longest night, in one sentence. */
export function surfaceSentence(metrics: SiteMetrics): string {
  const span = spanWords(metrics.windowHours)
  const sunAll = !metrics.sun.longestDownArc && metrics.sun.fractionUp > 0.999
  const earthAll = !metrics.earth.longestDownArc && metrics.earth.fractionUp > 0.999
  if (sunAll && earthAll) return `Over these ${span} the Sun stays up and Earth stays in view the whole time.`
  const sun = sunAll ? 'the Sun stays up' : `the Sun is up ${percent(metrics.sun.fractionUp)} of the time`
  const earth = earthAll ? 'Earth stays in view' : `Earth is in view ${percent(metrics.earth.fractionUp)} of the time`
  const night = metrics.sun.longestDownArc
    ? `; the longest night is ${metrics.sun.longestDownOpen ? 'at least ' : ''}${Math.round(metrics.sun.longestDownH)} hours`
    : ''
  return `Over these ${span} ${sun} and ${earth}${night}.`
}
