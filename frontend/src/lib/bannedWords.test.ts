// @vitest-environment jsdom
/**
 * D-16 and the glossary's "Words that never appear": the Compare page and the
 * printable report, rendered from the API's answers, say what was worked out
 * and in which order, never a verdict. Everything a reader can meet is
 * checked: the visible words, the screen-reader words, the spoken transcript
 * and the tooltips.
 *
 * The battery limit is not entered here (the service answers it empty, as it
 * does until a team enters one), so the assumed-limit words are on screen.
 */
import { createElement } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, screen } from '@testing-library/react'
import { renderApp } from '../test/render'
import { api, type CompareItemDTO, type MetricsDTO, type WindowsDTO } from './api/client'
import type { ParameterDTO } from './api/lifecycle'
import { setSites } from './sites'
import { useMission } from './store'
import type { Site } from './types'
import { CompareScreen } from '../screens/CompareScreen'
import { ReportScreen } from '../screens/ReportScreen'
import metricsFixture from './api/__fixtures__/connecting-ridge.metrics.json'
import windowsFixture from './api/__fixtures__/connecting-ridge.windows.json'
import missionsFixture from './api/__fixtures__/missions.list.json'
import parametersFixture from './api/__fixtures__/lifecycle/parameters.json'

/** The words that never appear (docs/design-glossary.md), as whole words, any case. */
const BANNED = /\b(best|safest|recommended|score|likely|chance|survives)\b/i

const SITES: Site[] = [
  ['connecting-ridge', 'B', 'Connecting Ridge', -89.44],
  ['malapert-massif', 'G', 'Malapert massif', -85.99],
  ['faustini-rim', 'I', 'Faustini rim', -87.18],
].map(([id, code, name, lat]) => ({
  id: id as string,
  code: code as string,
  name: name as string,
  latDeg: lat as number,
  lonDeg: 0,
  elevM: 0,
  note: 'A candidate site.',
  searchKind: 'rim',
  kind: 'candidate',
  coordinateRule: 'derived_open_sky',
  terrainModelled: true,
}))

const HORIZON = {
  site_id: 'connecting-ridge',
  azimuth_step_deg: 90,
  azimuth_count: 4,
  el_deg: [0, 0, 0, 0],
  range_m: [0, 0, 0, 0],
  tol_deg: [0, 0, 0, 0],
  max_el_deg: 0,
  max_el_bearing_deg: 0,
  meta: (metricsFixture as unknown as MetricsDTO).meta,
}

const NOT_ENTERED = (parametersFixture as unknown as { parameters: ParameterDTO[] }).parameters.map((p) =>
  p.id === 'battery_limit_h' ? { ...p, value: { ...p.value, value: null, missing_reason: 'Not entered.' } } : p,
)

/** One of each kind of place: a definite 1st, a lower bound, and an edge that skims the skyline. */
function item(siteId: string, position: number, over: Partial<CompareItemDTO>): CompareItemDTO {
  return {
    site_id: siteId,
    position,
    rank: position,
    rank_range: [position, position],
    tied: false,
    tied_with: [],
    incomparable_with: [],
    censored: false,
    grazing: false,
    uncertainty_s: 3600,
    metrics: metricsFixture as unknown as CompareItemDTO['metrics'],
    delta_vs_best: {},
    ...over,
  } as CompareItemDTO
}

beforeEach(() => {
  setSites(SITES)
  useMission.setState({ compareIds: SITES.map((s) => s.id), siteId: 'connecting-ridge', rankBy: 'longestDark' })
  vi.spyOn(api, 'metrics').mockResolvedValue(metricsFixture as unknown as MetricsDTO)
  vi.spyOn(api, 'windows').mockResolvedValue(windowsFixture as unknown as WindowsDTO)
  vi.spyOn(api, 'horizon').mockResolvedValue(HORIZON as never)
  vi.spyOn(api, 'timeline').mockReturnValue(new Promise(() => {}))
  vi.spyOn(api, 'health').mockRejectedValue(new Error('not in this test'))
  vi.spyOn(api, 'missions').mockResolvedValue(missionsFixture as never)
  vi.spyOn(api, 'parameters').mockResolvedValue({ parameters: NOT_ENTERED })
  vi.spyOn(api, 'compare').mockImplementation(async (body) => ({
    window: { start: '2027-03-14T00:00:00Z', end: '2027-04-12T12:45:00Z', step_s: 900 } as never,
    rank_by: body.rank_by,
    items: [
      item('connecting-ridge', 1, {}),
      item('malapert-massif', 2, { rank: null, rank_range: [2, 3], censored: true }),
      item('faustini-rim', 3, { rank: null, rank_range: [1, 3], grazing: true, uncertainty_s: null }),
    ],
    ties: [],
    unavailable: [],
    meta: (metricsFixture as unknown as MetricsDTO).meta as never,
  }))
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

/** Every word a reader can meet on the page: text (visible, screen-reader, transcript), names and tooltips. */
function everything(): string {
  const attrs = [...document.body.querySelectorAll('[aria-label],[title],[aria-description]')].flatMap((el) =>
    ['aria-label', 'title', 'aria-description'].map((a) => el.getAttribute(a) ?? ''),
  )
  return [document.body.textContent ?? '', ...attrs].join(' \n ').replace(/ /g, ' ')
}

describe('no verdict words on the pages that compare sites', () => {
  it('Compare: the order, its places and the limit say no verdict', async () => {
    renderApp(createElement(CompareScreen), { route: '/compare' })
    await screen.findByText(/^In order of longest night, shortest first,/, {}, { timeout: 5000 })
    const words = everything()
    expect(words).not.toMatch(BANNED)
    // What it says instead: a place, the number it is by, and the limit's label.
    expect(words).toContain('1st by longest night')
    expect(words).toContain('120 h battery limit (assumed)')
    expect(words).toContain('Because the Sun skims the skyline at the start or end of this night.')
    expect(words).toMatch(/can't be ranked, because the chosen dates cut its value short; it could be 2nd to 3rd/)
    expect(words).not.toMatch(/[–—]/)
  })

  it('Report: the cards and "Against the battery limit" say no verdict, and no sentence that is not worked out', async () => {
    renderApp(createElement(ReportScreen), { route: '/report' })
    await screen.findByText('Against the battery limit', {}, { timeout: 5000 })
    const words = everything()
    expect(words).not.toMatch(BANNED)
    expect(words).not.toMatch(/latitude, not terrain|Assessment/)
    expect(words).toContain('1st by longest night')
    expect(words).toMatch(/within the margin of the 120 h battery limit \(assumed\)/)
    expect(words).not.toMatch(/[–—]/)
  })
})
