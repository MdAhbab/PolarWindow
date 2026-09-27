// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, renderHook, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { renderApp } from '../../test/render'
import type {
  ContactDTO,
  LaunchCalendarDTO,
  QuantityDTO,
  ReadyDTO,
  RiskDTO,
  SectionDTO,
  SectionStatusDTO,
  TripDTO,
} from '../../lib/api/lifecycle'
import { api } from '../../lib/api/client'
import { useSection, type SectionView } from '../../lib/api/lifecycleQueries'
import { QuantityTile } from './QuantityTile'
import { SectionStates } from './Section'
import { JourneyBar } from './JourneyBar'
import { ReadinessList, RiskTable, sortItems } from './Readiness'
import { LimitBars, LimitTable } from './LimitBars'
import { coverageGaps, tripStretches } from './TripStrip'
import { shadowAndContact } from '../../screens/sections/TripSection'
import { seaWords, zoneWords } from '../../screens/sections/ReturnSection'
import { calendarDays } from './LaunchCalendar'
import { axisTicks, complexOf, contactRows } from './ContactChart'
import sectionsFixture from '../../lib/api/__fixtures__/lifecycle/sections.json'
import readyFixture from '../../lib/api/__fixtures__/lifecycle/ready.json'
import tripFixture from '../../lib/api/__fixtures__/lifecycle/trip.json'
import launchFixture from '../../lib/api/__fixtures__/lifecycle/launch.json'
import contactFixture from '../../lib/api/__fixtures__/lifecycle/contact.json'
import jobRunning from '../../lib/api/__fixtures__/lifecycle/job-running.json'
import jobDone from '../../lib/api/__fixtures__/lifecycle/job-done.json'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

const ready = (readyFixture as unknown as SectionDTO<ReadyDTO>).data
const trip = tripFixture as unknown as SectionDTO<TripDTO>
const launch = (launchFixture as unknown as SectionDTO<LaunchCalendarDTO>).data
const contact = (contactFixture as unknown as SectionDTO<ContactDTO>).data

const q = (over: Partial<QuantityDTO>): QuantityDTO => ({
  value: 12,
  unit: 'h',
  provenance: 'computed',
  pm: null,
  lo: null,
  hi: null,
  factor: null,
  open: false,
  no_margin_reason: null,
  missing_reason: null,
  source: null,
  ...over,
})

describe('QuantityTile: every margin form, and missing', () => {
  const tile = (el: HTMLElement) => el.closest('div.border') as HTMLElement

  it('±: figure, margin, unit; the sentence a screen reader hears', () => {
    render(<QuantityTile term="tripShadow" q={q({ value: 1.2, pm: 0.02 })} inRow={false} />)
    const t = tile(screen.getByText('Longest time in shadow'))
    expect(within(t).getByText('1.20')).toBeTruthy()
    expect(within(t).getByText('±0.02')).toBeTruthy()
    expect(within(t).getByText('about 1.20 hours, plus or minus 0.02 hours')).toBeTruthy()
  })

  it('a range, with the caller’s "if it flies as planned"', () => {
    render(<QuantityTile term="viaRelay" q={q({ value: null, lo: 12, hi: 31 })} note="if it flies as planned" scale={100} inRow={false} />)
    expect(screen.getByText('12–31')).toBeTruthy()
    expect(screen.getByText('if it flies as planned')).toBeTruthy()
    expect(screen.getByText('12 to 31 hours')).toBeTruthy()
  })

  it('a factor', () => {
    render(<QuantityTile term="tripShadow" q={q({ value: 4.1e9, unit: 'cm^-2', factor: 2 })} inRow={false} />)
    expect(screen.getByText('4.1 × 10⁹')).toBeTruthy()
    expect(screen.getByText('×/÷2')).toBeTruthy()
  })

  it('a lower bound', () => {
    render(<QuantityTile term="tripShadow" q={q({ value: 288, pm: 6, open: true })} inRow={false} />)
    expect(screen.getByText('≥288')).toBeTruthy()
    expect(screen.getByText(/^at least 288 hours/)).toBeTruthy()
  })

  it('no margin: says why under the number', () => {
    render(<QuantityTile term="sunAtLanding" q={q({ value: 2, unit: 'deg', no_margin_reason: 'A rule the team set.' })} inRow={false} />)
    expect(screen.getByText('2°')).toBeTruthy()
    expect(screen.getByText('No margin: a rule the team set.')).toBeTruthy()
  })

  it('no margin: a reason that opens with an acronym keeps its case', () => {
    render(<QuantityTile term="flightTime" q={q({ value: 6.1, unit: 'd', no_margin_reason: 'TLI to closest approach.' })} inRow={false} />)
    expect(screen.getByText('No margin: TLI to closest approach.')).toBeTruthy()
  })

  it('missing: a dash and the reason, never a zero', () => {
    render(<QuantityTile term="tripShadow" q={q({ value: null, missing_reason: 'No trajectory yet' })} inRow={false} />)
    expect(screen.getByText('No trajectory yet')).toBeTruthy()
    expect(screen.getByText('Not available: No trajectory yet')).toBeTruthy()
    expect(screen.queryByText('0')).toBeNull()
  })

  it('where it comes from opens from the label (invariant 10); a live number shows its age', () => {
    render(
      <QuantityTile term="boosterWaves" q={q({ value: 2.5, unit: 'm', provenance: 'entered', source: 'A. Rahman', no_margin_reason: 'A limit.' })} age="as of 40 min ago" inRow={false} />,
    )
    expect(screen.getByText('as of 40 min ago')).toBeTruthy()
    const explain = screen.getByText(/Entered by A. Rahman/).closest('p') as HTMLElement
    expect(explain.hidden).toBe(true)
    screen.getByRole('button', { name: /Waves at the booster landing zone/ }).click()
  })
})

