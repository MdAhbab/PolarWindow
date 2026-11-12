// @vitest-environment jsdom
import '../test/dialog'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { KeyNumberRow } from './KeyNumbers'
import { adaptHorizon, adaptSite } from '../lib/api/adapters'
import { api, type MetricsDTO, type WindowsDTO } from '../lib/api/client'
import type { ParameterDTO } from '../lib/api/lifecycle'
import type { SiteMetrics } from '../lib/types'
import { renderApp } from '../test/render'
import { useMission } from '../lib/store'
import { useSettingsTab } from '../lib/settingsTab'
import metricsFixture from '../lib/api/__fixtures__/connecting-ridge.metrics.json'
import windowsFixture from '../lib/api/__fixtures__/connecting-ridge.windows.json'
import parametersFixture from '../lib/api/__fixtures__/lifecycle/parameters.json'

const ENTERED = (parametersFixture as unknown as { parameters: ParameterDTO[] }).parameters
/** The same parameters with the battery limit not entered, as the service answers until someone does. */
const NOT_ENTERED = ENTERED.map((p) =>
  p.id === 'battery_limit_h'
    ? {
        ...p,
        value: { ...p.value, value: null, no_margin_reason: null, source: null, missing_reason: 'The lander’s battery limit is not published.' },
        changed_by: null,
        changed_at: null,
      }
    : p,
)

