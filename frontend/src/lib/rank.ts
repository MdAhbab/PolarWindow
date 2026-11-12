/**
 * What a site's place in the comparison may be called (U11, handoff §10.7).
 *
 * The Compare page orders by one number at a time and says which number; a
 * place in that order is "1st by longest night", never a verdict on the site
 * (D-16, design-glossary "Words that never appear"). So rank 1 reads "1st"
 * like every other place, over the battery limit or not; the limit is said
 * beside the night's figure, not folded into the place.
 *
 * The server's ranking is censoring-aware (system-design §10.7): a value the
 * window cut short is a lower bound, an untimeable edge has no margin, and
 * either one can make a place impossible to state. `rank` is then null and
 * `rank_range` says where the site could fall. This function is the only place
 * that turns those fields into words.
 */
import type { MetricKey } from './types'

export interface RankFacts {
  /** Definite competition rank, or null when it cannot be stated. */
  rank: number | null
  /** [highest possible, lowest possible] place. */
  rankRange: readonly number[]
  tied: boolean
  /** The ranked value is a lower bound: the window, not the terrain, ended it. */
  censored: boolean
  /** An edge of the ranked value cannot be timed. */
  grazing: boolean
  /** Short names of the sites it cannot be ordered against. */
  incomparableWith?: readonly string[]
  /** How many sites are in the order: a range covering all of them says nothing. */
  places?: number
  /** The number the sites are ordered by, so a skimming edge names its body and gap. */
  metric?: MetricKey
}

export interface RankLabel {
  /** `first` is rank 1: a place, the same kind of word as every other place. */
  kind: 'first' | 'joint' | 'place' | 'unranked'
  text: string
  /** Tooltip and accessible description; for an unranked site, the places it could take. */
  title?: string
  /** For an unranked site, why no place can be stated, in words. */
  why?: string
  /** `uncertain` renders in `text-uncertain`: a margin we admit to. */
  tone: 'ink' | 'uncertain'
}

export function ordinal(n: number): string {
  const mod100 = n % 100
  if (mod100 >= 11 && mod100 <= 13) return `${n}th`
  switch (n % 10) {
    case 1:
      return `${n}st`
    case 2:
      return `${n}nd`
    case 3:
      return `${n}rd`
    default:
      return `${n}th`
  }
}

/**
 * "could be 1st to 2nd". Words, not a dash, so the range never splits at a
 * line end (V140). Nothing when the range covers every place: it would say
 * no more than "anywhere" (c4).
 */
export function rangeWords(range: readonly number[], places?: number): string | undefined {
  if (range.length < 2) return undefined
  const [lo, hi] = range
  if (places !== undefined && places > 1 && lo <= 1 && hi >= places) return undefined
  return lo === hi ? `${ordinal(lo)}` : `could be ${ordinal(lo)} to ${ordinal(hi)}`
}

/** Which end of each order is 1st, as the server orders it (backend core/metrics.py METRIC_KEYS). */
export function firstEnd(metric: MetricKey): 'most first' | 'shortest first' {
  return metric === 'sunHours' || metric === 'earthHours' ? 'most first' : 'shortest first'
}

/** Why an edge cannot be timed, naming the body and the stretch (glossary: "skims the skyline"). */
function skimWords(metric: MetricKey | undefined): string {
  switch (metric) {
    case 'longestDark':
      return 'the Sun skims the skyline at the start or end of this night'
    case 'longestBlackout':
      return 'Earth skims the skyline at the start or end of this time without contact'
    case 'sunHours':
      return 'the Sun skims the skyline at a sunrise or sunset, so that moment cannot be timed'
    case 'earthHours':
      return 'Earth skims the skyline as it rises or sets, so that moment cannot be timed'
    default:
      return 'a start or end skims the skyline, so it cannot be timed'
  }
}

export function rankLabel(f: RankFacts): RankLabel {
  if (f.rank === null) {
    const title = rangeWords(f.rankRange, f.places)
    // One label for every reason, so the card stays short; the reason and the
    // places it could take are said when the label is opened.
    const text = 'too close to call'
    if (f.censored) return { kind: 'unranked', text, title, why: 'the chosen dates cut its value short', tone: 'uncertain' }
    if (f.grazing) return { kind: 'unranked', text, title, why: skimWords(f.metric), tone: 'uncertain' }
    const others = f.incomparableWith?.length ? ` from ${f.incomparableWith.join(' and ')}` : ''
    return { kind: 'unranked', text, title, why: `the margins can’t separate it${others}`, tone: 'uncertain' }
  }
  if (f.tied) return { kind: 'joint', text: `joint ${ordinal(f.rank)}`, tone: 'ink' }
  if (f.rank === 1) return { kind: 'first', text: '1st', tone: 'ink' }
  return { kind: 'place', text: ordinal(f.rank), tone: 'ink' }
}