describe('SectionStates: the same states on every section', () => {
  const terms = ['tripSunlight', 'tripHeard', 'tripShadow', 'tripUnheard']
  const show = (view: SectionView<TripDTO>) =>
    render(
      <SectionStates view={view} terms={terms}>
        {(s) => <p>answer for {s.data.source}</p>}
      </SectionStates>,
    )

  it('loading: the numbers’ labels with no values, never zeros', () => {
    show({ status: 'pending' })
    expect(screen.getByText('Longest time in shadow')).toBeTruthy()
    expect(screen.getAllByText('——')).toHaveLength(4)
  })

  it('working it out: real progress and what still works', () => {
    show({ status: 'working', job: { job_id: 1, status: 'running', progress: 0.35, message: 'Working out passes', poll_after_s: 2 } })
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('35')
    expect(screen.getByText('Working out passes')).toBeTruthy()
    expect(screen.getByText(/The other sections and the landing numbers are unaffected/)).toBeTruthy()
  })

  it('a queued job says it has not started, without a fake number', () => {
    show({ status: 'working', job: { job_id: 1, status: 'queued', progress: null, message: 'Queued', poll_after_s: 2 } })
    expect(screen.getByRole('progressbar').getAttribute('aria-valuetext')).toBe('Not started yet')
  })

  it('an error is the server’s problem, with what still works and a retry', () => {
    const retry = vi.fn()
    show({ status: 'error', error: { title: 'Trip engine down', detail: 'x', stillWorks: 'Landing works.' }, retry })
    expect(screen.getByText('Trip engine down')).toBeTruthy()
    expect(screen.getByText('Landing works.')).toBeTruthy()
  })

  it('a refusal its status explains is that state, not an error', async () => {
    const { ApiError } = await import('../../lib/api/client')
    render(
      <SectionStates
        view={{ status: 'error', error: new ApiError(404, { detail: { title: 'Not found' } }), retry: () => {} }}
        terms={terms}
        status={{ section: 'return', state: 'not_applicable', summary: 'No capsule returns; the booster was expended', as_of: null }}
      >
        {() => <p>never</p>}
      </SectionStates>,
    )
    expect(screen.getByText('Does not apply')).toBeTruthy()
    expect(screen.getByText('No capsule returns; the booster was expended')).toBeTruthy()
    expect(screen.queryByText('Not found')).toBeNull()
  })

  it('the answer', () => {
    show({ status: 'answer', section: trip, refreshing: false })
    expect(screen.getByText('answer for flown')).toBeTruthy()
  })
})

describe('JourneyBar', () => {
  it('six links in order, each with its state in words, the open one marked', () => {
    renderApp(
      <JourneyBar missionId="im-2" current="trip" statuses={(sectionsFixture as unknown as SectionDTO<SectionStatusDTO[]>).data} loading={false} />,
    )
    const links = screen.getAllByRole('link')
    expect(links.map((l) => l.getAttribute('href'))).toEqual([
      '/missions/im-2/ready',
      '/missions/im-2/launch',
      '/missions/im-2/trip',
      '/missions/im-2/landing',
      '/missions/im-2/contact',
      '/missions/im-2/return',
    ])
    expect(links[2].getAttribute('aria-current')).toBe('page')
    expect(links.filter((l) => l.getAttribute('aria-current'))).toHaveLength(1)
    expect(links[4].textContent).toContain('Working it out')
    expect(links[5].textContent).toContain('Does not apply')
  })

  it('says why the summaries are missing, and still navigates', () => {
    renderApp(<JourneyBar missionId="im-2" current="ready" statuses={undefined} loading={false} problem="Not found" />)
    expect(screen.getAllByRole('link')).toHaveLength(6)
    expect(screen.getByText('Step summaries are not available: Not found')).toBeTruthy()
  })
})

