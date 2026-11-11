// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, screen, within } from '@testing-library/react'
import { renderApp } from '../../test/render'
import { adaptPublishedDate } from '../../lib/api/adapters'
import type { SectionStatusDTO } from '../../lib/api/lifecycle'
import { useActiveScenario } from '../scenario/store'
import { JourneyPath } from './JourneyBar'

const status = (section: SectionStatusDTO['section'], state: SectionStatusDTO['state'], summary: string): SectionStatusDTO => ({
  section,
  state,
  summary,
  as_of: null,
})

const statuses = [
  status('ready', 'needs_input', 'Two parts are not entered yet.'),
  status('launch', 'needs_input', 'No vehicle is chosen yet.'),
  status('trip', 'no_data', 'Nothing is published about the trip.'),
  status('landing', 'computing', 'Sunlight at the landing spot is being worked out.'),
  status('contact', 'available', 'The Deep Space Network can hear it most days.'),
  status('return', 'not_applicable', 'Nothing comes back to Earth.'),
]

const quarter = adaptPublishedDate({ date: '2027-10-01', precision: 'quarter', as_published: 'Q4 2027' })!

function renderPath(route: string) {
  return renderApp(
    <JourneyPath
      missionId="rook"
      statuses={statuses}
      loading={false}
      status="planned"
      target="Shackleton rim"
      next={{ what: 'Launch', date: quarter, days: null }}
    />,
    { route },
  )
}

const hrefs = (nav: HTMLElement) => within(nav).getAllByRole('link').map((a) => a.getAttribute('href'))

describe('the mission home as a journey', () => {
  afterEach(() => {
    cleanup()
    useActiveScenario.setState({ active: {} })
  })

  it('says each stop’s state in words beside its shape, with its one-line answer, from Earth to the Moon', () => {
    renderPath('/missions/rook')
    const nav = screen.getByRole('navigation', { name: 'Mission sections' })
    const stops = within(nav).getAllByRole('listitem')
    expect(stops).toHaveLength(6)
    const said = stops.map((li) => li.textContent ?? '')
    expect(said[0]).toContain('Needs input')
    expect(said[1]).toContain('Needs input')
    expect(said[2]).toContain('No data yet')
    expect(said[3]).toContain('Working it out')
    expect(said[4]).toContain('Available')
    expect(said[5]).toContain('Does not apply')
    expect(said[2]).toContain('Nothing is published about the trip.')
    // Where it is now and what comes next, in words; the landing spot at the Moon's end.
    expect(nav.textContent).toContain('getting ready')
    expect(nav.textContent).toContain('Launch: Q4 2027')
    expect(nav.textContent).toContain('The Moon, Shackleton rim')
  })

  it('offers a scenario where a step has no data or needs input, but never for Ready', () => {
    renderPath('/missions/rook')
    expect(screen.getByRole('link', { name: 'Explore a scenario for Trip' }).getAttribute('href')).toBe(
      '/missions/rook/trip?scenario=new',
    )
    expect(screen.getByRole('link', { name: 'Explore a scenario for Launch' }).getAttribute('href')).toBe(
      '/missions/rook/launch?scenario=new',
    )
    expect(screen.queryByRole('link', { name: 'Explore a scenario for Ready' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'Explore a scenario for Contact' })).toBeNull()
    // With no scenario open, every step opens on the record.
    const steps = hrefs(screen.getByRole('navigation', { name: 'Mission sections' })).filter((h) => !h?.endsWith('=new'))
    expect(steps).toEqual([
      '/missions/rook/ready',
      '/missions/rook/launch',
      '/missions/rook/trip',
      '/missions/rook/surface',
      '/missions/rook/contact',
      '/missions/rook/return',
    ])
  })

  it('keeps an open scenario on the step links, except Ready, which always shows the record', () => {
    renderPath('/missions/rook?scenario=s1')
    const nav = screen.getByRole('navigation', { name: 'Mission sections' })
    expect(nav.textContent).toContain('The steps open in the scenario you were reading.')
    const steps = hrefs(nav).filter((h) => !h?.endsWith('=new'))
    expect(steps[0]).toBe('/missions/rook/ready')
    expect(steps.slice(1)).toEqual([
      '/missions/rook/launch?scenario=s1',
      '/missions/rook/trip?scenario=s1',
      '/missions/rook/surface?scenario=s1',
      '/missions/rook/contact?scenario=s1',
      '/missions/rook/return?scenario=s1',
    ])
  })
})
