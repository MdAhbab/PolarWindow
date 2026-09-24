/**
 * Contract v2 adapters: missions, published dates and the calendar.
 *
 * The fixtures are real responses from the v2 API (IM-2's record, four list
 * items chosen for their edge cases, and three months of Connecting Ridge's
 * calendar). What is pinned here is the part a screen would get silently
 * wrong: a year-precision date drawn as one day, an unconfirmed field turned
 * into a zero, seconds left as seconds.
 */
import { describe, expect, it } from 'vitest'
import type { CalendarDTO, MissionDetailDTO, MissionListDTO } from './client'
import { qs } from './client'
import {
  adaptCalendar,
  adaptMission,
  adaptMissionDetail,
  adaptPublishedDate,
  latestAccessed,
  precisionSpanEnd,
} from './adapters'
import detailFixture from './__fixtures__/mission-im-2.detail.json'
import listFixture from './__fixtures__/missions.list.json'
import calendarFixture from './__fixtures__/connecting-ridge.calendar.json'

const detail = detailFixture as unknown as MissionDetailDTO
const list = listFixture as unknown as MissionListDTO
const calendar = calendarFixture as unknown as CalendarDTO
const byId = (id: string) => list.items.find((m) => m.id === id)!

describe('adaptPublishedDate', () => {
  it('keeps the published phrase and its precision, never a reformatted date', () => {
    const d = adaptPublishedDate({ date: '2027-01-01', precision: 'year', as_published: 'late 2027' })!
    expect(d.asPublished).toBe('late 2027')
    expect(d.precision).toBe('year')
  })

  it('spans the whole period its precision covers, so a year is not drawn as 1 January', () => {
    const y = adaptPublishedDate({ date: '2027-01-01', precision: 'year', as_published: 'late 2027' })!
    expect(y.startMs).toBe(Date.UTC(2027, 0, 1))
    expect(y.endMs).toBe(Date.UTC(2028, 0, 1))
    expect(precisionSpanEnd(Date.UTC(2026, 9, 1), 'quarter')).toBe(Date.UTC(2027, 0, 1))
    expect(precisionSpanEnd(Date.UTC(2026, 11, 1), 'month')).toBe(Date.UTC(2027, 0, 1))
    expect(precisionSpanEnd(Date.UTC(2024, 1, 22), 'day')).toBe(Date.UTC(2024, 1, 23))
  })

  it('passes a missing date through as null', () => {
    expect(adaptPublishedDate(null)).toBeNull()
  })
})

describe('adaptMission', () => {
  it('converts the surface-window summary to hours and keeps its flags', () => {
    const m = adaptMission(byId('im-2'))
    expect(m.summary).not.toBeNull()
    expect(m.summary!.sunHours).toBeCloseTo(byId('im-2').summary!.sunlit_s / 3600, 9)
    expect(m.summary!.longestDarkOpen).toBe(byId('im-2').summary!.longest_dark_open)
    expect(m.target?.coordinateKind).toBe('actual_landing')
    expect(m.siteId).toBe('mission-im-2')
  })

  it('carries a missing summary as null, not as zeros', () => {
    const m = adaptMission(byId('blue-moon-mk1-viper'))
    expect(m.summary).toBeNull()
    expect(m.surfaceWindow.basis).toBe('none')
    expect(m.landing?.precision).toBe('year')
  })

  it('keeps unconfirmed fields as null and lists them', () => {
    const m = adaptMission(byId('cs-8'))
    expect(m.provider).toBeNull()
    expect(m.target).toBeNull()
    expect(m.unconfirmedFields).toEqual(expect.arrayContaining(['provider', 'target']))
  })

  it('keeps a mission lost before landing with a launch and no landing', () => {
    const m = adaptMission(byId('peregrine-m1'))
    expect(m.landing).toBeNull()
    expect(m.launch?.precision).toBe('day')
    expect(m.target?.coordinateKind).toBe('feature_centre')
    expect(m.terrainModelled).toBe(false)
  })
})

describe('adaptMissionDetail', () => {
  const m = adaptMissionDetail(detail)

  it('keeps every payload with its source and classification', () => {
    expect(m.payloads).toHaveLength(detail.payloads.length)
    for (const p of m.payloads) {
      expect(p.sourceUrl).toMatch(/^https?:\/\//)
      expect(p.instrumentTypes.length).toBeGreaterThan(0)
    }
  })

  it('carries the target site and its terrain flag', () => {
    expect(m.site?.id).toBe('mission-im-2')
    expect(m.site?.terrainModelled).toBe(true)
    expect(m.meta.uncertainty.terrainModelled).toBe(true)
  })

  it('keeps a published ellipse absent rather than inventing one', () => {
    expect(m.ellipseRing).toBeNull()
    expect(m.unconfirmedFields).toContain('ellipse')
  })

  it('reports the latest date any source was read', () => {
    expect(latestAccessed(m.sources)).toBe('2026-09-23')
    expect(latestAccessed([])).toBeNull()
  })
})

describe('adaptCalendar', () => {
  const c = adaptCalendar(calendar)

  it('converts every bucket to hours and keeps the censoring flags', () => {
    expect(c.bucket).toBe('month')
    expect(c.items).toHaveLength(calendar.items.length)
    const [first] = c.items
    const raw = calendar.items[0]
    expect(first.sunHours).toBeCloseTo(raw.sunlit_s / 3600, 9)
    expect(first.longestDarkH).toBeCloseTo(raw.longest_dark_s / 3600, 9)
    expect(first.sunFraction).toBe(raw.sun_fraction_up)
    expect(first.longestBlackoutOpen).toBe(raw.longest_blackout_open)
    expect(first.startMs).toBe(Date.UTC(2027, 2, 1))
  })

  it('keeps the buckets contiguous', () => {
    for (let i = 1; i < c.items.length; i++) expect(c.items[i].startMs).toBe(c.items[i - 1].endMs)
  })
})

describe('qs', () => {
  it('sends a list as repeated keys, the way the API reads status and payload_type', () => {
    expect(qs({ status: ['planned', 'in_transit'], payload_type: ['volatiles'] })).toBe(
      '?status=planned&status=in_transit&payload_type=volatiles',
    )
  })

  it('drops empty values instead of sending key=', () => {
    expect(qs({ q: '', provider: undefined, region: null, status: [] })).toBe('')
  })
})