describe('readiness, risks and limits', () => {
  it('blocked first, then the least advanced, then the items with no state entered', () => {
    const sorted = sortItems(ready.items)
    const order = sorted.map((i) => i.state)
    expect(order[0]).toBe('blocked')
    expect(order.indexOf('in_test')).toBeLessThan(order.indexOf('ready'))
    expect(sorted[sorted.length - 1].state_known).toBe(false)
  })

  it('an item nobody has entered a state for says so, and is never shown as "not started"', () => {
    renderApp(<ReadinessList items={ready.items} />)
    expect(screen.getAllByText('Not entered yet').length).toBeGreaterThan(0)
    expect(screen.queryByText('Not started')).toBeNull()
  })

  it('a blocked item says so in words and gives its reason, not colour alone', () => {
    renderApp(<ReadinessList items={ready.items} />)
    expect(screen.getAllByText(/Waiting on the updated debris analysis/).length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: /^Change/ })).toBeNull()
  })

  it('risks: likelihood and consequence side by side, never multiplied', () => {
    renderApp(<RiskTable risks={ready.risks as RiskDTO[]} />)
    expect(screen.getAllByText('L 2 · C 5').length).toBe(1)
    // 2 × 5 would be 10: no product appears anywhere.
    expect(screen.queryByText('10')).toBeNull()
  })

  it('over the team’s limit: the words and the amount, beside the glyph', () => {
    render(
      <LimitBars
        rows={[
          { id: 'w', label: 'Wind', value: q({ value: 9.5, unit: 'm/s', pm: 2.1 }), limit: q({ value: 8, unit: 'm/s', provenance: 'entered', no_margin_reason: 'x' }) },
          { id: 'n', label: 'Waves', value: q({ value: 1.8, unit: 'm', pm: 0.4 }), limit: null },
        ]}
      />,
    )
    expect(screen.getByText('9.5 ±2.1 m/s: 1.5 m/s over the team’s limit')).toBeTruthy()
    expect(screen.getByText('1.8 ±0.4 m; no limit entered by the team')).toBeTruthy()
  })

  it('return: a limit not entered is a missing number with its reason, read as "none entered", never 0', () => {
    const none = q({ value: null, unit: 'm/s', provenance: 'entered', missing_reason: 'Not published by the launch provider.' })
    render(<LimitTable rows={[{ id: 'w', label: 'Wind', value: q({ value: 9.5, unit: 'm/s', pm: 2.1 }), limit: none }]} />)
    const cells = screen.getAllByRole('cell').map((c) => c.textContent)
    expect(cells).toEqual(['9.5 ±2.1 m/s', 'none entered', '—', '—'])
  })

  it('return: the zone with its size only when published, and the sea in one sentence', () => {
    expect(zoneWords({ lat_deg: 28.485712, lon_deg: -80.542963, pm_km: null })).toBe('near 28.5°N 80.5°W')
    expect(zoneWords({ lat_deg: 30.9, lon_deg: -74.9, pm_km: 12 })).toBe('near 30.9°N 74.9°W, ±12 km')
    const past = 'This launch is in the past; the sea and wind then were not recorded.'
    const none = q({ value: null, unit: 'm', provenance: 'entered', missing_reason: 'Not published.' })
    const base = { zone: null, note: '', hazard_area_seen: null, limits: { wave_height_m: none, wind_m_s: { ...none, unit: 'm/s' } } }
    // On land there are no waves: one shared reason is the sentence.
    expect(seaWords({ ...base, landing: 'land', wave_height_m: null, wind_m_s: q({ value: null, unit: 'm/s', missing_reason: past }) })).toBe(past)
    // Different reasons: one line pointing at the numbers.
    expect(
      seaWords({
        ...base,
        landing: 'unknown',
        wave_height_m: q({ value: null, unit: 'm', missing_reason: 'Wave forecasts are not recorded yet.' }),
        wind_m_s: q({ value: null, unit: 'm/s', missing_reason: 'Wind forecasts are not worked out yet.' }),
      }),
    ).toBe('Neither the sea nor the wind at the zone is forecast yet; each number below says why.')
    // A forecast, against the team's limit when one is entered.
    expect(
      seaWords({
        ...base,
        landing: 'droneship',
        wave_height_m: q({ value: 1.8, unit: 'm', pm: 0.4 }),
        wind_m_s: q({ value: null, unit: 'm/s', missing_reason: 'x' }),
        limits: { ...base.limits, wave_height_m: q({ value: 2.5, unit: 'm', provenance: 'entered', no_margin_reason: 'A limit the team entered.' }) },
      }),
    ).toBe('Waves there are forecast at 1.8 ±0.4 m against the team’s limit of 2.5 m.')
  })
})

