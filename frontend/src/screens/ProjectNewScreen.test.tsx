// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { renderApp } from '../test/render'
import { useSession } from '../lib/session'
import options from '../lib/api/__fixtures__/experience/project.options.json'
import saved from '../lib/api/__fixtures__/experience/project.saved.json'
import modelRead from '../lib/api/__fixtures__/experience/intake.model.json'
import rulesRead from '../lib/api/__fixtures__/experience/intake.rules.json'

const reply = vi.hoisted(() => ({ next: null as unknown }))
vi.mock('../lib/api/projects', async (orig) => {
  const real = await orig<typeof import('../lib/api/projects')>()
  return {
    ...real,
    useIntake: () => ({ mutateAsync: async () => reply.next, progress: null }),
  }
})
import mission from '../lib/api/__fixtures__/mission-im-2.detail.json'
import { ProjectEditScreen, ProjectNewScreen } from './ProjectNewScreen'

const posts: { url: string; body: Record<string, unknown> }[] = []

beforeEach(() => {
  posts.length = 0
  useSession.setState({
    session: { token: 't', roleName: 'Project manager', expiresAt: Date.now() + 1e7, offline: false, user: { id: 1, name: 'Ada', team: null } },
  })
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input))
      const json = (status: number, body: unknown) =>
        Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } }))
      if (url.pathname.endsWith('/projects/options')) return json(200, options)
      if (url.pathname.endsWith('/projects') && init?.method === 'POST') {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>
        posts.push({ url: url.pathname, body })
        if (body.name === 'Bad dates')
          return json(422, {
            detail: { title: 'The dates do not fit', detail: 'Check them.', errors: [{ field: 'landing.date', message: 'Landing is before launch.' }] },
          })
        return json(201, saved)
      }
      if (url.pathname.endsWith('/missions/mine-1'))
        return json(200, {
          ...mission,
          id: 'mine-1',
          origin: 'project',
          lifecycle: {
            vehicle_id: null, vehicle_name: null, pad_id: null, pad_name: null, t0: null, transfer: null, descent: null, spacecraft: null,
            rovers: [], returns: null, field_sources: {},
            comms: { bands: [], ground_stations: [], relays: [], eirp_dbw: 12.5, gt_dbk: null, frequency_mhz: 2250, data_rates_kbps: [2, 64], required_ebn0_db: null, required_margin_db: 3, eirp_tol_db: null },
          },
        })
      if (url.pathname.endsWith('/missions/mine-2'))
        return json(200, {
          ...mission,
          id: 'mine-2',
          origin: 'project',
          lifecycle: {
    vehicle_id: 'falcon-9',
    vehicle_name: 'Falcon 9',
    pad_id: 'ksc-39a',
    pad_name: 'LC-39A',
    t0: null,
    transfer: { type: 'low_energy', flight_days: 90, lunar_orbit_days: 12.5 },
    descent: { sun_el_min_deg: 2, sun_el_max_deg: 15, earth_required: null },
    comms: {
      bands: ['S', 'X'],
      ground_stations: ['dss-43'],
      relays: ['queqiao-2'],
      eirp_dbw: 12.5,
      gt_dbk: -3,
      frequency_mhz: 2250,
      data_rates_kbps: [2, 64],
      required_ebn0_db: 2.5,
      required_margin_db: 3,
      eirp_tol_db: 1,
    },
    spacecraft: { mass_kg: 1900, area_m2: null, cr: null },
    rovers: [{ id: 'mine-2/iris', name: 'Iris', organisation: 'CMU', source_url: 'https://example.org/iris' }],
    returns: 'sample_capsule',
    field_sources: { comms: 'https://example.org/comms' },
  },
        })
      if (url.pathname.endsWith('/projects/mine-2') && init?.method === 'PUT') {
        posts.push({ url: url.pathname, body: JSON.parse(String(init.body)) as Record<string, unknown> })
        return json(200, saved)
      }
      if (url.pathname.endsWith('/projects/mine-1') && init?.method === 'PUT') {
        posts.push({ url: url.pathname, body: JSON.parse(String(init.body)) as Record<string, unknown> })
        return json(200, saved)
      }
      return new Promise(() => {})
    }),
  )
})
afterEach(cleanup)

