// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, screen } from '@testing-library/react'
import { DispersionPanel, DispersionResult, dispersionBody } from './DispersionPanel'
import { binLabel, scaleBarMetres, slopeBin } from './DispersionMap'
import { renderApp } from '../../test/render'
import fixture from '../../lib/api/__fixtures__/surface/peak-near-shackleton.dispersion.json'
import type { DispersionResponseDTO } from '../../lib/api/surface.types'

const data = fixture as unknown as DispersionResponseDTO

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('DispersionPanel', () => {
  it('starts empty, with no figure filled in for the person, and asks for nothing until all six are typed', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    renderApp(<DispersionPanel siteId="peak-near-shackleton" siteName="Peak near Shackleton" />)
    const inputs = screen.getAllByRole('textbox') as HTMLInputElement[]
    expect(inputs).toHaveLength(6)
    expect(inputs.every((i) => i.value === '')).toBe(true)
    expect((screen.getByRole('button', { name: /Work it out/ }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(screen.getByLabelText(/Slope limit/), { target: { value: '10' } })
    expect(screen.getByText('5 of 6 figures still to type.')).toBeTruthy()
    expect(screen.getByText('entered')).toBeTruthy()
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('builds the request only from six numbers', () => {
    const all = { semi_major_m: '300', semi_minor_m: '100', azimuth_deg: '30', footprint_diameter_m: '4.6', cg_height_m: '1.5', slope_limit_deg: '10' }
    expect(dispersionBody(all).body).toEqual({
      ellipse: { semi_major_m: 300, semi_minor_m: 100, azimuth_deg: 30 },
      lander: { footprint_diameter_m: 4.6, cg_height_m: 1.5, slope_limit_deg: 10 },
    })
    expect(dispersionBody({ ...all, cg_height_m: '' }).missing).toEqual(['cg_height_m'])
    expect(dispersionBody({ ...all, azimuth_deg: 'north' }).bad).toEqual(['azimuth_deg'])
  })
})

describe('DispersionResult', () => {
  it('shows the map, the slope spread with its baseline, the shares in words and the long-term light as its basis says', () => {
    renderApp(<DispersionResult data={data} />)
    expect(screen.getByRole('img', { name: /Slope map, north up/ })).toBeTruthy()
    expect(screen.getByText('Baseline: over 15 m.')).toBeTruthy()
    expect(screen.getAllByText('± 1.4')).toHaveLength(3)
    expect(screen.getByText('354 of 1000 points (32 to 38 %)')).toBeTruthy()
    expect(screen.getByText('397 of 1000 points (37 to 43 %)')).toBeTruthy()
    expect(screen.getByText(/long-term average over the LOLA data/)).toBeTruthy()
    expect(screen.getByText(/PGDA 5 m LOLA, Site04/)).toBeTruthy()
    expect(screen.getByText('unknown')).toBeTruthy()
    expect(screen.getByText('What this does not model')).toBeTruthy()
  })
})

describe('map helpers', () => {
  it('bins slopes on the legend edges, the last bin open-ended', () => {
    expect(slopeBin(0)).toBe(0)
    expect(slopeBin(9.99)).toBe(1)
    expect(slopeBin(10)).toBe(2)
    expect(slopeBin(45)).toBe(5)
    expect(binLabel(5)).toBe('30° and over')
  })
  it('picks a round scale bar about a quarter of the map', () => {
    expect(scaleBarMetres(347)).toBe(50)
    expect(scaleBarMetres(2000)).toBe(500)
  })
})
