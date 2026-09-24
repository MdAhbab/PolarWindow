/**
 * What a ranked site may be called (U11, handoff §10.7).
 *
 * The server's ranking is censoring-aware (system-design §10.7): a value the
 * window cut short is a lower bound, an untimeable edge has no margin, and
 * either one can make a place impossible to state. `rank` is then null and
 * `rank_range` says where the site could fall. This function is the only place
 * that turns those fields into words, so "best" cannot leak onto a lower bound
 * or onto a site over the survival limit from some other code path.
 */

export interface RankFacts {
  /** Definite competition rank, or null when it cannot be stated. */
  rank: number | null
  /** [best possible, worst possible] place. */
  rankRange: readonly number[]
  tied: boolean
  /** The ranked value is a lower bound: the window, not the terrain, ended it. */
  censored: boolean
  /** An edge of the ranked value cannot be timed. */
  grazing: boolean
  /** The site's longest night is over the survival limit. */
  overLimit: boolean
  /** Short names of the sites it cannot be ordered against. */
  incomparableWith?: readonly string[]
}

export interface RankLabel {
  kind: 'best' | 'joint' | 'place' | 'over' | 'unranked'
  text: string
  /** Tooltip and accessible description; for an unranked site, the range. */
  title?: string
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

export function rangeWords(range: readonly number[]): string | undefined {
  if (range.length < 2) return undefined
  const [lo, hi] = range
  return lo === hi ? `${ordinal(lo)}` : `could be ${ordinal(lo)}–${ordinal(hi)}`
}

export function rankLabel(f: RankFacts): RankLabel {
  if (f.rank === null) {
    const title = rangeWords(f.rankRange)
    if (f.censored) return { kind: 'unranked', text: "cut short, can't rank", title, tone: 'uncertain' }
    if (f.grazing) return { kind: 'unranked', text: "edge can't be timed, can't rank", title, tone: 'uncertain' }
    const others = f.incomparableWith?.length ? ` against ${f.incomparableWith.join(' and ')}` : ''
    return { kind: 'unranked', text: `can't rank${others}`, title, tone: 'uncertain' }
  }
  if (f.tied) return { kind: 'joint', text: `joint ${ordinal(f.rank)}`, tone: 'ink' }
  if (f.rank === 1) {
    if (f.overLimit) return { kind: 'over', text: '1st, over the limit', tone: 'ink' }
    // A definite rank on a censored value should not happen (the server nulls
    // it), but "best" on a lower bound is the one label this must never print.
    if (f.censored) return { kind: 'place', text: '1st', tone: 'ink' }
    return { kind: 'best', text: 'best', tone: 'ink' }
  }
  return { kind: 'place', text: ordinal(f.rank), tone: 'ink' }
}
