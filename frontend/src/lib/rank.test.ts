/**
 * U11, R5: a place in the order is a place ("1st"), never a verdict on the
 * site. The cases are the ones the 2026-09-23 review reproduced (system-design
 * §10.7), where a lower bound once outranked a measured value, and the audit
 * of 12 Nov (journeys R5, c4, V140).
 */
import { describe, expect, it } from 'vitest'
import { firstEnd, ordinal, rangeWords, rankLabel, type RankFacts } from './rank'

const base: RankFacts = {
  rank: 1,
  rankRange: [1, 1],
  tied: false,
  censored: false,
  grazing: false,
}

/** The only labels a place may have: an ordinal, a joint ordinal, or "too close to call". */
const PLACE = /^((joint )?\d+(st|nd|rd|th)|too close to call)$/

describe('rankLabel', () => {
  it('calls a definite first place "1st", like every other place', () => {
    expect(rankLabel(base)).toMatchObject({ kind: 'first', text: '1st', tone: 'ink' })
    expect(rankLabel({ ...base, rank: 2, rankRange: [2, 2] })).toMatchObject({ kind: 'place', text: '2nd' })
  })

  it('only ever says a place, whatever the facts', () => {
    const cases: RankFacts[] = [
      base,
      { ...base, censored: true },
      { ...base, tied: true },
      { ...base, rank: null, rankRange: [1, 3], censored: true },
      { ...base, rank: null, rankRange: [1, 3], grazing: true, metric: 'longestDark' },
      { ...base, rank: null, rankRange: [1, 2], incomparableWith: ['D'] },
    ]
    for (const f of cases) expect(rankLabel(f).text).toMatch(PLACE)
  })

  it('says "1st" on a censored value too, if a rank slipped through', () => {
    expect(rankLabel({ ...base, censored: true }).text).toBe('1st')
  })

  it('says "too close to call" for a null rank on a censored value, with the reason and the range in words', () => {
    const l = rankLabel({ ...base, rank: null, rankRange: [1, 3], censored: true, places: 4 })
    expect(l).toMatchObject({ kind: 'unranked', text: 'too close to call', why: 'the chosen dates cut its value short', tone: 'uncertain' })
    expect(l.title).toBe('could be 1st to 3rd')
  })

  it('names the body that skims the skyline rather than calling it cut short', () => {
    const l = rankLabel({ ...base, rank: null, rankRange: [1, 4], grazing: true, metric: 'longestDark', places: 5 })
    expect(l.why).toBe('the Sun skims the skyline at the start or end of this night')
    expect(l.title).toBe('could be 1st to 4th')
    expect(rankLabel({ ...base, rank: null, rankRange: [2, 3], grazing: true, metric: 'longestBlackout' }).why).toBe(
      'Earth skims the skyline at the start or end of this time without contact',
    )
  })

  it('gives only the reason when the range covers every place (c4)', () => {
    const l = rankLabel({ ...base, rank: null, rankRange: [1, 3], grazing: true, metric: 'longestDark', places: 3 })
    expect(l.title).toBeUndefined()
    expect(l.why).toBe('the Sun skims the skyline at the start or end of this night')
  })

  it('names what a measured site cannot be ordered against', () => {
    const l = rankLabel({ ...base, rank: null, rankRange: [1, 2], incomparableWith: ['D', 'I'] })
    expect(l.why).toBe('the margins can’t separate it from D and I')
    expect(l.tone).toBe('uncertain')
  })

  it('prints tied sites as joint places', () => {
    expect(rankLabel({ ...base, tied: true }).text).toBe('joint 1st')
    expect(rankLabel({ ...base, rank: 3, rankRange: [3, 4], tied: true }).text).toBe('joint 3rd')
  })

  it('gives a later definite place as an ordinal', () => {
    expect(rankLabel({ ...base, rank: 2, rankRange: [2, 2] })).toMatchObject({ kind: 'place', text: '2nd' })
  })
})

describe('rangeWords', () => {
  it('writes a range with "to", never a dash, so it cannot split at a line end (V140)', () => {
    expect(rangeWords([1, 2])).toBe('could be 1st to 2nd')
    expect(rangeWords([1, 2])).not.toMatch(/[–—-]/)
    expect(rangeWords([2, 2])).toBe('2nd')
  })
})

describe('firstEnd', () => {
  it('says which end of each order is 1st, as the server orders', () => {
    expect(firstEnd('sunHours')).toBe('most first')
    expect(firstEnd('earthHours')).toBe('most first')
    expect(firstEnd('longestDark')).toBe('shortest first')
    expect(firstEnd('longestBlackout')).toBe('shortest first')
  })
})

describe('ordinal', () => {
  it('handles the teens', () => {
    expect([1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 101].map(ordinal)).toEqual([
      '1st', '2nd', '3rd', '4th', '11th', '12th', '13th', '21st', '22nd', '23rd', '101st',
    ])
  })
})
