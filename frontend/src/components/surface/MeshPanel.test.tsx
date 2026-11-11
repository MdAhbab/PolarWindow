// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, screen, within } from '@testing-library/react'

const live = vi.hoisted(() => ({ on: true }))
vi.mock('../../lib/api/home', async (orig) => {
  const real = await orig<typeof import('../../lib/api/home')>()
  return {
    ...real,
    get LIVE_SERVICE() {
      return live.on
    },
  }
})

import { MeshPanel, MeshResult, initialMeshRows, meshRequestFrom } from './MeshPanel'
import { pairStates } from './MeshMap'
import { renderApp } from '../../test/render'
import request from '../../lib/api/__fixtures__/surface/connecting-ridge.mesh.request.json'
import fixture from '../../lib/api/__fixtures__/surface/connecting-ridge.mesh.json'
import type { MeshRequestDTO, MeshResponseDTO } from '../../lib/api/surface.types'

const data = fixture as unknown as MeshResponseDTO
const req = request as unknown as MeshRequestDTO

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  live.on = true
})

describe('meshRequestFrom', () => {
  it('builds, from the preset alone, the request the service was saved answering', () => {
    const { body, errors } = meshRequestFrom(initialMeshRows(), {}, req.start, req.end)
    expect(errors).toEqual({})
    expect(body).toEqual(req)
  })

  it('omits the Earth uplink when both its boxes are emptied, and sends typed units in the service units', () => {
    const { body } = meshRequestFrom(
      initialMeshRows(),
      { 'n1.uplink_kbps': '', 'n1.uplink_w': '', 'n2.uplink_kbps': '250', 's.frequency_hz': '437', 's.buffer_bytes': '10', 's.loss_min': '30' },
      req.start,
      req.end,
    )
    expect('earth_uplink_bps' in body.nodes[1]).toBe(false)
    expect('earth_uplink_power_w' in body.nodes[1]).toBe(false)
    expect(body.nodes[0].earth_uplink_bps).toBe(100000)
    expect(body.nodes[2].earth_uplink_bps).toBe(250000)
    expect(body.radio.frequency_hz).toBe(437e6)
    expect(body.guard.buffer_bytes).toBe(10e6)
    expect(body.loss_threshold_s).toBe(1800)
  })

  it('says in a sentence when only half of an uplink is given or a figure is not a number', () => {
    const { errors } = meshRequestFrom(initialMeshRows(), { 'n0.uplink_w': '', 'n1.east_m': 'far' }, req.start, req.end)
    expect(errors['n0.uplink_kbps']).toBeUndefined()
    expect(errors['n0.uplink_w']).toBe('Give both the rate and the power, or leave both empty.')
    expect(errors['n1.east_m']).toBe('Type a number.')
  })
})

