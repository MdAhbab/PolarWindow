import { describe, expect, it } from 'vitest'
import type { MetricsDTO } from '../../lib/api/client'
import type { AdaptedSiteBrief } from '../../lib/api/adapters'
import { exampleLine, pickExampleSite, type ExampleSite } from './example'

/** What the service answered for Shackleton rim over its default dates (the metrics endpoint, as served). */
const answer = (over: Partial<MetricsDTO> = {}): MetricsDTO =>
  ({
    site_id: 'shackleton-rim',
    start: '2027-03-14T00:00:00Z',
    end: '2027-04-12T12:45:00Z',
    sunlit_s: 1209696.357,
    sun_fraction_up: 0.474,
    sunlit_tolerance_s: 7720.8,
    longest_dark_s: 742696.383,
    longest_dark_tolerance_s: 749.4,
    longest_dark_open: false,
    longest_dark_grazing: false,
    longest_blackout_s: 1094384.778,
    longest_blackout_tolerance_s: 699.3,
    longest_blackout_open: false,
    longest_blackout_grazing: false,
    meta: { uncertainty: { terrain_modelled: true } },
    ...over,
  }) as unknown as MetricsDTO

const site: ExampleSite = {
  id: 'shackleton-rim',
  name: 'Shackleton rim, east shoulder',
  start: '2027-03-14T00:00:00Z',
  end: '2027-04-12T12:45:00Z',
}

const brief = (id: string, over: Partial<AdaptedSiteBrief['site']> = {}, summary: Partial<NonNullable<AdaptedSiteBrief['summary']>> | null = {}): AdaptedSiteBrief =>
  ({
    site: { id, name: id, kind: 'candidate', terrainModelled: true, ...over },
    summary:
      summary === null
        ? null
        : { grazing: false, referenceWindowStart: '2027-03-14T00:00:00Z', referenceWindowEnd: '2027-04-12T12:45:00Z', ...summary },
  }) as unknown as AdaptedSiteBrief

describe('which site the examples are about', () => {
  it('is the first candidate the service lists with a summary inside the terrain model', () => {
    const items = [
      brief('mission-im-1', { kind: 'mission_target' }),
      brief('no-summary', {}, null),
      brief('outside-model', { terrainModelled: false }),
      brief('skims', {}, { grazing: true }),
      brief('shackleton-rim'),
      brief('connecting-ridge'),
    ]
    expect(pickExampleSite(items)?.id).toBe('shackleton-rim')
  })

  it('carries the service’s own default dates for it', () => {
    expect(pickExampleSite([brief('a')])).toEqual({
      id: 'a',
      name: 'a',
      start: '2027-03-14T00:00:00Z',
      end: '2027-04-12T12:45:00Z',
    })
  })

  it('is none when there is nothing to pick', () => {
    expect(pickExampleSite(undefined)).toBeNull()
    expect(pickExampleSite([])).toBeNull()
    expect(pickExampleSite([brief('only-a-target', { kind: 'mission_target' })])).toBeNull()
  })
})

describe('the example line, printed as the dashboard prints a figure', () => {
  it('gives the share of sunlight in whole hours with its margin, the share, the dates and the tag', () => {
    const l = exampleLine('sunlight', site, answer())
    expect(l).toMatchObject({
      label: 'Time in sunlight at Shackleton rim, east shoulder',
      figure: '336',
      margin: '±2.1',
      unit: 'h',
      note: '47% of the time',
      dates: '29.5 days from 14 Mar 2027',
      tag: 'worked out',
    })
  })

  it('gives the longest night and the longest time without contact', () => {
    expect(exampleLine('night', site, answer())).toMatchObject({
      label: 'Longest night at Shackleton rim, east shoulder',
      figure: '206',
      margin: '±0.2',
      note: null,
    })
    expect(exampleLine('contact', site, answer())).toMatchObject({
      label: 'Longest time without contact at Shackleton rim, east shoulder',
      figure: '304',
      margin: '±0.2',
    })
  })

  it('says it all to a screen reader in one sentence, with the margin and where it came from', () => {
    expect(exampleLine('night', site, answer())?.spoken).toBe(
      'Longest night at Shackleton rim, east shoulder: about 206 hours, plus or minus 0.2 hours. 29.5 days from 14 Mar 2027. Worked out.',
    )
    expect(exampleLine('sunlight', site, answer())?.spoken).toContain('47% of the time')
  })

  it('marks a figure the dates cut short with the lower-bound sign, as the dashboard does', () => {
    const l = exampleLine('night', site, answer({ longest_dark_open: true }))
    expect(l?.figure).toBe('≥206')
    expect(l?.spoken).toContain('at least 206 hours')
  })

  it('says a margin under three minutes as timed to within a few minutes', () => {
    const l = exampleLine('night', site, answer({ longest_dark_tolerance_s: 60 }))
    expect(l?.margin).toBe('±<0.1')
    expect(l?.spoken).toContain('timed to within a few minutes')
  })
})

describe('when there is no honest example, there is none', () => {
  it('has nothing without an answer', () => {
    expect(exampleLine('night', site, undefined)).toBeNull()
    expect(exampleLine('night', site, null)).toBeNull()
  })

  it('leaves out a figure the service gives no margin for', () => {
    expect(exampleLine('night', site, answer({ longest_dark_tolerance_s: null }))).toBeNull()
    expect(exampleLine('contact', site, answer({ longest_blackout_tolerance_s: null }))).toBeNull()
    expect(exampleLine('sunlight', site, answer({ sunlit_tolerance_s: Number.NaN }))).toBeNull()
  })

  it('leaves out a figure that skims the skyline, and says nothing of one measure for the other', () => {
    const a = answer({ longest_dark_grazing: true })
    expect(exampleLine('night', site, a)).toBeNull()
    expect(exampleLine('contact', site, a)).not.toBeNull()
    expect(exampleLine('sunlight', site, a)).not.toBeNull()
  })

  it('leaves out a site outside the terrain model', () => {
    const a = answer({ meta: { uncertainty: { terrain_modelled: false } } } as unknown as Partial<MetricsDTO>)
    expect(exampleLine('night', site, a)).toBeNull()
  })

  it('leaves out a night that does not happen and a figure that is not a number', () => {
    expect(exampleLine('night', site, answer({ longest_dark_s: 0 }))).toBeNull()
    expect(exampleLine('contact', site, answer({ longest_blackout_s: Number.NaN }))).toBeNull()
  })

  it('leaves out dates it cannot read', () => {
    expect(exampleLine('night', { ...site, start: 'later' }, answer())).toBeNull()
    expect(exampleLine('night', { ...site, end: site.start }, answer())).toBeNull()
  })
})