const shell = () =>
  renderApp(
    <Routes>
      <Route path="/projects/new" element={<ProjectNewScreen />} />
      <Route path="/missions/:id" element={<p>hub</p>} />
    </Routes>,
    { route: '/projects/new' },
  )

const dropIn = async (container: HTMLElement, file: File) => {
  const input = container.querySelector('input[type=file]') as HTMLInputElement
  await act(async () => {
    fireEvent.change(input, { target: { files: [file] } })
  })
}

describe('adding a project', () => {
  it('needs only a name, says what an unknown field does, and saves to the new hub', async () => {
    shell()
    expect(screen.getByText(/a step that is missing its data will offer a scenario/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Save project' }))
    const name = await screen.findByLabelText(/Mission name/)
    expect(name.getAttribute('aria-invalid')).toBe('true')
    expect(name.getAttribute('aria-describedby')).toBeTruthy()
    fireEvent.change(name, { target: { value: 'Aurora 1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save project' }))
    expect(await screen.findByText('hub')).toBeTruthy()
    expect(posts[0].body).toMatchObject({ name: 'Aurora 1', launch: null, target: null, payloads: [] })
  })

  it('shows a server refusal on the field it names', async () => {
    shell()
    fireEvent.change(await screen.findByLabelText(/Mission name/), { target: { value: 'Bad dates' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save project' }))
    expect(await screen.findByText('Landing is before launch.')).toBeTruthy()
  })

  it('fills the form from a model reading and shows the evidence on focus', async () => {
    reply.next = modelRead
    const { container } = shell()
    await screen.findByLabelText(/Mission name/)
    await dropIn(container, new File(['x'], 'brief.pdf', { type: 'application/pdf' }))
    await waitFor(() => expect((screen.getByLabelText(/Mission name/) as HTMLInputElement).value).toBe('Aurora 1'))
    expect(screen.getByText('brief.pdf: 7 of 9 fields filled')).toBeTruthy()
    expect(screen.getByText(/Page 5 is a scanned image/)).toBeTruthy()
    const marks = screen.getAllByRole('button', { name: 'From the file' })
    expect(screen.getAllByRole('button', { name: 'Worked out' }).length).toBe(1)
    await act(async () => marks[0].focus())
    expect(marks[0].getAttribute('aria-expanded')).toBe('true')
    const panel = document.getElementById(marks[0].getAttribute('aria-controls')!)!
    expect(within(panel).getByText('Mission Aurora 1 will deliver')).toBeTruthy()
    expect((screen.getAllByLabelText('Launch').find((e) => e.tagName === 'INPUT') as HTMLInputElement).value).toBe('')
  })

  it('says plainly that rules read the file when no model is set up, and keeps what is already filled', async () => {
    reply.next = rulesRead
    const { container } = shell()
    fireEvent.change(await screen.findByLabelText(/Mission name/), { target: { value: 'Mine' } })
    await dropIn(container, new File(['x'], 'dates.txt', { type: 'text/plain' }))
    expect(await screen.findByText(/No AI model is set up, so this file was read by rules/)).toBeTruthy()
    expect((screen.getByLabelText(/Mission name/) as HTMLInputElement).value).toBe('Mine')
    expect(screen.getByText(/gives a different value for mission name/)).toBeTruthy()
  })

  it('refuses a file of the wrong kind before sending it', async () => {
    const { container } = shell()
    await screen.findByLabelText(/Mission name/)
    await waitFor(() => expect(container.querySelector('input[type=file]')!.getAttribute('accept')).toContain('.pdf'))
    await dropIn(container, new File(['x'], 'pic.png', { type: 'image/png' }))
    expect(await screen.findByText(/pic.png is not a kind of file/)).toBeTruthy()
  })
})

describe('the radio figures in the form', () => {
  it('is closed by default, takes optional figures, and sends only what was typed', async () => {
    const { container } = shell()
    const eirp = (await screen.findByLabelText('Radio power (EIRP, dBW)')) as HTMLInputElement
    expect(eirp.closest('details')!.hasAttribute('open')).toBe(false)
    expect(screen.getByText(/Contact can work out the radio link once it has three of these/)).toBeTruthy()
    expect(screen.getAllByLabelText(/Ground dish sensitivity \(G\/T, dB\/K\)|Radio frequency, lander to Earth \(downlink, MHz\)|Signal needed per bit \(Eb\/N0, dB\)|Spare signal kept in hand \(link margin, dB\)|Margin on radio power \(EIRP ±, dB\)|Data rates \(kbps/).length).toBe(6)
    expect(eirp.value).toBe('')
    fireEvent.change(screen.getByLabelText(/Mission name/), { target: { value: 'Aurora 1' } })
    fireEvent.change(eirp, { target: { value: '12.5' } })
    fireEvent.change(screen.getByLabelText(/Data rates/), { target: { value: '2, 64,256' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save project' }))
    expect(await screen.findByText('hub')).toBeTruthy()
    expect(posts[0].body.lifecycle).toMatchObject({ eirp_dbw: 12.5, data_rates_kbps: [2, 64, 256] })
    for (const k of ['eirp_tol_db', 'gt_dbk', 'frequency_mhz', 'required_ebn0_db', 'required_margin_db']) expect(k in (posts[0].body.lifecycle as object)).toBe(false)
    expect(container).toBeTruthy()
  })

  it('names a bad rate in a sentence and does not send it', async () => {
    shell()
    fireEvent.change(await screen.findByLabelText(/Mission name/), { target: { value: 'Aurora 1' } })
    fireEvent.change(screen.getByLabelText(/Data rates/), { target: { value: '2, fast' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save project' }))
    expect(await screen.findByText(/Give the data rates as numbers above 0/)).toBeTruthy()
    expect(posts.length).toBe(0)
  })

  it('loads a saved project’s figures when editing, and saves them back', async () => {
    renderApp(
      <Routes>
        <Route path="/projects/:id/edit" element={<ProjectEditScreen />} />
        <Route path="/missions/:id" element={<p>hub</p>} />
      </Routes>,
      { route: '/projects/mine-1/edit' },
    )
    const eirp = (await screen.findByLabelText('Radio power (EIRP, dBW)')) as HTMLInputElement
    expect(eirp.value).toBe('12.5')
    expect((screen.getByLabelText('Radio frequency, lander to Earth (downlink, MHz)') as HTMLInputElement).value).toBe('2250')
    expect((screen.getByLabelText(/Data rates/) as HTMLInputElement).value).toBe('2, 64')
    expect((screen.getByLabelText('Spare signal kept in hand (link margin, dB)') as HTMLInputElement).value).toBe('3')
    expect((screen.getByLabelText('Ground dish sensitivity (G/T, dB/K)') as HTMLInputElement).value).toBe('')
    expect(eirp.closest('details')!.hasAttribute('open')).toBe(true)
    fireEvent.change(eirp, { target: { value: '14' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByText('hub')).toBeTruthy()
    expect(posts[0].body.lifecycle).toMatchObject({ eirp_dbw: 14, frequency_mhz: 2250, data_rates_kbps: [2, 64], required_margin_db: 3 })
  })

  it('keeps the vehicle, pad, transfer, bands, relays, mass and the rest when a saved project is saved untouched', async () => {
    renderApp(
      <Routes>
        <Route path="/projects/:id/edit" element={<ProjectEditScreen />} />
        <Route path="/missions/:id" element={<p>hub</p>} />
      </Routes>,
      { route: '/projects/mine-2/edit' },
    )
    expect(((await screen.findByLabelText('Radio power (EIRP, dBW)')) as HTMLInputElement).value).toBe('12.5')
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByText('hub')).toBeTruthy()
    expect(posts[0].body.lifecycle).toEqual({
      vehicle_id: 'falcon-9', vehicle_name: 'Falcon 9', pad_id: 'ksc-39a', pad_name: 'LC-39A',
      transfer_type: 'low_energy', flight_days: 90, lunar_orbit_days: 12.5,
      sun_el_min_deg: 2, sun_el_max_deg: 15, bands: ['S', 'X'], ground_stations: ['dss-43'], relays: ['queqiao-2'],
      mass_kg: 1900,
      rovers: [{ id: 'mine-2/iris', name: 'Iris', organisation: 'CMU', source_url: 'https://example.org/iris' }],
      returns: 'sample_capsule',
      field_sources: { comms: 'https://example.org/comms' },
      eirp_dbw: 12.5, eirp_tol_db: 1, gt_dbk: -3, frequency_mhz: 2250,
      data_rates_kbps: [2, 64], required_ebn0_db: 2.5, required_margin_db: 3,
    })
  })
})
