// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import { KeyNumberRow } from './KeyNumbers'
import { adaptHorizon, adaptSite } from '../lib/api/adapters'
import type { MetricsDTO, WindowsDTO } from '../lib/api/client'
import type { SiteMetrics } from '../lib/types'
import metricsFixture from '../lib/api/__fixtures__/connecting-ridge.metrics.json'
import windowsFixture from '../lib/api/__fixtures__/connecting-ridge.windows.json'

afterEach(cleanup)

const mask = adaptHorizon({
  site_id: 'connecting-ridge',
  azimuth_step_deg: 90,
  azimuth_count: 4,
  el_deg: [0, 0, 0, 0],
  range_m: [0, 0, 0, 0],
  tol_deg: [0, 0, 0, 0],
  max_el_deg: 0,
  max_el_bearing_deg: 0,
  meta: (metricsFixture as unknown as MetricsDTO).meta,
} as never)

const real = (): SiteMetrics =>
  adaptSite('connecting-ridge', windowsFixture as unknown as WindowsDTO, metricsFixture as unknown as MetricsDTO, mask).metrics

/** The same site over a window with no night and no blackout at all. */
function allDay(): SiteMetrics {
  const m = real()
  const noGap = (b: SiteMetrics['sun']) => ({
    ...b,
    arcs: [{ ...b.arcs[0], up: true, startH: 0, endH: 12.75, hours: 12.75, openStart: true, openEnd: true }],
    upHours: 12.75,
    fractionUp: 1,
    longestDownH: 0,
    longestDownToleranceH: 0,
    longestDownArc: undefined,
    longestDownOpen: false,
  })
  return { ...m, windowHours: 12.75, sun: noGap(m.sun), earth: noGap(m.earth) }
}

const tile = (label: RegExp) => screen.getByText(label).closest('div.border') as HTMLElement

describe('KeyNumberRow', () => {
  it('shows the computing state, never zeros, before the numbers arrive', () => {
    render(<KeyNumberRow metrics={undefined} face="public" />)
    expect(screen.getAllByText('——')).toHaveLength(4)
    expect(screen.queryByText('0')).toBeNull()
  })

  it('shows the four numbers in order, with the night over the limit and its margin', () => {
    render(<KeyNumberRow metrics={real()} face="public" />)
    const labels = screen.getAllByText(/^(Time in the Sun|Time it can call home|Longest night|Longest time it can't call home)$/)
    expect(labels.map((l) => l.textContent)).toEqual([
      'Time in the Sun',
      'Time it can call home',
      'Longest night',
      "Longest time it can't call home",
    ])
    const night = tile(/^Longest night$/)
    expect(within(night).getByText('122')).toBeTruthy()
    expect(within(night).getByText('±17.1')).toBeTruthy()
    expect(within(night).getByText(/2 h over the 120 h limit/)).toBeTruthy()
    expect(within(night).getByText(/about 122 hours, plus or minus 17.1 hours/)).toBeTruthy()
  })

  it('adds the expert term only in Expert', () => {
    const { rerender } = render(<KeyNumberRow metrics={real()} face="public" />)
    expect(screen.queryByText('Earth contact (DTE)')).toBeNull()
    rerender(<KeyNumberRow metrics={real()} face="planner" />)
    expect(screen.getByText('Earth contact (DTE)')).toBeTruthy()
  })

  it('says plainly when there is no night and no blackout: no ±, no margin arithmetic', () => {
    render(<KeyNumberRow metrics={allDay()} face="public" />)
    expect(screen.queryByText(/±/)).toBeNull()
    expect(screen.getByText('The Sun did not set in this window')).toBeTruthy()
    expect(screen.getByText('Earth stayed in view for the whole window')).toBeTruthy()
    expect(screen.queryByText(/margin on/)).toBeNull()
  })

  it('keeps the numbers but drops the ± on a smooth-Moon skyline (uncertain, not hidden)', () => {
    render(<KeyNumberRow metrics={real()} face="public" uncertain />)
    expect(within(tile(/^Longest night$/)).getByText('122')).toBeTruthy()
    expect(screen.queryByText(/±/)).toBeNull()
    expect(screen.getAllByText(/, uncertain$/)).toHaveLength(4)
  })

  it('marks a night the window cut short as at least its value', () => {
    const m = real()
    const cut = { ...m, sun: { ...m.sun, longestDownOpen: true } }
    render(<KeyNumberRow metrics={cut} face="public" />)
    const night = tile(/^Longest night$/)
    expect(within(night).getByText(/≥/)).toBeTruthy()
    expect(within(night).getByText(/at least 122 hours/)).toBeTruthy()
  })
})
