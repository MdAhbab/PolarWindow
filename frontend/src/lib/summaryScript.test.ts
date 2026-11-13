import { describe, expect, it } from 'vitest'
import { buildComparisonSummary as buildComparison, buildSiteSummary as buildSite, type Summary, type SummaryInput } from './summaryScript'
import { ASSUMED_LIMIT, nightAgainstLimit, type BatteryLimit } from './geometry/metrics'

const ENTERED: BatteryLimit = { h: 96, basis: 'entered', by: 'A. Rahman' }

/** The words as heard: a non-breaking space (lib/format.ts) is a space. */
const plain = (s: Summary): Summary => ({ ...s, text: s.text.replace(/ /g, ' '), sentences: s.sentences.map((x) => x.replace(/ /g, ' ')) })
const buildSiteSummary = (i: SummaryInput) => plain(buildSite(i))
const buildComparisonSummary = (i: Parameters<typeof buildComparison>[0]) => plain(buildComparison(i))

const site: SummaryInput = {
  siteName: 'Connecting Ridge',
  latDeg: -89.438,
  windowStartIso: '2027-03-14T00:00:00Z',
  windowHours: 708.734,
  sunUpH: 574.4,
  sunFraction: 0.81,
  earthUpH: 430.1,
  earthFraction: 0.61,
  nightH: 121.6,
  nightOpen: false,
  nightToleranceH: 17.09,
  nightGrazing: false,
  nightMarginH: 17.09,
  silenceH: 278.5,
  silenceOpen: false,
  silenceToleranceH: 5.3,
  silenceGrazing: false,
  worstCompoundH: 38.4,
  batteryLimit: ASSUMED_LIMIT,
  coverage: 1,
  terrainModelled: true,
}

describe('buildSiteSummary', () => {
  it('speaks the numbers it is given, with their margins, and no symbols', () => {
    const s = buildSiteSummary(site)
    expect(s.text).toContain('Sunlight 574 hours, 81 percent of the time.')
    expect(s.text).toContain('Longest night: about 122 hours, give or take 17 hours.')
    expect(s.text).not.toMatch(/[≈±%]/)
  })

  it('says a night within its margin of the limit is within it, never over it, and says the limit is assumed', () => {
    // 121.6 h against 120 h with a 17.09 h margin: the difference is inside the margin.
    const s = buildSiteSummary(site)
    expect(s.text).toContain('That is within the margin of the 120 hour battery limit, which is assumed.')
    expect(s.text).not.toMatch(/over the|past the/)
  })

  it('says how far past or inside the assumed limit a night is, beyond its margin', () => {
    expect(buildSiteSummary({ ...site, nightH: 606, nightMarginH: 1.2 }).text).toContain(
      'That is 486 hours past the 120 hour battery limit, which is assumed.',
    )
    expect(buildSiteSummary({ ...site, nightH: 64, nightMarginH: 2 }).text).toContain(
      'That is 56 hours inside the 120 hour battery limit, which is assumed.',
    )
  })

  it('names the limit the team entered as theirs, with no "assumed"', () => {
    const s = buildSiteSummary({ ...site, nightH: 64, nightMarginH: 2, batteryLimit: ENTERED })
    expect(s.text).toContain('That is 32 hours inside the 96 hour battery limit your team entered.')
    expect(s.text).not.toMatch(/assumed/)
  })

  it('says a cut-short night is at least its value, and never gives it a margin', () => {
    const s = buildSiteSummary({ ...site, nightH: 102, nightOpen: true, nightMarginH: undefined })
    expect(s.text).toContain('Longest night: at least 102 hours. These dates cut it short')
    expect(s.text).toContain('It may run past the 120 hour battery limit, which is assumed.')
  })

  it('says plainly when there was no night and no blackout', () => {
    const s = buildSiteSummary({ ...site, windowHours: 12.75, nightH: 0, silenceH: 0, worstCompoundH: 0 })
    expect(s.text).toContain('Over 13 hours from 14 March 2027')
    expect(s.text).toContain('The Sun did not set on these dates.')
    expect(s.text).toContain('It stays in contact with Earth the whole time.')
    expect(s.text).not.toMatch(/about 0 hours|inside the 120 hour/)
  })

  it('says a northern site is north, and flags a flat-ground skyline', () => {
    const s = buildSiteSummary({ ...site, latDeg: 18.56, terrainModelled: false })
    expect(s.text).toContain('18.6 degrees north')
    expect(s.text).toContain('There is no terrain data here')
  })
})