describe('the charts’ arrays, shared with their tables', () => {
  it('trip: shadow stretches, and the gaps between heard stretches', () => {
    const rows = tripStretches(trip.data)
    expect(rows.filter((r) => r.kind === 'shadow')).toHaveLength(1)
    const unheard = rows.filter((r) => r.kind === 'unheard').map((r) => (r.end - r.start) / 3_600_000)
    expect(unheard).toEqual([6, 4])
  })

  it('trip with gaps in the data (IM-1): no line across a gap, and a gap is no data, not out of contact', () => {
    const t0 = Date.UTC(2024, 1, 16, 17)
    const iso = (ms: number) => new Date(ms).toISOString()
    const minute = 60_000
    // Two hours of samples, five hours with none, then two more hours.
    const times = [...Array.from({ length: 121 }, (_, i) => t0 + i * minute), ...Array.from({ length: 121 }, (_, i) => t0 + 7 * 60 * minute + i * minute)]
    const gappy: TripDTO = {
      ...trip.data,
      start: iso(times[0]),
      end: iso(times[times.length - 1]),
      samples: times.map((t) => ({ t: iso(t), earth_km: 250_000, moon_km: 300_000, light: 'lit' as const, heard: true })),
      shadow: [],
      heard: [
        { start: iso(times[0]), end: iso(times[120]), open_start: true, open_end: true },
        { start: iso(times[121]), end: iso(times[241]), open_start: true, open_end: true },
      ],
      // The service lists the stretches the reconstruction covers; the second starts a few microseconds late.
      covered: [
        { start: iso(times[0]), end: iso(times[120]), open_start: false, open_end: false },
        { start: `${iso(times[121]).slice(0, -1)}020Z`, end: iso(times[241]), open_start: false, open_end: false },
      ],
      burns: [],
    }
    expect(coverageGaps(gappy)).toEqual([{ start: times[120], end: times[121] }])
    const rows = tripStretches(gappy)
    expect(rows.map((r) => r.kind)).toEqual(['nodata'])
    expect((rows[0].end - rows[0].start) / 3_600_000).toBe(5)
    // One stretch covering the trip: no gaps.
    expect(coverageGaps(trip.data)).toEqual([])
  })

  it('trip gaps come from the covered stretches, not the spacing of the samples', () => {
    const iso = (ms: number) => new Date(ms).toISOString()
    const t0 = Date.parse(trip.data.start!)
    const t1 = Date.parse(trip.data.end!)
    const mid = t0 + (t1 - t0) / 2
    const hour = 3_600_000
    // Evenly spaced samples, but the reconstruction leaves out three hours in the middle and the last hour.
    const covered = [
      { start: iso(t0), end: iso(mid), open_start: false, open_end: false },
      { start: iso(mid + 3 * hour), end: iso(t1 - hour), open_start: false, open_end: false },
    ]
    expect(coverageGaps({ ...trip.data, covered })).toEqual([
      { start: mid, end: mid + 3 * hour },
      { start: t1 - hour, end: t1 },
    ])
    // Two stretches that meet within a second are one: no gap at the seam.
    const seam = [
      { start: iso(t0), end: iso(mid), open_start: false, open_end: false },
      { start: iso(mid + 400), end: iso(t1), open_start: false, open_end: false },
    ]
    expect(coverageGaps({ ...trip.data, covered: seam })).toEqual([])
    // A trip that lists no covered stretches (a designed one) has no gaps.
    expect(coverageGaps({ ...trip.data, covered: [] })).toEqual([])
  })

  it('trip answer: never in shadow, heard the whole time, and "at least" when the dates cut a stretch short', () => {
    const n = trip.data.numbers
    const zero = { ...n.longest_shadow_h, value: 0, pm: null }
    expect(shadowAndContact({ ...n, longest_shadow_h: zero, longest_unheard_h: zero })).toBe(
      'It is never in shadow, and a ground station can hear it the whole time.',
    )
    expect(shadowAndContact({ ...n, longest_shadow_h: zero, longest_unheard_h: { ...zero, value: 0.12, open: true } })).toBe(
      'It is never in shadow; the longest time without contact is at least 0.12 h.',
    )
    // With gaps in the data, it is said of the covered hours only.
    expect(shadowAndContact({ ...n, longest_shadow_h: zero, longest_unheard_h: zero }, 30.1)).toBe(
      'In the 30.1 hours NASA’s reconstruction covers, it is never in shadow, and a ground station can hear it the whole time.',
    )
  })

  it('launch calendar: days with opportunities, and runs of empty days as one line', () => {
    const days = calendarDays(launch.opportunities)
    expect(days.filter((d) => d.kind === 'day')).toHaveLength(6)
    expect(days.find((d) => d.kind === 'gap')).toEqual({ kind: 'gap', days: 1 })
  })

  it('contact: antennas of one Deep Space Network complex share a row; the table keeps each antenna', () => {
    const two = {
      ...contact,
      nodes: [...contact.nodes, { id: 'dss-24', kind: 'station' as const, name: 'DSS-24', operator: 'NASA JPL', status: 'operating' as const, orbit: null, launch_note: null }],
      links: [...contact.links, { from: 'lander', to: 'dss-24', stretches: [contact.links[0].stretches[0]], data_rate_kbps: null, margin_db: null }],
    }
    const rows = contactRows(two)
    const goldstone = rows.find((r) => r.key === 'goldstone')!
    expect(goldstone.label).toBe('Goldstone, California')
    expect(goldstone.links).toHaveLength(2)
    expect(goldstone.caption).toBe('Deep Space Network, 2 antennas')
    expect(complexOf({ id: 'dss-63' } as never)?.name).toBe('Madrid, Spain')
    expect(complexOf({ id: 'ksat-1' } as never)).toBeNull()
  })

  it('contact axis: labels stay inside the dates, in hours for a short stay and days for a long one', () => {
    const t0 = Date.UTC(2025, 2, 6, 17, 30)
    const short = axisTicks(t0, t0 + 12.75 * 3_600_000)
    expect(short[0].label).toBe('6 Mar 2025')
    expect(short.every((t) => t.at < t0 + 12.75 * 3_600_000)).toBe(true)
    expect(short.slice(1).map((t) => t.label)).toEqual(['21:00', '00:00', '03:00'])
    const long = axisTicks(t0, t0 + 14 * 86_400_000)
    expect(long.slice(1).map((t) => t.label)).toEqual(['Day 2', 'Day 4', 'Day 6', 'Day 8', 'Day 10', 'Day 12'])
  })

  it('contact: a relay with no real orbit is a range row, drawn after the real links', () => {
    const rows = contactRows(contact)
    expect(rows[rows.length - 1].planned).toBe(true)
    expect(rows.filter((r) => r.planned)).toHaveLength(1)
  })
})

