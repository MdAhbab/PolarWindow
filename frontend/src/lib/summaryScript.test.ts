import { describe, expect, it } from 'vitest'
import { buildComparisonSummary, buildSiteSummary, type SummaryInput } from './summaryScript'

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
  silenceH: 278.5,
  silenceOpen: false,
  silenceToleranceH: 5.3,
  silenceGrazing: false,
  worstCompoundH: 38.4,
  survivalLimitH: 120,
  coverage: 1,
  terrainModelled: true,
}

describe('buildSiteSummary', () => {
  it('speaks the numbers it is given, with their margins, and no symbols', () => {
    const s = buildSiteSummary(site)
    expect(s.text).toContain('Sunlight 574 hours, 81 percent of the time.')
    expect(s.text).toContain('Longest night: about 122 hours, give or take 17 hours.')
    expect(s.text).toContain('2 hours over the 120 hour battery limit')
    expect(s.text).not.toMatch(/[≈±%]/)
  })

  it('says a cut-short night is at least its value, and never gives it a margin', () => {
    const s = buildSiteSummary({ ...site, nightH: 112, nightOpen: true })
    expect(s.text).toContain('Longest night: at least 112 hours. These dates cut it short')
    expect(s.text).toContain('It may run past the 120 hour battery limit.')
  })

  it('says plainly when there was no night and no blackout', () => {
    const s = buildSiteSummary({ ...site, windowHours: 12.75, nightH: 0, silenceH: 0, worstCompoundH: 0 })
    expect(s.text).toContain('Over 12.75 hours from 14 March 2027')
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
  const base = { rankedBy: 'Longest night', windowStartIso: '2027-03-14T00:00:00Z', windowHours: 708.734, survivalLimitH: 120 }

  it('never calls a cut-short value best, and gives the range it could fall in', () => {
    const s = buildComparisonSummary({
      ...base,
      sites: [
        { name: 'de Gerlache rim', label: { kind: 'unranked', text: "cut short, can't rank", title: 'could be 1st–3rd' }, valueH: 112, open: true, overLimit: false },
        { name: 'Connecting Ridge', label: { kind: 'unranked', text: "can't rank against D", title: 'could be 1st–2nd' }, valueH: 121.6, open: false, overLimit: true },
      ],
    })
    expect(s.text).not.toMatch(/\bbest\b/)
    expect(s.text).toContain("de Gerlache rim can't be ranked, because the chosen dates cut its value short; it could be 1st–3rd: at least 112 hours.")
    expect(s.text).toContain('Connecting Ridge has a night over the 120 hour battery limit')
  })

  it('says best only where the ranking allows it, and joint places as ties', () => {
    const s = buildComparisonSummary({
      ...base,
      sites: [
        { name: 'A', label: { kind: 'best', text: 'best' }, valueH: 80, open: false, overLimit: false },
        { name: 'B', label: { kind: 'joint', text: 'joint 2nd' }, valueH: 90, open: false, overLimit: false },
      ],
    })
    expect(s.sentences[1]).toBe('A is best: about 80 hours.')
    expect(s.sentences[2]).toContain('B is joint 2nd, tied with')
  })
})
