// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { renderApp } from '../../test/render'
import { api, ApiError } from '../../lib/api/client'
import type { AuditEntryDTO, FeedsDTO, ParameterDTO, RiskScaleDTO, RiskScalesDTO } from '../../lib/api/lifecycle'
import { useSession } from '../../lib/session'
import { DataSources, levelsHaveNoWords, parameterChangeWords, ParametersPanel, RiskScalePanel } from './ProjectPanels'
import parametersFixture from '../../lib/api/__fixtures__/lifecycle/parameters.json'
import riskScalesFixture from '../../lib/api/__fixtures__/lifecycle/risk-scales.json'
import historyFixture from '../../lib/api/__fixtures__/lifecycle/history-parameter.json'
import feedsFixture from '../../lib/api/__fixtures__/lifecycle/feeds.json'

const parameters = parametersFixture as unknown as { parameters: ParameterDTO[] }
const scales = riskScalesFixture as unknown as RiskScalesDTO
const history = (historyFixture as unknown as { entries: AuditEntryDTO[] }).entries
const feeds = feedsFixture as unknown as FeedsDTO

beforeEach(() => {
  useSession.setState({
    session: { token: 't', roleName: 'Project manager', expiresAt: Date.now() + 3_600_000, offline: false, user: { id: 7, name: 'A. Rahman', team: null } },
  })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  useSession.setState({ session: null })
})

const openRow = (title: string) => fireEvent.click(screen.getByText(title, { selector: 'summary' }))
/** The list item whose whole text starts with these words (an item's first words sit in a child element). */
const itemStarting = (words: string) => screen.getAllByRole('listitem').find((li) => li.textContent?.startsWith(words) && !li.querySelector('li'))

describe('Settings → Project: the risk scale as built', () => {
  it('a scale whose levels are only numbers says so in one sentence instead of a table of repeats', async () => {
    expect(levelsHaveNoWords(scales.scales[0])).toBe(true)
    vi.spyOn(api, 'riskScales').mockResolvedValue(scales)
    renderApp(<RiskScalePanel enabled />)
    openRow('Risk scale')
    await screen.findByText(/No words are entered for the levels yet/)
    expect(screen.getByText(/5 likelihood levels, and 5 consequence levels for each of/).textContent).toContain(
      'safety, technical, cost and schedule, 1 the lowest',
    )
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.getByRole('link', { name: 'standards.nasa.gov' })).toBeTruthy()
    expect(screen.getByText(/GPR 7120.4, which is not public/)).toBeTruthy()
  })

  it('a scale with words for its levels is a table, one row per level', async () => {
    const worded: RiskScaleDTO = {
      ...scales.scales[0],
      likelihood: scales.scales[0].likelihood.map((l) => ({ ...l, words: l.level === 1 ? 'Very unlikely' : l.words })),
    }
    expect(levelsHaveNoWords(worded)).toBe(false)
    vi.spyOn(api, 'riskScales').mockResolvedValue({ default_id: worded.id, scales: [worded] })
    renderApp(<RiskScalePanel enabled />)
    openRow('Risk scale')
    const table = await screen.findByRole('table')
    expect(within(table).getAllByRole('row')).toHaveLength(6)
    expect(within(table).getByText('Very unlikely')).toBeTruthy()
  })
})

