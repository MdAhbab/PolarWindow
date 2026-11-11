// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { HomeScreen } from '../../screens/HomeScreen'
import { renderApp } from '../../test/render'
import { adaptPublishedDate } from '../../lib/api/adapters'
import { nextEvent } from '../../lib/api/home'
import type { FeedDTO, SectionStatusDTO } from '../../lib/api/lifecycle'
import { useAsk } from '../ask/store'
import listFixture from '../../lib/api/__fixtures__/missions.list.json'
import sectionsFixture from '../../lib/api/__fixtures__/lifecycle/sections.json'
import { countdownWords, feedAgesLine, headline, journeySteps, needsYou, utcClock, utcDateWords } from './model'

const NOW = Date.parse('2026-11-11T12:00:00Z')

const status = (section: SectionStatusDTO['section'], state: SectionStatusDTO['state']): SectionStatusDTO => ({
  section,
  state,
  summary: `${section} ${state}`,
  as_of: null,
})

describe('what needs the manager', () => {
  it('lists steps waiting on input (to the form) or data (to a scenario), in project then journey order', () => {
    const items = needsYou(
      [
        { id: 'rook', name: 'Lunar Rook' },
        { id: 'kite', name: 'Kite' },
      ],
      [
        [status('ready', 'needs_input'), status('trip', 'no_data'), status('launch', 'needs_input'), status('landing', 'available')],
        undefined,
      ],
    )
    expect(items.map((n) => [n.stepName, n.action, n.href])).toEqual([
      ['Ready', 'Fill it in', '/missions/rook/ready'],
      ['Launch', 'Fill in the form', '/projects/rook/edit'],
      ['Trip', 'Explore a scenario', '/missions/rook/trip?scenario=new'],
    ])
  })

  it('gives the six steps in journey order, unknown where the service did not say', () => {
    const strip = journeySteps([status('contact', 'computing')])
    expect(strip.map((s) => s.name)).toEqual(['Ready', 'Launch', 'Trip', 'Surface', 'Contact', 'Return'])
    expect(strip.map((s) => s.state)).toEqual([null, null, null, null, 'computing', null])
  })

  it('opens with counts of real things, and nothing while they are unknown', () => {
    expect(headline(null, 2)).toBeNull()
    expect(headline(0, 0)).toBe('Nothing waits on you; nothing is being worked out.')
    expect(headline(1, null)).toBe('1 step waits on you.')
    expect(headline(3, 1)).toBe('3 steps wait on you; 1 thing is being worked out.')
  })
})

describe('dates and ages', () => {
  it('counts down in days only for a date known to the day', () => {
    const day = adaptPublishedDate({ date: '2027-01-20', precision: 'day', as_published: '20 January 2027' })!
    const quarter = adaptPublishedDate({ date: '2027-10-01', precision: 'quarter', as_published: 'Q4 2027' })!
    expect(countdownWords({ what: 'Launch', date: day, days: 70 })).toBe('Launch in 70 days')
    expect(countdownWords({ what: 'Landing', date: day, days: 0 })).toBe('Landing today')
    expect(countdownWords({ what: 'Landing', date: quarter, days: null })).toBe('Landing: Q4 2027')
  })

  it('takes the next event in the mission’s own order, even when a vaguer later one starts earlier', () => {
    const launch = adaptPublishedDate({ date: '2027-01-20', precision: 'day', as_published: '20 January 2027' })
    const landing = adaptPublishedDate({ date: '2027-01-01', precision: 'year', as_published: 'late 2027' })
    expect(nextEvent({ launch, landing }, NOW)).toMatchObject({ what: 'Launch', days: 70 })
    expect(nextEvent({ launch, landing }, Date.parse('2027-02-01T00:00:00Z'))).toMatchObject({ what: 'Landing', days: null })
    expect(nextEvent({ launch: null, landing: null }, NOW)).toBeNull()
  })

  it('writes the clock and the date in UTC', () => {
    expect(utcClock(Date.parse('2026-11-11T04:05:06Z'))).toBe('04:05:06')
    expect(utcDateWords(NOW)).toBe('Wednesday 11 November 2026')
  })

  it('gives each provider’s newest data age in one line, marking old ones', () => {
    const f = (provider_name: string, age_s: number | null, stale = false) => ({ provider: provider_name, provider_name, age_s, stale }) as FeedDTO
    expect(feedAgesLine([f('NOAA SWPC', 600), f('NOAA SWPC', 120), f('NASA DONKI', 9000, true), f('Open-Meteo', null)])).toBe(
      'NOAA SWPC 2 min, NASA DONKI 3 h (old), Open-Meteo nothing yet',
    )
    expect(feedAgesLine([])).toBeNull()
  })
})