describe('useSection follows a 202 through its job', () => {
  it('working while the job runs, then the answer once it is done', async () => {
    const trips = vi
      .spyOn(api, 'trip')
      .mockResolvedValueOnce({ kind: 'job', job: jobRunning as never })
      .mockResolvedValue({ kind: 'answer', section: trip })
    const jobs = vi.spyOn(api, 'job').mockResolvedValueOnce(jobRunning as never).mockResolvedValue(jobDone as never)
    vi.spyOn(api, 'sections').mockResolvedValue(sectionsFixture as never)
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
    const { result } = renderHook(() => useSection<TripDTO>('trip', 'im-2', (s) => api.trip('im-2', s)), { wrapper })
    await waitFor(() => expect(result.current.status).toBe('working'))
    await waitFor(() => expect(result.current.status).toBe('answer'), { timeout: 8000 })
    expect(jobs).toHaveBeenCalled()
    expect(trips).toHaveBeenCalledTimes(2)
  }, 10_000)

  it('a failed job is an error with what still works, not an endless spinner', async () => {
    vi.spyOn(api, 'trip').mockResolvedValue({ kind: 'job', job: { ...jobRunning, status: 'failed', message: 'Out of memory' } as never })
    vi.spyOn(api, 'sections').mockResolvedValue(sectionsFixture as never)
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
    const { result } = renderHook(() => useSection<TripDTO>('trip', 'im-2', (s) => api.trip('im-2', s)), { wrapper })
    await waitFor(() => expect(result.current.status).toBe('error'))
    const e = (result.current as { error: { title: string; detail: string; stillWorks: string } }).error
    expect(e.detail).toBe('Out of memory')
    expect(e.stillWorks).toMatch(/other sections/)
  })
})
