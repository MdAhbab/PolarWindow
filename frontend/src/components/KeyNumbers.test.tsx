// @vitest-environment jsdom
import '../test/dialog'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { KeyNumberRow, KeyNumberTile, fitFigure } from './KeyNumbers'
import { surfaceSentence } from '../lib/siteSentence'
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

/** What `fitFigure` says about a figure, read back from the size it writes: the share of the row it needs, in em and px. */
function fitNumbers(figure: string, margin: string | undefined, unit: string) {
  const s = String(fitFigure(figure, margin, unit).fontSize)
  const m = /calc\(\(100cqw - \(([\d.]+) \* var\(--pw-mpx\) \+ ([\d.]+) \* var\(--pw-upx\) \+ (\d+)px\)\) \/ ([\d.]+)\)/.exec(s)
  if (!m) throw new Error(`not the expected size: ${s}`)
  const [marginEm, unitEm, gapPx, figureEm] = m.slice(1).map(Number)
  return { s, marginEm, unitEm, gapPx, figureEm }
}

describe('a tile keeps its figure, its margin and its unit together', () => {
  it('draws them in one row that does not wrap, so the margin never drops to a line of its own', async () => {
    await renderRow(<KeyNumberRow metrics={real()} />)
    const night = tile(/^Longest night$/)
    const figure = within(night).getByText('122')
    const row = figure.parentElement as HTMLElement
    expect(row.className).not.toMatch(/flex-wrap/)
    expect(within(row).getByText('±17.1')).toBeTruthy()
    expect(within(row).getByText('h')).toBeTruthy()
    // The row is a container, so the figure can be sized against the tile's own width.
    expect((row.parentElement as HTMLElement).className).toContain('@container')
  })

  it('sizes a figure against the width of its row, between a floor and its full size', () => {
    const { s } = fitNumbers('122', '±17.1', 'h')
    expect(s).toMatch(/^clamp\(var\(--pw-fmin\), calc\(.*100cqw.*\), var\(--pw-fmax\)\)$/)
  })

  /** The figure's size at a row width, as the browser works it out (`clamp(min, (w - fixed) / em, max)`). */
  const sizeAt = (width: number, figure: string, margin: string | undefined, unit: string, max = 34, min = 22, margin_px = 17, unit_px = 17) => {
    const f = fitNumbers(figure, margin, unit)
    return Math.min(max, Math.max(min, (width - (f.marginEm * margin_px + f.unitEm * unit_px + f.gapPx)) / f.figureEm))
  }

  it('shrinks the figure as the tile narrows, and never below its floor', () => {
    // The phone's 2 × 2 grid: a tile is 164 px at 375 and 171 px at 390, less 32 px of padding.
    const at390 = sizeAt(139, '122', '±17.1', 'h')
    const at375 = sizeAt(132, '122', '±17.1', 'h')
    const at320 = sizeAt(104, '122', '±17.1', 'h')
    expect(at390).toBeGreaterThan(at375)
    expect(at375).toBeGreaterThan(at320)
    expect(at375).toBeLessThan(34)
    expect(at320).toBe(22)
  })

  it('leaves a short figure at full size where it already fits', () => {
    expect(sizeAt(132, '574', undefined, 'h')).toBe(34)
    expect(sizeAt(132, '13', undefined, 'h')).toBe(34)
    // The same figure with a margin is wider, so it is drawn smaller, not wrapped.
    expect(sizeAt(132, '122', '±17.1', 'h')).toBeLessThan(34)
  })

  it('makes room for a longer figure, a lower bound and a longer margin', () => {
    const plain = fitNumbers('288', '±7.2', 'h')
    const bound = fitNumbers('≥288', '±7.2', 'h')
    expect(bound.figureEm).toBeGreaterThan(plain.figureEm)
    expect(fitNumbers('288', '±17.1', 'h').marginEm).toBeGreaterThan(plain.marginEm)
    // A point or a colon is narrower than a digit.
    expect(fitNumbers('1.2', undefined, 's').figureEm).toBeLessThan(fitNumbers('122', undefined, 's').figureEm)
    expect(fitNumbers('00:16', '±4 min', '').figureEm).toBeLessThan(fitNumbers('00016', '±4 min', '').figureEm)
  })

  it('counts no gap where there is no margin or unit to sit beside the figure', () => {
    expect(fitNumbers('12', undefined, '').gapPx).toBe(2)
    expect(fitNumbers('12', undefined, 'h').gapPx).toBe(10)
    expect(fitNumbers('12', '±2', 'h').gapPx).toBe(18)
  })

  it('draws the margin and the unit of a written figure on the same row too', () => {
    render(<KeyNumberTile label="Launch time" value={0} display="00:16" margin="±4 min" unit="" bar={false} />)
    const figure = screen.getByText('00:16')
    expect(within(figure.parentElement as HTMLElement).getByText('±4 min')).toBeTruthy()
  })
})

describe('the headline and the tiles write a figure the same way', () => {
  it('says a 12.75 hour window as 13 hours, as the tiles do (IM-2 Surface)', () => {
    const m = allDay()
    expect(surfaceSentence(m)).toBe('Over these 13 hours the Sun stays up and Earth stays in view the whole time.')
    render(<KeyNumberRow metrics={m} />)
    expect(within(tile(/^Time in sunlight$/)).getByText('13')).toBeTruthy()
    expect(within(tile(/^Time in contact with Earth$/)).getByText('13')).toBeTruthy()
    expect(document.body.textContent).not.toMatch(/12\.75/)
  })

  it('says the night as the tile does: whole hours, with a lower bound where the dates cut it short', () => {
    const m = real()
    expect(surfaceSentence(m)).toContain('the longest night is 122 hours.')
    expect(surfaceSentence({ ...m, sun: { ...m.sun, longestDownOpen: true } })).toContain('the longest night is at least 122 hours.')
  })
})