beforeEach(() => {
  vi.spyOn(api, 'parameters').mockResolvedValue({ parameters: NOT_ENTERED })
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

const render = (ui: ReactNode) => renderApp(ui)
/** The row once the parameters have answered (the night's footnote waits for them). */
async function renderRow(ui: ReactNode) {
  const r = render(ui)
  await waitFor(() => expect(api.parameters).toHaveBeenCalled())
  // A failed read is retried once (a second or so) before the limit is said to be assumed.
  await screen.findAllByText(/battery limit|did not set/, {}, { timeout: 5000 })
  return r
}

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

const tile = (label: RegExp) => screen.getByText(label).closest('div.pw-tile') as HTMLElement
/** Text as read: the non-breaking spaces that keep a figure with its unit are spaces. */
const plain = (s: string | null) => (s ?? '').replace(/ /g, ' ')

describe('KeyNumberRow', () => {
  it('shows the computing state, never zeros, before the numbers arrive', () => {
    render(<KeyNumberRow metrics={undefined} />)
    expect(screen.getAllByText('Loading')).toHaveLength(4)
    expect(screen.queryByText('0')).toBeNull()
  })

  it('shows the four numbers in order, with the night and its margin', async () => {
    await renderRow(<KeyNumberRow metrics={real()} />)
    const labels = screen.getAllByText(/^(Time in sunlight|Time in contact with Earth|Longest night|Longest time without contact)$/)
    expect(labels.map((l) => l.textContent)).toEqual([
      'Time in sunlight',
      'Time in contact with Earth',
      'Longest night',
      'Longest time without contact',
    ])
    const night = tile(/^Longest night$/)
    expect(within(night).getByText('122')).toBeTruthy()
    expect(within(night).getByText('±17.1')).toBeTruthy()
    expect(within(night).getByText(/about 122 hours, plus or minus 17.1 hours/)).toBeTruthy()
  })

  it('compares the night with the limit using its margin, and says the limit is assumed, hatched, with a way to enter one', async () => {
    await renderRow(<KeyNumberRow metrics={real()} />)
    const night = tile(/^Longest night$/)
    // 121.6 h against 120 h, ±17.1 h: within the margin, so not over, not magenta.
    expect(plain(night.textContent)).toContain('within the margin of the 120 h battery limit (assumed)')
    expect(night.className).not.toContain('pw-card-alert')
    const hatched = within(night).getByText('120 h battery limit (assumed)')
    expect(hatched.className).toContain('pw-scenario')
    fireEvent.click(within(night).getByRole('button', { name: /Enter yours/ }))
    expect(useMission.getState().settingsOpen).toBe(true)
    expect(useSettingsTab.getState().tab).toBe('parameters')
    useMission.setState({ settingsOpen: false })
  })

  it('says how far past the limit a night beyond its margin is, in the alert colour', async () => {
    const m = real()
    const long = { ...m, sun: { ...m.sun, longestDownH: 606, longestDownToleranceH: 1.2 } }
    await renderRow(<KeyNumberRow metrics={long} />)
    const night = tile(/^Longest night$/)
    expect(plain(night.textContent)).toContain('486 ±1.2 h past the 120 h battery limit (assumed)')
    expect(night.className).toContain('pw-card-alert')
  })

  it('names the limit the team entered as theirs: no "assumed", no hatch, no link', async () => {
    vi.mocked(api.parameters).mockResolvedValue({ parameters: ENTERED })
    const m = real()
    const short = { ...m, sun: { ...m.sun, longestDownH: 64, longestDownToleranceH: 2 } }
    await renderRow(<KeyNumberRow metrics={short} />)
    const night = tile(/^Longest night$/)
    expect(plain(night.textContent)).toContain('32 ±2.0 h inside the 96 h battery limit your team entered')
    expect(night.textContent).not.toMatch(/assumed/)
    expect(night.querySelector('.pw-scenario')).toBeNull()
    expect(within(night).queryByRole('button', { name: /Enter yours/ })).toBeNull()
  })

  it('says assumed when the parameters cannot be read', async () => {
    vi.mocked(api.parameters).mockRejectedValue(new Error('unreachable'))
    await renderRow(<KeyNumberRow metrics={real()} />)
    expect(plain(tile(/^Longest night$/).textContent)).toContain('battery limit (assumed)')
  })

  it('says what a number means, and its professional name, only when its label is pressed', () => {
    render(<KeyNumberRow metrics={real()} />)
    expect(screen.queryByText(/so the lander can radio home directly/)).toBeNull()
    const button = screen.getByRole('button', { name: /Time in contact with Earth/ })
    expect(button.getAttribute('aria-expanded')).toBe('false')
    fireEvent.click(button)
    expect(button.getAttribute('aria-expanded')).toBe('true')
    const sheet = screen.getByRole('dialog', { name: 'About this number' })
    expect(sheet.textContent).toMatch(/so the lander can radio home directly/)
    expect(sheet.textContent).toContain('Also called Direct-to-Earth (DTE) contact.')
  })

  it('says plainly when there is no night and no blackout: no ±, no margin arithmetic', () => {
    render(<KeyNumberRow metrics={allDay()} />)
    expect(screen.queryByText(/±/)).toBeNull()
    expect(screen.getByText('The Sun did not set on these dates')).toBeTruthy()
    expect(screen.getByText('Earth stayed in view on all of these dates')).toBeTruthy()
    expect(screen.queryByText(/margin on/)).toBeNull()
  })

  it('keeps the numbers but drops the ± on a smooth-Moon skyline (uncertain, not hidden)', () => {
    render(<KeyNumberRow metrics={real()} uncertain />)
    expect(within(tile(/^Longest night$/)).getByText('122')).toBeTruthy()
    expect(screen.queryByText(/±/)).toBeNull()
    expect(screen.getAllByText(/, uncertain$/)).toHaveLength(4)
  })

  it('marks a night the window cut short as at least its value', () => {
    const m = real()
    const cut = { ...m, sun: { ...m.sun, longestDownOpen: true } }
    render(<KeyNumberRow metrics={cut} />)
    const night = tile(/^Longest night$/)
    expect(within(night).getByText(/≥/)).toBeTruthy()
    expect(within(night).getByText(/at least 122 hours/)).toBeTruthy()
  })

  it('never calls a night the dates cut short inside the limit', async () => {
    const m = real()
    const cut = { ...m, sun: { ...m.sun, longestDownH: 80, longestDownOpen: true, longestDownToleranceH: 2 } }
    await renderRow(<KeyNumberRow metrics={cut} />)
    const night = tile(/^Longest night$/)
    expect(plain(night.textContent)).toContain('these dates cut this night short; it may run past the 120 h battery limit (assumed)')
    expect(night.textContent).not.toMatch(/inside/)
  })
})