describe('Settings → Project: parameters as built', () => {
  it('each change in words, with the unit the way the screens write it', () => {
    expect(parameterChangeWords(history[0], 'h')).toBe('120 h → 96 h')
    expect(parameterChangeWords(history[1], 'h')).toBe('Set to 120 h')
    expect(parameterChangeWords({ ...history[1], after: { value: 12, note: null } }, 'deg')).toBe('Set to 12°')
    expect(parameterChangeWords({ ...history[0], before: { value: 96, note: null } }, 'h')).toBe('Note changed; the value stays 96 h')
  })

  it('how many are entered; a missing one says why, never a zero; an entered one says who set it', async () => {
    vi.spyOn(api, 'parameters').mockResolvedValue(parameters)
    renderApp(<ParametersPanel enabled />)
    await screen.findByText('1 of 4 entered')
    openRow('Parameters')
    expect(screen.getAllByText('Not entered yet')).toHaveLength(3)
    expect(screen.getByText(/No landing Sun height limit has been entered/)).toBeTruthy()
    expect(screen.getByText('96 h')).toBeTruthy()
    expect(screen.getByText(/From the lander power budget, rev C\. · set by A\. Rahman/)).toBeTruthy()
    expect(screen.getAllByRole('button', { name: /^Enter a value\s*for / })).toHaveLength(3)
  })

  it('change opens the form under the value with its history; Save sends the number and the note', async () => {
    vi.spyOn(api, 'parameters').mockResolvedValue(parameters)
    vi.spyOn(api, 'history').mockResolvedValue({ entries: history })
    const put = vi.spyOn(api, 'setParameter').mockResolvedValue(parameters)
    renderApp(<ParametersPanel enabled />)
    await screen.findByText('1 of 4 entered')
    openRow('Parameters')
    const change = screen.getByRole('button', { name: /^Change\s*for Battery limit/ })
    fireEvent.click(change)
    expect(change.getAttribute('aria-expanded')).toBe('true')
    expect(api.history).toHaveBeenCalledWith('parameter', 'battery_limit_h', expect.anything())
    expect(await screen.findByText('120 h → 96 h')).toBeTruthy()
    const changes = screen.getAllByText(/ → |^Set to /).map((n) => n.textContent)
    expect(changes).toEqual(['120 h → 96 h', 'Set to 120 h'])
    expect(screen.getByText('From the lander power budget, rev C.', { selector: 'li span' })).toBeTruthy()
    const value = screen.getByLabelText('Value, in hours') as HTMLInputElement
    expect(value.value).toBe('96')
    fireEvent.change(value, { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Enter a number.')).toBeTruthy()
    expect(put).not.toHaveBeenCalled()
    fireEvent.change(value, { target: { value: '100' } })
    fireEvent.change(screen.getByLabelText('Note (optional)'), { target: { value: 'Rev D' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(put).toHaveBeenCalledWith('battery_limit_h', { value: 100, note: 'Rev D' }))
    expect(await screen.findByText('Saved.')).toBeTruthy()
  })

  it('an out-of-range value is refused in the server’s words', async () => {
    vi.spyOn(api, 'parameters').mockResolvedValue(parameters)
    vi.spyOn(api, 'history').mockResolvedValue({ entries: [] })
    vi.spyOn(api, 'setParameter').mockRejectedValue(
      new ApiError(422, {
        detail: {
          title: 'That value could not be used',
          detail: 'Lowest Sun height allowed at landing: 120 deg is outside -5 to 90 deg',
          status: 422,
          ui: { still_works: 'Nothing was changed.' },
        },
      }),
    )
    renderApp(<ParametersPanel enabled />)
    await screen.findByText('1 of 4 entered')
    openRow('Parameters')
    fireEvent.click(screen.getByRole('button', { name: /^Enter a value\s*for Lowest Sun height/ }))
    expect(await screen.findByText('No changes recorded yet.')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Value, in degrees'), { target: { value: '120' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('120 deg is outside -5 to 90 deg')
    expect(screen.queryByText('Saved.')).toBeNull()
  })

  it('a server without parameters: the row is left out', async () => {
    vi.spyOn(api, 'parameters').mockRejectedValue(new ApiError(404, { detail: 'Not Found' }))
    const { container } = renderApp(<ParametersPanel enabled />)
    await waitFor(() => expect(api.parameters).toHaveBeenCalled())
    await waitFor(() => expect(container.textContent).toBe(''))
  })
})

describe('Settings → Data sources: the service’s note on a feed', () => {
  const glm = feeds.feeds.find((f) => f.provider === 'goes')!

  it('a product fetched only near a launch says why it holds nothing, in the service’s words, and is not called out of date', async () => {
    expect(glm.note).toMatch(/^Fetched only in the 6 hours before a designed launch opportunity/)
    vi.spyOn(api, 'feeds').mockResolvedValue(feeds)
    renderApp(<DataSources enabled live />)
    openRow('Data sources')
    await waitFor(() => expect(itemStarting('glm, florida')).toBeTruthy())
    const line = itemStarting('glm, florida')!
    expect(line.textContent).toBe(`glm, florida · no data yet · ${glm.note}`)
    expect(line.textContent).not.toContain('out of date')
    // The provider is working: its idle product is no fault.
    const provider = line.parentElement!.closest('li')!
    expect(within(provider).getByText('Working')).toBeTruthy()
    // A product with no note says nothing more than its age.
    expect(itemStarting('Protons and X-rays')!.textContent).toBe('Protons and X-rays · data from just now')
  })

  it('a stale product keeps its own state words, and its note too when it has one', async () => {
    const stale = { ...feeds, feeds: feeds.feeds.map((f) => (f.provider === 'ndbc' ? { ...f, note: 'Buoy 41010 is being serviced.' } : f)) }
    vi.spyOn(api, 'feeds').mockResolvedValue(stale)
    renderApp(<DataSources enabled live />)
    openRow('Data sources')
    await waitFor(() => expect(itemStarting('Buoy observations')).toBeTruthy())
    const line = itemStarting('Buoy observations')!
    expect(line.textContent).toContain('out of date')
    expect(line.textContent).toContain('The buoy has not reported since 21:00 UTC · Buoy 41010 is being serviced.')
  })
})