describe('buildComparisonSummary', () => {
  const base = {
    rankedBy: 'Longest night',
    firstEnd: 'shortest first',
    windowStartIso: '2027-03-14T00:00:00Z',
    windowHours: 708.734,
    batteryLimit: ASSUMED_LIMIT,
  }

  it('says which number orders the sites and which end is 1st', () => {
    const s = buildComparisonSummary({ ...base, sites: [] })
    expect(s.sentences[0]).toBe('Comparing 0 sites over 29.5 days from 14 March 2027, in order of longest night, shortest first.')
  })

  it('says why a place cannot be stated and the places it could take, in words', () => {
    const s = buildComparisonSummary({
      ...base,
      sites: [
        {
          name: 'de Gerlache rim',
          label: { kind: 'unranked', text: 'too close to call', title: 'could be 1st to 3rd', why: 'the chosen dates cut its value short' },
          valueH: 112,
          open: true,
          against: 'cut-short',
        },
        {
          name: 'Connecting Ridge',
          label: { kind: 'unranked', text: 'too close to call', title: 'could be 1st to 2nd', why: 'the margins can’t separate it from D' },
          valueH: 121.6,
          open: false,
          against: 'within-margin',
        },
      ],
    })
    expect(s.text).toContain(
      "de Gerlache rim can't be ranked, because the chosen dates cut its value short; it could be 1st to 3rd: at least 112 hours.",
    )
    expect(s.text).toContain('Connecting Ridge has a longest night within the margin of the 120 hour battery limit, which is assumed.')
    expect(s.text).not.toMatch(/[–—]/)
  })

  it('says a place as a place, 1st included, and joint places as ties', () => {
    const s = buildComparisonSummary({
      ...base,
      sites: [
        { name: 'A', label: { kind: 'first', text: '1st' }, valueH: 80, open: false, against: 'inside' },
        { name: 'B', label: { kind: 'joint', text: 'joint 2nd' }, valueH: 90, open: false, against: 'inside' },
      ],
    })
    expect(s.sentences[1]).toBe('A is 1st: about 80 hours.')
    expect(s.sentences[2]).toContain('B is joint 2nd, tied with')
  })

  it('counts the nights past the limit, with the limit named as assumed or entered', () => {
    const sites = [
      { name: 'Malapert massif', label: { kind: 'place' as const, text: '2nd' }, valueH: 288, open: true, against: 'past' as const },
      { name: 'Faustini rim', label: { kind: 'place' as const, text: '3rd' }, valueH: 606, open: false, against: 'past' as const },
    ]
    expect(buildComparisonSummary({ ...base, sites }).text).toContain(
      'On these dates, Malapert massif and Faustini rim have nights past the 120 hour battery limit, which is assumed.',
    )
    expect(buildComparisonSummary({ ...base, batteryLimit: ENTERED, sites }).text).toContain(
      'have nights past the 96 hour battery limit your team entered.',
    )
  })
})

describe('nightAgainstLimit', () => {
  it('uses the night’s margin: past or inside only by more than it', () => {
    expect(nightAgainstLimit({ h: 121.6, open: false, marginH: 17.09 }, 120)).toMatchObject({ kind: 'within-margin' })
    expect(nightAgainstLimit({ h: 606, open: false, marginH: 1.2 }, 120)).toMatchObject({ kind: 'past', byH: 486, atLeast: false })
    expect(nightAgainstLimit({ h: 64, open: false, marginH: 2 }, 120)).toMatchObject({ kind: 'inside', byH: 56 })
    // No margin that can be stated: compared as it is.
    expect(nightAgainstLimit({ h: 121.6, open: false }, 120)).toMatchObject({ kind: 'past' })
  })

  it('never calls a night the dates cut short inside the limit', () => {
    expect(nightAgainstLimit({ h: 102, open: true }, 120)).toEqual({ kind: 'cut-short' })
    expect(nightAgainstLimit({ h: 288, open: true, marginH: 0.4 }, 120)).toMatchObject({ kind: 'past', atLeast: true })
  })

  it('says there was no night when there was none', () => {
    expect(nightAgainstLimit({ h: 0, open: false, none: true }, 120)).toEqual({ kind: 'no-night' })
  })
})
