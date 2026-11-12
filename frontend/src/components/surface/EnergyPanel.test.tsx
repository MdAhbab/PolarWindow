// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, screen, within } from '@testing-library/react'
import { EnergyPanel, EnergyResult, landerFromEntered } from './EnergyPanel'
import { renderApp } from '../../test/render'
import fixture from '../../lib/api/__fixtures__/surface/shackleton-rim.energy.json'
import type { EnergyResponseDTO } from '../../lib/api/surface.types'

const data = fixture as unknown as EnergyResponseDTO

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('EnergyPanel', () => {
  it('starts from an assumed example and asks the service for nothing until Work it out', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    renderApp(<EnergyPanel siteId="shackleton-rim" siteName="Shackleton rim" startIso="2027-01-01T00:00:00Z" endIso="2027-01-31T00:00:00Z" />)
    expect(screen.getByText('Example lander: every figure is assumed.')).toBeTruthy()
    expect(screen.getByRole('button', { name: /Work it out/ })).toBeTruthy()
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('marks a typed figure as entered and says how many are the person’s own', () => {
    renderApp(<EnergyPanel siteId="shackleton-rim" siteName="Shackleton rim" startIso="2027-01-01T00:00:00Z" endIso="2027-01-31T00:00:00Z" />)
    const battery = screen.getByLabelText(/Battery capacity/) as HTMLInputElement
    const layout = screen.getByLabelText(/Panel layout/) as HTMLSelectElement
    expect(battery.className).toContain('pw-scenario')
    expect(layout.className).toContain('pw-scenario')
    fireEvent.change(battery, { target: { value: '1500' } })
    expect(battery.className).not.toContain('pw-scenario')
    expect(screen.getByText(/Example lander with 1 of your figure./)).toBeTruthy()
    const field = battery.closest('div') as HTMLElement
    expect(within(field).getByText('entered')).toBeTruthy()
  })

  it('sends typed figures as bare numbers (entered) and refuses what is not a number', () => {
    expect(landerFromEntered({ battery_capacity_wh: '1500', array_geometry: 'sun_tracking', avionics_w: ' ' })).toEqual({
      lander: { battery_capacity_wh: 1500, array_geometry: 'sun_tracking' },
      errors: {},
    })
    expect(landerFromEntered({ payload_w: 'fifty' }).errors).toEqual({ payload_w: 'Type a number' })
  })
})

describe('EnergyResult', () => {
  it('shows each key quantity with its margin and provenance, the charts, the ground basis and what is not modelled', () => {
    renderApp(<EnergyResult data={data} />)
    expect(screen.getByText('Coldest inside the lander (bus)')).toBeTruthy()
    expect(screen.getByText('range −107 to −101')).toBeTruthy()
    expect(screen.getAllByText('computed').length).toBeGreaterThanOrEqual(6)
    expect(screen.getByRole('img', { name: /battery empties about 576 hours in/i })).toBeTruthy()
    expect(screen.getByText(/operational minimum −20 °C/)).toBeTruthy()
    expect(screen.getByText(/Diviner, 22 triangles within 1,000 m/)).toBeTruthy()
    expect(screen.getByText(/not a weather forecast/)).toBeTruthy()
    expect(screen.getByText(/midpoint of those two bounds, not a best estimate/)).toBeTruthy()
    expect(screen.getByText('What this does not model')).toBeTruthy()
    expect(screen.getAllByText('assumed').length).toBeGreaterThan(20)
  })

  it('reads one moment out when the charts are focused and an arrow key is pressed', () => {
    renderApp(<EnergyResult data={data} />)
    const group = screen.getByRole('group', { name: /arrow keys/ })
    fireEvent.keyDown(group, { key: 'Home' })
    expect(screen.getByText(/1 Jan 00:00 UTC/)).toBeTruthy()
    expect(screen.getByText(/power 588 W/)).toBeTruthy()
  })
})
