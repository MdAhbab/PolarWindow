/**
 * U11: "best" is a claim, and this is the only function allowed to make it.
 * The cases are the ones the 2026-09-23 review reproduced (system-design
 * §10.7): a lower bound once outranked a measured value and was called best.
 */
import { describe, expect, it } from 'vitest'
import { ordinal, rankLabel, type RankFacts } from './rank'

const base: RankFacts = {
  rank: 1,
  rankRange: [1, 1],
  tied: false,
  censored: false,
  grazing: false,
  overLimit: false,
}

describe('rankLabel', () => {
  it('calls a definite, measured, survivable first place best', () => {
    expect(rankLabel(base)).toMatchObject({ kind: 'best', text: 'best', tone: 'ink' })
  })

  it('never calls a site over the survival limit best', () => {
    const l = rankLabel({ ...base, overLimit: true })
    expect(l.kind).not.toBe('best')
    expect(l.text).not.toMatch(/best/)
  })

  it('never calls a censored value best, even if a rank slipped through', () => {
    const l = rankLabel({ ...base, censored: true })
    expect(l.text).not.toMatch(/best/)
  })

  it('says "cut short, can\'t rank" for a null rank on a censored value, with the range as its title', () => {
    const l = rankLabel({ ...base, rank: null, rankRange: [1, 3], censored: true })
    expect(l).toMatchObject({ kind: 'unranked', text: "cut short, can't rank", tone: 'uncertain' })
    expect(l.title).toBe('could be 1st–3rd')
  })

  it('names an untimeable edge rather than calling it cut short', () => {
    const l = rankLabel({ ...base, rank: null, rankRange: [1, 4], grazing: true })
    expect(l.text).toBe("edge can't be timed, can't rank")
    expect(l.title).toBe('could be 1st–4th')
  })

  it('names what a measured site cannot be ordered against', () => {
    const l = rankLabel({ ...base, rank: null, rankRange: [1, 2], incomparableWith: ['D', 'I'] })
    expect(l.text).toBe("can't rank against D and I")
    expect(l.tone).toBe('uncertain')
  })

  it('prints tied sites as joint, never as best', () => {
    expect(rankLabel({ ...base, tied: true }).text).toBe('joint 1st')
    expect(rankLabel({ ...base, rank: 3, rankRange: [3, 4], tied: true }).text).toBe('joint 3rd')
  })

  it('gives a later definite place as an ordinal', () => {
    expect(rankLabel({ ...base, rank: 2, rankRange: [2, 2] })).toMatchObject({ kind: 'place', text: '2nd' })
  })
})

describe('ordinal', () => {
  it('handles the teens', () => {
    expect([1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 101].map(ordinal)).toEqual([
      '1st', '2nd', '3rd', '4th', '11th', '12th', '13th', '21st', '22nd', '23rd', '101st',
    ])
  })
})