describe('MeshPanel', () => {
  it('starts from an assumed preset and asks the service for nothing until Work it out', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    renderApp(<MeshPanel siteId="connecting-ridge" siteName="Connecting Ridge" startIso={req.start} endIso={req.end} />)
    expect(screen.getByText(/every figure is assumed/)).toBeTruthy()
    expect(screen.getByText('Radio and helper rules')).toBeTruthy()
    expect(screen.getAllByText('assumed').length).toBeGreaterThan(30)
    const battery = screen.getAllByLabelText(/^Battery/)[0] as HTMLInputElement
    expect(battery.className).toContain('pw-scenario')
    fireEvent.change(battery, { target: { value: '1500' } })
    expect(battery.className).not.toContain('pw-scenario')
    expect(within(battery.closest('div') as HTMLElement).getByText('entered')).toBeTruthy()
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('adds rows up to six and keeps at least one', () => {
    renderApp(<MeshPanel siteId="connecting-ridge" siteName="Connecting Ridge" startIso={req.start} endIso={req.end} />)
    const add = screen.getByRole('button', { name: 'Add a rover' }) as HTMLButtonElement
    fireEvent.click(add)
    fireEvent.click(add)
    fireEvent.click(add)
    expect(add.disabled).toBe(true)
    expect(screen.getAllByLabelText('Name')).toHaveLength(6)
    for (let i = 0; i < 5; i++) fireEvent.click(screen.getAllByRole('button', { name: /^Remove / })[0])
    expect(screen.getAllByLabelText('Name')).toHaveLength(1)
    expect((screen.getByRole('button', { name: /^Remove / }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('with the service off shows the saved-copy note and fetches nothing', () => {
    live.on = false
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    renderApp(<MeshPanel siteId="connecting-ridge" siteName="Connecting Ridge" startIso={req.start} endIso={req.end} />)
    expect(screen.getByText(/saved copy of the page/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Work it out/ })).toBeNull()
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})

describe('MeshResult', () => {
  it('shows the three longest stretches for the lander: 195, 195 and, if uncertain links hold, 168', () => {
    renderApp(<MeshResult data={data} request={req} />)
    const lander = document.querySelector('[data-node-stretch="lander"]') as HTMLElement
    const w = within(lander)
    expect(w.getAllByText('at least 195')).toHaveLength(2)
    expect(w.getByText('at least 168')).toBeTruthy()
    expect(w.getByText('If uncertain links also hold')).toBeTruthy()
    expect(w.getByText('A condition, not a result.')).toBeTruthy()
    expect(screen.getByText(/shortened no node.s longest stretch/)).toBeTruthy()
    expect(screen.getByText(/height error \(2 m\)/)).toBeTruthy()
  })

  it('draws uncertain links dashed and leaves blocked ones out', () => {
    renderApp(<MeshResult data={data} request={req} />)
    const lines = Array.from(document.querySelectorAll('svg line[data-link]'))
    expect(lines.map((l) => l.getAttribute('data-link')).sort()).toEqual(['lander-r1', 'lander-r2'])
    for (const l of lines) {
      expect(l.getAttribute('data-sight')).toBe('uncertain')
      expect(l.getAttribute('stroke-dasharray')).toBeTruthy()
    }
    expect(document.querySelector('[data-link="r1-r2"]')).toBeNull()
    expect(screen.getByRole('img', { name: /0 links drawn solid \(clear\), 2 dashed \(uncertain\), 1 not drawn \(blocked\)/ })).toBeTruthy()
    expect(document.querySelectorAll('[data-node][data-earth="true"]')).toHaveLength(3)
  })

  it('lists the links, the helpers with provenance on each figure, and what is not modelled', () => {
    renderApp(<MeshResult data={data} request={req} />)
    expect(screen.getByText('Rover 1 to Rover 2')).toBeTruthy()
    expect(screen.getAllByText('computed').length).toBeGreaterThanOrEqual(15)
    expect(screen.getAllByText('Lowest state of charge')).toHaveLength(3)
    expect(screen.getAllByText(/Active relay/)).toHaveLength(3)
    expect(screen.getByText('Terrain basis')).toBeTruthy()
    expect(screen.getByText('LOLA_LDEM_875S_5M + LOLA_LDEM_80S_80M')).toBeTruthy()
    expect(screen.getByText('LOLA_LDEM_80S_20M + LDEM_80S_80M')).toBeTruthy()
    expect(screen.getByText('What this does not model')).toBeTruthy()
  })

  it('never says the mesh improves, fixes, solves or boosts anything', () => {
    const { container } = renderApp(<MeshResult data={data} request={req} />)
    const copy = container.cloneNode(true) as HTMLElement
    // The service's own list of what is not modelled is quoted as it came ("resolve" is in it); it is not this page's claim.
    copy.querySelectorAll('li').forEach((li) => li.remove())
    expect(copy.textContent ?? '').not.toMatch(/improv|fix|solv|boost/i)
  })
})

describe('pairStates', () => {
  it('keeps one entry per pair, in the state held longest, and marks a pair whose state changed', () => {
    const [l] = (fixture as unknown as MeshResponseDTO).links
    const segs = [
      { ...l, start_s: 0, end_s: 3600, terrain_sight: 'clear' as const },
      { ...l, start_s: 3600, end_s: 36000, terrain_sight: 'uncertain' as const },
    ]
    const out = pairStates(segs)
    expect(out).toHaveLength(1)
    expect(out[0].terrain_sight).toBe('uncertain')
    expect(out[0].changed).toBe(true)
    expect(pairStates([l])[0].changed).toBe(false)
  })
})