type Reply = { status: number; body: unknown } | 'pending'

const project = {
  ...listFixture.items[2],
  id: 'rook',
  name: 'Lunar Rook',
  origin: 'project',
  owner_name: 'Demo project manager',
  launch: { date: '2027-01-20', precision: 'day', as_published: '20 January 2027' },
}
const sections = {
  ...sectionsFixture,
  data: sectionsFixture.data.map((s) =>
    s.section === 'launch' ? { ...s, state: 'needs_input' } : s.section === 'trip' ? { ...s, state: 'no_data' } : s,
  ),
}
const activity = {
  active: [
    {
      key: 'scenario:s1',
      kind: 'scenario',
      label: 'Scenario: Falcon 9 from LC-39A',
      mission_id: 'rook',
      mission_name: 'Lunar Rook',
      href: '/missions/rook/launch?scenario=s1',
      status: 'running',
      progress: 0.4,
      message: 'Launch opportunities',
      started_at: '2026-11-11T11:58:00Z',
      finished_at: null,
    },
  ],
  recent: [],
  poll_after_s: 3,
}

function stubApi(projects: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const path = new URL(String(input)).pathname
      let reply: Reply = 'pending'
      if (path.endsWith('/projects')) reply = { status: 200, body: projects }
      else if (path.endsWith('/sections')) reply = { status: 200, body: sections }
      else if (path.endsWith('/activity')) reply = { status: 200, body: activity }
      else if (path.endsWith('/missions')) reply = { status: 200, body: listFixture }
      if (reply === 'pending') return new Promise(() => {})
      const r = reply
      return Promise.resolve(new Response(JSON.stringify(r.body), { status: r.status, headers: { 'content-type': 'application/json' } }))
    }),
  )
}

describe('Home', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(NOW)
    useAsk.setState({ isOpen: false, text: null, textId: 0 })
  })
  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  it('answers what needs the manager today: the count, each step one click away, the projects and the work in progress', async () => {
    stubApi({ items: [project], total: 1 })
    renderApp(<HomeScreen />, { route: '/home' })

    expect(await screen.findByRole('heading', { level: 1, name: '2 steps wait on you; 1 thing is being worked out.' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Fill in the form: Lunar Rook, Launch' }).getAttribute('href')).toBe('/projects/rook/edit')
    expect(screen.getByRole('link', { name: 'Explore a scenario: Lunar Rook, Trip' }).getAttribute('href')).toBe(
      '/missions/rook/trip?scenario=new',
    )
    expect(screen.getByRole('link', { name: 'Lunar Rook' }).getAttribute('href')).toBe('/missions/rook')
    expect(screen.getByText('Launch in 70 days')).toBeTruthy()
    expect(screen.getByText('Launch: Needs input')).toBeTruthy()
    expect(screen.getByRole('progressbar', { name: 'Progress of Scenario: Falcon 9 from LC-39A' })).toBeTruthy()
    expect(screen.getByRole('link', { name: /^New project/ }).getAttribute('href')).toBe('/projects/new')

    fireEvent.click(screen.getByRole('button', { name: 'What does Lunar Rook still need?' }))
    expect(useAsk.getState()).toMatchObject({ isOpen: true, text: 'What does Lunar Rook still need?' })
  })

  it('empty: the two ways to start and three CLPS missions to explore', async () => {
    stubApi({ items: [], total: 0 })
    renderApp(<HomeScreen />, { route: '/home' })
    expect(await screen.findByText('No projects yet')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Drop a file' }).getAttribute('href')).toBe('/projects/new')
    expect(screen.getByRole('link', { name: 'Fill in the form' }).getAttribute('href')).toBe('/projects/new')
    const list = await screen.findByText('CLPS missions to explore')
    const explore = await waitFor(() => {
      const links = [...(list.parentElement?.querySelectorAll('a') ?? [])]
      expect(links.length).toBeGreaterThan(0)
      return links
    })
    expect(explore.length).toBeLessThanOrEqual(3)
    expect(explore.every((a) => a.getAttribute('href')?.startsWith('/missions/'))).toBe(true)
  })
})
