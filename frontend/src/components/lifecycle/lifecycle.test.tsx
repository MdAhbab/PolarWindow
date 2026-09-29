// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, renderHook, screen, waitFor, within } from '@testing-library/react'
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
import { CorrectionsRow, shadowAndContact } from '../../screens/sections/TripSection'
import { checkWords, climatologyWords, forecastLine, observedWords, percentWords, rulesSummary, WeatherRuleTable } from './WeatherRules'
import { RadiationRow, radiationSentence, screeningFigure } from './Radiation'
import { eventCountWords, outlookSentence, readingAge, spaceWeatherSentence, SpaceWeatherRow } from './SpaceWeather'
import spaceWeatherFixture from '../../lib/api/__fixtures__/lifecycle/space-weather.json'
import weatherFixture from '../../lib/api/__fixtures__/lifecycle/launch-weather.json'
import type { RadiationDTO, SpaceWeatherDTO } from '../../lib/api/lifecycle'
import { forecastChangeWords, limitDraft, limitsToSend, shownForecast } from '../../screens/sections/LaunchSection'
import type { EnteredLimitDTO, LaunchWeatherDTO, RuleRowDTO } from '../../lib/api/lifecycle'
import { capsuleLimitWords, CapsuleCheckRow, seaWords, zoneWords } from '../../screens/sections/ReturnSection'
import returnFixture from '../../lib/api/__fixtures__/lifecycle/return.json'
import { oldFeedsWords } from './OldFeeds'
import type { CapsuleModelCheckDTO, FeedDTO } from '../../lib/api/lifecycle'
import { LaunchCalendar, LaunchTable, calendarDays, periodWords } from './LaunchCalendar'
import { axisTicks, complexOf, contactRows, plannedWords } from './ContactChart'
import { contactAnswer, coveredWords, numberWords, orbiterWords, orbitWords, relayList } from '../../screens/sections/ContactSection'
import { bearingWords, rayRuns, rayWords, roverSentence, ViewshedPanel } from './RoverSight'
import roverFixture from '../../lib/api/__fixtures__/lifecycle/rover.json'
import roverUnresolvable from '../../lib/api/__fixtures__/lifecycle/rover-unresolvable.json'
import type { RoverSightDTO } from '../../lib/api/lifecycle'
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

  it('trip corrections: a budget, never a prediction, each size with its sample and every assumption', () => {
    const c = trip.data.corrections!
    render(<CorrectionsRow c={c} note={null} />)
    expect(screen.getByText('Corrections on the way')).toBeTruthy()
    expect(screen.getByText(c.label)).toBeTruthy()
    const text = document.body.textContent ?? ''
    expect(text).toContain('a budget: 18.1 m/s in 99 of 100 runs')
    expect(text).toContain('In 1,000 runs of the flight as planned')
    expect(text).toContain('(16.5–19.9 m/s, allowing for the number of runs)')
    expect(text).toContain('Every run passed close to the Moon.')
    const table = screen.getByRole('table')
    // Three corrections and their total, each at 95 and at 99 of 100 runs.
    expect(within(table).getAllByRole('row')).toHaveLength(5)
    expect(within(table).getByRole('rowheader', { name: 'All 3 together' })).toBeTruthy()
    for (const a of c.assumptions) expect(screen.getByText(a.value)).toBeTruthy()
    cleanup()
    render(<CorrectionsRow c={null} note="No trip has been worked out." />)
    expect(screen.getByText('No trip has been worked out.')).toBeTruthy()
    expect(screen.queryByRole('table')).toBeNull()
  })

  it('weather rules: a small share keeps a digit, and lightning is seen now, not at the launch', () => {
    expect(percentWords(0.0099)).toBe('1.0%')
    expect(percentWords(0.004)).toBe('0.4%')
    expect(percentWords(0.123)).toBe('12%')
    expect(percentWords(0)).toBe('0%')
    expect(observedWords({ state: 'clear', detail: 'None within 10 nmi.' }).lead).toBe('Seen now: clear.')
    expect(observedWords({ state: 'seen', detail: '3 flashes within 10 nmi.' })).toEqual({ lead: 'Seen now:', detail: '3 flashes within 10 nmi.' })
    expect(observedWords({ state: 'no_data', detail: 'Watched by the range.' })).toEqual({ detail: 'Watched by the range.' })
  })

  describe('one forecast beside the runs, and who disagrees', () => {
    const rules = (weatherFixture as unknown as { data: LaunchWeatherDTO }).data.rules
    const wind = rules[0]
    const hrrr = wind.one_forecast[0]
    const nws = wind.one_forecast[1]

    it('each forecast is named in full, answers first, then how the number was made and how that forecast did', () => {
      const h = forecastLine(hrrr)
      expect(h.lead).toBe('High-Resolution Rapid Refresh (HRRR) forecast:')
      expect(h.answer).toBe('14.2 m/s, over the limit.')
      expect(h.how).toBe("One forecast, at the rule's height from the model's 10 m and 80 m winds.")
      expect(h.note).toMatch(/^Checked against KXMR for 2021 to 2025/)
      const n = forecastLine(nws)
      expect(n.lead).toBe('National Weather Service (NWS) forecast:')
      expect(n.answer).toBe('8.9 m/s, under the limit.')
      expect(n.note).toBe('The National Weather Service keeps no archive of its forecasts, so this one cannot be checked against observations.')
    })

    it('says whether the shares shown were checked: all, none, or by system; nothing where no share is shown', () => {
      const share = (checked: boolean) => ({ k: 3, n: 31, lo: 0.02, hi: 0.26, checked })
      const per = (...cs: (boolean | null)[]) => ({
        per_system: cs.map((c, i) => ({ system: (['GEFS', 'ECMWF-ENS', 'AIFS-ENS'] as const)[i], share: c === null ? null : share(c), missing_reason: c === null ? 'not recorded' : null })),
      })
      expect(checkWords(per(true, null, null))).toBe('checked against observations')
      expect(checkWords(per(false, false, null))).toBe('not yet checked against observations')
      expect(checkWords(per(true, false, null))).toBe('checked against observations for NOAA GEFS, not yet for ECMWF ENS')
      expect(checkWords(per(null, null, null))).toBeNull()
      expect(checkWords({ per_system: [] })).toBeNull()
    })

    it('the closed row counts the rules that disagree and the rules checked against observations', () => {
      expect(rulesSummary(rules)).toBe('6 rules; models disagree on 1')
      const checked = rules.map((r, i) => (i === 0 ? { ...r, per_system: r.per_system.map((p, j) => (j === 0 && p.share ? { ...p, share: { ...p.share, checked: true } } : p)) } : r))
      expect(rulesSummary(checked)).toBe('6 rules; models disagree on 1; 1 checked against observations')
      expect(rulesSummary([wind])).toBe('1 rule; models disagree on 1')
    })

    it('the table gives the disagreement in a sentence and each forecast with its note; a checked rule says so', () => {
      render(<WeatherRuleTable rules={rules} />)
      // The table and the phone list carry the same words.
      expect(screen.getAllByText('Models disagree').length).toBeGreaterThan(0)
      expect(screen.getAllByText(wind.disagreement_note as string).length).toBeGreaterThan(0)
      expect(screen.getAllByText(nws.note as string).length).toBeGreaterThan(0)
      expect(screen.getAllByText(hrrr.note as string).length).toBeGreaterThan(0)
      expect(screen.getAllByText('High-Resolution Rapid Refresh (HRRR) forecast:').length).toBeGreaterThan(0)
      // Only the wind rule disagrees, so the sentence is shown once per layout, not for every rule.
      expect(screen.getAllByText('Models disagree')).toHaveLength(2)
      expect(document.body.textContent).toContain('A forecast model can answer this · not yet checked against observations')
      expect(document.body.textContent).not.toContain('· checked against observations ·')
      cleanup()
      const checked = rules.map((r, i) => (i === 0 ? { ...r, per_system: r.per_system.map((p) => (p.share ? { ...p, share: { ...p.share, checked: true } } : p)) } : r))
      render(<WeatherRuleTable rules={checked} />)
      expect(document.body.textContent).toContain('A forecast model can answer this · checked against observations · nasa.gov')
    })
  })

  it('team weather limits: start as entered; an empty field is no limit; a limit for a rule not shown is sent as it stands', () => {
    const rule = (id: string, units: string[]) => ({ id, units }) as unknown as RuleRowDTO
    const e = (rule_id: string, value: number, unit: string, note: string | null): EnteredLimitDTO => ({
      rule_id, value, unit, note, entered_by: 'N', entered_at: '2026-09-20T00:00:00Z',
    })
    const shear = rule('shear', [])
    const tops = rule('tops', ['ft', 'm'])
    const stored = [e('tops', 10000, 'ft', 'From the range.'), e('elsewhere', 30, 'kt', null)]
    expect(limitDraft(tops, stored[0])).toEqual({ value: '10000', unit: 'ft', note: 'From the range.' })
    expect(limitDraft(tops, undefined)).toEqual({ value: '', unit: 'ft', note: '' })
    expect(limitDraft(shear, undefined).unit).toBe('')
    const drafts = { shear: { value: '25', unit: '', note: '' }, tops: { value: '', unit: 'ft', note: 'From the range.' } }
    expect(limitsToSend([shear, tops], drafts, stored).errors).toEqual({ 'shear-unit': 'The unit the limit is given in.' })
    drafts.shear.unit = 'kt'
    expect(limitsToSend([shear, tops], drafts, stored)).toEqual({
      limits: [
        { rule_id: 'shear', value: 25, unit: 'kt', note: null },
        { rule_id: 'elsewhere', value: 30, unit: 'kt', note: null },
      ],
      errors: {},
    })
    expect(limitsToSend([shear], { shear: { value: '-1', unit: 'kt', note: '' } }, []).errors).toEqual({ shear: 'A number above zero.' })
  })

  it('launch calendar: days with opportunities, and runs of empty days as one line', () => {
    const days = calendarDays(launch.opportunities)
    expect(days.filter((d) => d.kind === 'day')).toHaveLength(6)
    expect(days.find((d) => d.kind === 'gap')).toEqual({ kind: 'gap', days: 1 })
  })

  it('launch calendar: a launch period is said in words, in the mark\u2019s name and in the table, and one instant is not', () => {
    const one = launch.opportunities[0]
    expect(periodWords(one)).toBeNull()
    const inDay = { ...one, kind: 'window' as const, window_open: '2024-01-08T07:18:00Z', window_close: '2024-01-08T08:03:00Z' }
    expect(periodWords(inDay)).toBe('07:18 to 08:03 UTC')
    // Past midnight the dates are given, so the close is not read as the same day.
    expect(periodWords({ ...inDay, window_open: '2024-01-08T23:40:00Z', window_close: '2024-01-09T00:25:00Z' })).toBe('8 January 2024, 23:40 UTC to 9 January 2024, 00:25 UTC')
    // A period whose ends the service does not give is not made up.
    expect(periodWords({ ...inDay, window_close: null })).toBeNull()
    const withPeriod = { ...one, ...inDay, t0: { ...one.t0, value: Date.parse('2024-01-08T07:18:38Z') / 1000 } }
    render(<LaunchCalendar opportunities={[withPeriod]} selected={withPeriod.id} onSelect={() => {}} />)
    expect(screen.getByRole('button', { name: /, a launch period from 07:18 to 08:03 UTC$/ })).toBeTruthy()
    cleanup()
    render(<LaunchTable opportunities={[withPeriod, { ...one, id: 'other', t0: { ...one.t0, value: withPeriod.t0.value + 86400 } }]} />)
    expect(screen.getByText('Launch period, 07:18 to 08:03 UTC')).toBeTruthy()
    expect(screen.getByText('One instant')).toBeTruthy()
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

  it('contact: a relay with no real orbit is a range row after the real links, with or without a link; orbiters come last, never as relays', () => {
    const rows = contactRows(contact)
    const planned = rows.findIndex((r) => r.planned)
    expect(rows.filter((r) => r.planned)).toHaveLength(1)
    expect(rows[planned].caption).toBe('relay · not launched')
    expect(rows.slice(0, planned).every((r) => !r.planned && !r.orbiter)).toBe(true)
    const orbiters = rows.slice(planned + 1)
    expect(orbiters.map((r) => r.label)).toEqual(['Lunar Reconnaissance Orbiter', 'Danuri'])
    expect(orbiters.every((r) => r.orbiter && !r.relayId && r.caption === 'could see the lander; not a relay')).toBe(true)
    expect(orbiters[0].links[0].stretches).toHaveLength(contact.orbiters!.find((o) => o.id === 'lro')!.pass_count)
    // A trajectory that stops early leaves the rest of the dates as no data, not out of view.
    expect(orbiters[0].noData).toEqual([])
    expect(orbiters[1].noData).toEqual([{ start: Date.parse('2025-03-11T00:00:00Z'), end: Date.parse(contact.end!) }])
    // One with no trajectory for these dates has no row at all.
    const none = contactRows({ ...contact, orbiters: [{ ...contact.orbiters![0], covered: null, passes: [], pass_count: 0 }] })
    expect(none.some((r) => r.orbiter)).toBe(false)
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

describe('Official forecast: the one shown, and taking it back', () => {
  const f = (id: number, pct: number, at: string, by = 'A. Rahman') => ({
    id,
    probability_pct: pct,
    concerns: ['Cumulus cloud rule'],
    pdf_url: `https://example.test/${pct}.pdf`,
    entered_by: by,
    entered_at: at,
  })
  const older = f(7, 10, '2026-09-28T10:00:00Z')
  const saved = f(8, 20, '2026-09-28T11:00:00Z')
  // The weather answer carries the same stored row (same id), as a separate object.
  const stored = { ...saved }
  it('shows the newest at hand', () => {
    expect(shownForecast([older, saved, null], [])).toBe(saved)
    expect(shownForecast([null, undefined], [])).toBeNull()
  })
  it('leaves out one taken back, whichever answer still carries it (by its id)', () => {
    expect(shownForecast([stored, null, older], [saved])).toBe(older)
    expect(shownForecast([stored, null, null], [saved])).toBeNull()
    // Another forecast of the same percent, entered at the same second, is not the one taken back.
    expect(shownForecast([f(9, 20, '2026-09-28T11:00:00Z')], [saved])?.id).toBe(9)
    // Two entered at the same time: the later row.
    expect(shownForecast([saved, f(9, 30, '2026-09-28T11:00:00Z')], [])?.id).toBe(9)
  })
  it('says what each history entry did', () => {
    const e = { at: '', by: 'A', note: null }
    expect(forecastChangeWords({ ...e, action: 'set', before: null, after: older })).toBe('Entered 10% (cumulus cloud rule)')
    expect(forecastChangeWords({ ...e, action: 'set', before: older, after: saved })).toBe(
      'Entered 20% (cumulus cloud rule); before it: 10% (cumulus cloud rule)',
    )
    expect(forecastChangeWords({ ...e, action: 'delete', before: saved, after: null })).toBe('Took back 20% (cumulus cloud rule); shown now: none')
  })
})

describe('Radiation on the way: screening only', () => {
  const rad = tripFixture.data.radiation as unknown as RadiationDTO
  it('opens with the belts and the cosmic-ray dose, each with its margin', () => {
    expect(radiationSentence(rad)).toBe(
      'At least 21.1 ×/÷2 h in the radiation belts over 4 passes. Cosmic rays give 0.17 ±0.05 mGy a day on the way and 0.12 ±0.04 mGy a day at the landing spot, before any shielding.',
    )
  })
  it('says a lower bound of zero is not counted, never "≥0"', () => {
    const b = { ...rad.belt_hours, value: 0, open: true }
    expect(screeningFigure(b)).toBe('none counted')
    expect(radiationSentence({ ...rad, belt_hours: b, belt_passes: 0, surface: null })).toMatch(
      /^No time in the radiation belts is counted \(the climb out is not in NASA’s reconstruction\)\. Cosmic rays give .+ on the way, before any shielding\.$/,
    )
  })
  it('says why the belts are not counted, once, when the reconstruction starts beyond them (IM-1)', () => {
    const why = 'NASA’s reconstruction starts 242,208 km above Earth, beyond the belts, so the crossing of them is not in it and is not counted.'
    const gone = (x: QuantityDTO) => ({ ...x, value: null, factor: null, open: false, missing_reason: why })
    const im1 = { ...rad, belt_hours: gone(rad.belt_hours), belt_passes: 0, electron_fluence_gt1mev: gone(rad.electron_fluence_gt1mev), fluence_gt10mev: gone(rad.fluence_gt10mev) }
    expect(radiationSentence(im1)).toMatch(/^NASA’s reconstruction starts 242,208 km above Earth, beyond the belts, so the crossing of them is not in it and is not counted\. Cosmic rays give /)
    renderApp(<RadiationRow r={im1} note={null} />)
    fireEvent.click(screen.getByText('Radiation on the way'))
    expect(screen.getAllByText('Not counted, as above')).toHaveLength(2)
    expect(screen.queryByText(/≥0|×\/÷2 per cm²/)).toBeNull()
  })
  it('a lander lost on the way has no surface dose, and says why (Peregrine)', () => {
    const lost = { ...rad, surface: null, surface_note: 'It was lost before reaching the Moon, so there is no surface dose.' }
    expect(radiationSentence(lost)).toMatch(/ on the way, before any shielding\.$/)
    renderApp(<RadiationRow r={lost} note={null} />)
    fireEvent.click(screen.getByText('Radiation on the way'))
    expect(screen.getByText('It was lost before reaching the Moon, so there is no surface dose.')).toBeTruthy()
    expect(screen.queryByText('Cosmic-ray dose at the landing spot')).toBeNull()
  })
  it('an open sky taken as flat says it is assumed, and why (Blue Ghost 1)', () => {
    renderApp(<RadiationRow r={rad} note={null} />)
    fireEvent.click(screen.getByText('Radiation on the way'))
    expect(screen.getByText(/mGy a day \(100% of the sky open, assumed\)$/)).toBeTruthy()
    expect(screen.getByText(/^The elevation model does not cover this landing site, so its horizon is taken as flat/)).toBeTruthy()
    expect(screen.getByText(/^One solar particle event crossed NOAA's threshold .+; its fluence is not worked out\.$/)).toBeTruthy()
  })
  it('shows the fluences as powers of ten with their factor, and why there is none', () => {
    expect(screeningFigure(rad.electron_fluence_gt1mev)).toMatch(/^≥[\d.]+ × 10¹⁰ ×\/÷2 per cm²$/)
    renderApp(<RadiationRow r={null} note="No trip has been worked out." />)
    expect(screen.getByText('No trip has been worked out.')).toBeTruthy()
  })
})

describe('Space weather now', () => {
  const sw = spaceWeatherFixture.data as unknown as SpaceWeatherDTO
  const meta = spaceWeatherFixture.meta
  it('says the readings in one line', () => {
    expect(spaceWeatherSentence(sw, meta)).toBe(
      'Now: Kp 1, protons above 10 MeV at 0.23 pfu, X-ray flares class B4.7, solar wind at 456 km/s; 2 alerts in the last 24 hours.',
    )
  })
  it('an empty alert list is "no alerts" only when the service says the list is current', () => {
    const quiet = { ...sw, now: { ...sw.now, alerts: [] } }
    expect(spaceWeatherSentence(quiet, meta)).toMatch(/; no alerts in the last 24 hours\.$/)
    const held = { ...sw, now: { ...sw.now, alerts: [], alerts_missing_reason: 'SWPC’s alert list was last read 3 days ago.' } }
    expect(spaceWeatherSentence(held, meta)).toMatch(/; SWPC’s alerts of the last 24 hours are not shown here\.$/)
  })
  it('says how many DONKI gave when more than three', () => {
    expect(eventCountWords(20, 133)).toBe('3 newest of 133')
    expect(eventCountWords(4, null)).toBe('3 newest of 4')
    expect(eventCountWords(3, 3)).toBeNull()
    expect(eventCountWords(2, 2)).toBeNull()
    expect(eventCountWords(0, 0)).toBeNull()
  })
  it('says why the X-ray class and the alerts are not shown, never "None" for no data', async () => {
    const why = { ...sw, now: { ...sw.now, xray_class: null, xray_missing_reason: 'The X-ray reading is 2 days old.', alerts: [], alerts_missing_reason: 'The alert list is 2 days old.' } }
    vi.spyOn(api, 'spaceWeather').mockResolvedValue({ ...spaceWeatherFixture, data: why } as never)
    renderApp(<SpaceWeatherRow />)
    fireEvent.click(screen.getByText('Space weather now'))
    expect(await screen.findByText('The X-ray reading is 2 days old.')).toBeTruthy()
    expect(screen.getByText(/The alert list is 2 days old\./)).toBeTruthy()
    expect(screen.queryByText('None')).toBeNull()
  })
  it('says when no reading is recent enough, once', () => {
    const missing = { ...sw.now.kp, value: null, missing_reason: 'Old.' }
    const none = { ...sw, now: { ...sw.now, kp: missing, proton_10mev_pfu: missing, proton_100mev_pfu: missing, solar_wind_km_s: missing, bz_nt: missing, xray_class: null } }
    expect(spaceWeatherSentence(none, { computed_at: '2026-09-26T20:14:00Z', stale: true })).toBe(
      'No reading is recent enough to show: the newest is from 26 September 2026, 20:14 UTC. Each says why below.',
    )
  })
  it('gives NOAA’s outlook as issued, or why not', () => {
    expect(outlookSentence(sw.outlook)).toBe(
      'NOAA’s outlook for Sep 26-Sep 28 2026, issued 26 September 2026, 12:30 UTC: a 1%, 1% and 1% chance of a radiation storm (S1 or greater), day by day; the largest Kp expected is 4.',
    )
    expect(outlookSentence({ ...sw.outlook, missing_reason: 'Too old.' })).toBe('Too old.')
  })
  it('dates each reading by its own source', () => {
    expect(readingAge(meta, (u) => u === sw.now.kp.source, )).toMatch(/^as of /)
    expect(readingAge(meta, () => false)).toBeNull()
  })
})

describe('Weather rules: past years', () => {
  const c = { share: 0.0101, years: '2019-2025', source: '' }
  it('reads a lightning rule as thunder at the pad, a wind rule as over the limit', () => {
    expect(climatologyWords({ class: 'observation', climatology: c })).toBe('Past years (2019-2025): thunder could be heard at the pad 1.0% of the time.')
    expect(climatologyWords({ class: 'model', climatology: { ...c, years: '2001-2024' } })).toBe('Past years (2001-2024): over the limit 1.0% of the time.')
  })
})

describe('Return: the capsule model, checked against a real landing', () => {
  const check = (returnFixture.data.capsule as { model_check: CapsuleModelCheckDTO }).model_check
  it('says the service’s words first, whether the plan’s limit is met, the air, then the numbers, the date and the sources', () => {
    render(<CapsuleCheckRow check={check} />)
    expect(screen.getByText('The capsule model, checked against a real landing')).toBeTruthy()
    expect(screen.getByText('12.1 km from it; the plan’s 10 km is not met')).toBeTruthy()
    expect(screen.getByText(check.note)).toBeTruthy()
    // The air the modelled fall went through, as served.
    expect(screen.getByText('The air the modelled fall went through')).toBeTruthy()
    expect(screen.getByText(check.atmosphere)).toBeTruthy()
    expect(screen.getByText('12.1 km (9.4 to 14.8 km over the published drag range)')).toBeTruthy()
    expect(screen.getByText('51.2 by 21.8 km; holds the real landing point')).toBeTruthy()
    expect(screen.getByText('29 September 2026, 08:17 UTC')).toBeTruthy()
    expect(screen.getByRole('link', { name: /naif\.jpl\.nasa\.gov/ }).getAttribute('href')).toBe(check.sources[0])
  })
  it('a limit not met says by how much, in words and a shape', () => {
    render(<CapsuleCheckRow check={check} />)
    expect(screen.getByText('The plan’s 10 km is not met: 2.1 km over the limit.')).toBeTruthy()
    cleanup()
    render(<CapsuleCheckRow check={{ ...check, distance_km: 12.5, measured_inside_ellipse: false }} />)
    expect(screen.getByText('The plan’s 10 km is not met: 2.5 km over the limit.')).toBeTruthy()
    expect(screen.getByText('51.2 by 21.8 km; does not hold the real landing point')).toBeTruthy()
  })
  it('a limit met says so, with what is to spare, and no shape', () => {
    const note = 'The entry model lands its capsule 9.5 km from where the recovery team found it (the limit is 10 km).'
    render(<CapsuleCheckRow check={{ ...check, distance_km: 9.5, distance_range_km: [6.7, 12.2], passed: true, note }} />)
    expect(screen.getByText('9.5 km from it; the plan’s 10 km is met')).toBeTruthy()
    expect(screen.getByText('The plan’s 10 km is met, with 0.5 km to spare.')).toBeTruthy()
    expect(screen.queryByText(/not met/)).toBeNull()
  })
  it('a saved copy recorded before the air was served leaves the line out rather than empty', () => {
    const { atmosphere: _air, ...old } = check
    render(<CapsuleCheckRow check={old as CapsuleModelCheckDTO} />)
    expect(screen.queryByText('The air the modelled fall went through')).toBeNull()
    expect(screen.getByText('12.1 km from it; the plan’s 10 km is not met')).toBeTruthy()
  })
  it('reads the limit and the air from the answer, not from the screen', () => {
    const other = { ...check, limit_km: 15, passed: true, distance_km: 12.1, atmosphere: 'The U.S. Standard Atmosphere 1976: the solar files have no values for that day.' }
    expect(capsuleLimitWords(other)).toEqual({
      met: true,
      short: 'the plan’s 15 km is met',
      long: 'The plan’s 15 km is met, with 2.9 km to spare.',
    })
    render(<CapsuleCheckRow check={other} />)
    expect(screen.getByText('12.1 km from it; the plan’s 15 km is met')).toBeTruthy()
    expect(screen.getByText(other.atmosphere)).toBeTruthy()
  })
})

describe('The hub’s note on old live data', () => {
  const base = { provider: 'swpc', provider_name: 'NOAA Space Weather Prediction Center', product: 'kp', stale: false, breaker: 'closed', errors: 0, age_s: 60 }
  const f = (over: Partial<FeedDTO>) => ({ ...base, ...over }) as FeedDTO
  it('names each provider once, old first, then one not answering whose data is still recent', () => {
    expect(
      oldFeedsWords([
        f({ stale: true }),
        f({ product: 'alerts', stale: true }),
        f({ provider: 'donki', provider_name: 'NASA space weather database (DONKI)', stale: true }),
        f({ provider: 'nomads', provider_name: 'NOAA weather models', errors: 1 }),
        f({ provider: 'nws', provider_name: 'US National Weather Service' }),
      ]),
    ).toBe(
      'Some live data is older than usual: NOAA Space Weather Prediction Center and NASA space weather database (DONKI). NOAA weather models is not answering right now; its data is still recent. Each number from them says how old it is, or why it is missing.',
    )
  })
  it('says nothing when every feed is recent', () => {
    expect(oldFeedsWords([f({}), f({ product: 'alerts' })])).toBeNull()
  })
})

describe('Contact through a relay', () => {
  const q = (o: Partial<QuantityDTO>): QuantityDTO => ({ ...contact.numbers.direct_h, value: null, pm: null, lo: null, hi: null, missing_reason: null, ...o })

  it('the relay is a range with its launch status beside it; waits that count it say so', () => {
    expect(contactAnswer(contact)).toBe(
      'A ground station can hear it for 159.0 ±0.5 h over these dates. Through Lunar Pathfinder (not launched) it could reach Earth for 60–95 h, if it flies as planned; ' +
        'that adds 1.5–4 h to direct contact. The longest time without contact is 1.0 ±0.1 h directly, or 0.4–1 h with the relay, if it flies as planned.',
    )
    const [r] = relayList(contact)
    expect(r.state?.words).toBe('Not launched')
    expect(r.launch).toMatch(/^To fly on Firefly's Blue Ghost Mission 2/)
    expect(numberWords(contact.numbers.either_h, 'if the relay flies as planned')).toBe('166–168 h, if the relay flies as planned')
    // Its orbit: published figures and assumed ranges say which they are.
    expect(orbitWords(r.orbit!.apoapsis_km)).toBe('7,332 km, published')
    expect(orbitWords(r.orbit!.inclination_deg)).toBe('46.8–54.9°, assumed')
    expect(plannedWords(r)).toBe('1.5–4 h somewhere in these dates, if it flies as planned')
    // Orbiters: their passes in words, and a trajectory that stops early says so.
    const [lro, danuri] = contact.orbiters!
    expect(orbiterWords({ ...lro, pass_count: 0, passes: [], in_view_h: { ...lro.in_view_h, value: null, pm: null, missing_reason: 'No trajectory is recorded for these dates.' } })).toBe(
      'Not known: No trajectory is recorded for these dates.',
    )
    expect(orbiterWords({ ...lro, pass_count: 0, passes: [], in_view_h: { ...lro.in_view_h, value: 0 } })).toBe('No pass over these dates.')
    const t = (x: string) => Date.parse(x)
    expect(coveredWords(lro, t(contact.start!), t(contact.end!))).toBeNull()
    expect(coveredWords(danuri, t(contact.start!), t(contact.end!))).toMatch(/to 11 March 2025 only; passes outside that are not known\.$/)
  })

  it('a planned relay with no published orbit is named, not counted; with no relay the waits are plain', () => {
    const reason = "The planned relay's orbit is not published, so time through it is not worked out."
    const unpublished = {
      ...contact,
      relays: [{ ...contact.relays[0], launch_status: 'planned' as const, adds_h: q({ missing_reason: "The relay's orbit is not published." }) }],
      nodes: contact.nodes.map((n) => (n.kind === 'relay' ? { ...n, status: 'planned' as const } : n)),
      numbers: { ...contact.numbers, via_relay_h: q({ missing_reason: reason }), either_h: q({ missing_reason: reason }), longest_unheard_h: q({ value: 0.23 }) },
    }
    expect(contactAnswer(unpublished)).toBe(
      'A ground station can hear it for 159.0 ±0.5 h over these dates. Lunar Pathfinder (planned, not launched) could relay for it, but time through it is not worked out yet. ' +
        'The longest time without contact is 0.23 h.',
    )
    expect(numberWords(unpublished.numbers.either_h)).toBe(`Not worked out: ${reason}`)
    expect(plannedWords(unpublished.relays[0])).toBe("Not worked out: The relay's orbit is not published.")
    const none = { ...contact, relays: [], numbers: { ...contact.numbers, longest_unheard_h: q({ value: 0 }) } }
    expect(contactAnswer(none)).toBe('A ground station can hear it for all 159.0 ±0.5 h of these dates.')
  })
})

describe('Rover and lander line of sight', () => {
  const rover = (roverFixture as unknown as SectionDTO<RoverSightDTO>).data
  const v = rover.viewshed!

  it('a ray reads as runs of one state, from the first sample to the last', () => {
    expect(rayRuns(['clear', 'clear', 'uncertain', 'blocked', 'blocked'], [25, 50, 75, 100, 125]).map((r) => [r.state, r.from, r.to])).toEqual([
      ['clear', 25, 50],
      ['uncertain', 75, 75],
      ['blocked', 100, 125],
    ])
    expect(rayWords(v.sight[27], v.ranges_m)).toBe('In sight 25–275 m; uncertain 300 m; blocked 325–425 m; in sight 450–500 m')
    expect(bearingWords(270)).toBe('270° (west)')
    expect(bearingWords(10)).toBe('10°')
  })

  it('the answer first: the share over the ground or the drive, the longest stretch or why not, and a site the terrain map does not cover', () => {
    expect(roverSentence(rover, 'Yaoki')).toBe(
      'Within 500 m of the lander, 18–26% of the ground is out of its sight; the radio path is not clear over 25–33%. No drive is published for Yaoki, so no stretch of it can be measured.',
    )
    const drive = {
      ...rover,
      share_basis: 'drive' as const,
      out_of_sight_share: { ...rover.out_of_sight_share, lo: null, hi: null, value: 12, no_margin_reason: 'every sample is clear or blocked' },
      longest_out_of_sight_m: { ...rover.longest_out_of_sight_m, value: 140, pm: 25, missing_reason: null },
    }
    expect(roverSentence({ ...drive, radio_not_clear_share: undefined }, 'FLIP')).toBe(
      'FLIP would be out of the lander’s sight for 12% of its drive. The longest stretch out of sight is 140 ±25 m.',
    )
    const bad = (roverUnresolvable as unknown as SectionDTO<RoverSightDTO>).data
    expect(roverSentence(bad, 'CADRE')).toMatch(/^Reiner Gamma is outside the polar terrain map/)
  })

  it('the map is laid over the terrain from the answer’s tiles, with the ground in the legend; without them it is drawn as sectors', () => {
    const { unmount } = render(<ViewshedPanel v={v} roverName="Yaoki" tile={rover.viewshed_tile} at={rover.lander} />)
    const map = screen.getByTestId('site-tile-map')
    expect(map.getAttribute('aria-label')).toMatch(/^Line of sight between Yaoki and the lander, out to 500 m in 36 directions, north up\. The table lists each direction\. Drawn over the terrain map\.$/)
    const hrefs = Array.from(map.querySelectorAll('image')).map((i) => i.getAttribute('href') ?? '')
    // The terrain under the answer's own layer, each from the answer's address at one zoom.
    expect(hrefs.some((h) => /\/tiles\/viewshed\/91\/\d+\/\d+\/\d+\.png\?layer=terrain$/.test(h))).toBe(true)
    expect(hrefs.some((h) => /\?layer=sight$/.test(h))).toBe(true)
    expect(hrefs.every((h) => !h.includes('{'))).toBe(true)
    for (const words of ['The lander', 'In sight', 'Blocked by the ground', 'Uncertain: the terrain map’s error could tip it either way', 'The ground, shaded from the terrain map']) {
      expect(screen.getByText(words)).toBeTruthy()
    }
    // The switch asks for the radio path's tiles.
    fireEvent.click(screen.getByRole('button', { name: 'Radio path' }))
    expect(Array.from(screen.getByTestId('site-tile-map').querySelectorAll('image')).some((i) => /\?layer=radio$/.test(i.getAttribute('href') ?? ''))).toBe(true)
    // What the radio path needs beyond the line of sight is said in plain words, above the map and over the table, never by its term.
    expect(screen.getByText('Where the radio path is clear too: the ground must also stay out of the space around the line of sight that the radio signal needs, so less of the ground is clear.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Read the chart as a table' }))
    expect(screen.getByRole('columnheader', { name: 'Radio path (the space around the line of sight that the radio signal needs)' })).toBeTruthy()
    expect(document.body.textContent).not.toMatch(/Fresnel/i)
    unmount()

    render(<ViewshedPanel v={v} roverName="Yaoki" tile={null} at={null} />)
    expect(screen.queryByTestId('site-tile-map')).toBeNull()
    expect(screen.getByRole('img', { name: /^Line of sight between Yaoki and the lander/ })).toBeTruthy()
    expect(screen.queryByText('The ground, shaded from the terrain map')).toBeNull()
  })

  it('a layer that does not load says so, since a map without it would read as no blockers', () => {
    render(<ViewshedPanel v={v} roverName="Yaoki" tile={rover.viewshed_tile} at={rover.lander} />)
    expect(screen.queryByRole('status')).toBeNull()
    const layer = Array.from(screen.getByTestId('site-tile-map').querySelectorAll('image')).find((i) => /\?layer=sight$/.test(i.getAttribute('href') ?? ''))!
    fireEvent.error(layer)
    expect(screen.getByRole('status').textContent).toBe('The map layer did not load, so nothing is drawn over the terrain. The table has the same answer.')
  })
})
