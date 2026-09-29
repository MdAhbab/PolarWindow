// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { renderApp } from '../../test/render'
import { api } from '../../lib/api/client'
import type { RelayCatalogueDTO, RelayChoiceDTO, RelayRowDTO } from '../../lib/api/lifecycle'
import relaysFixture from '../../lib/api/__fixtures__/lifecycle/relays.json'
import { MAX_COMPARED, RelayCompare, relaysToAdd, sameRelays } from './RelayCompare'
import { PlanDownload, listable, parseRate, planUrl } from './PlanDownload'

const catalogue = relaysFixture as unknown as RelayCatalogueDTO
/** The row's title sits in a span inside its summary. */
const summaryOf = (title: string) => screen.getByText(title).closest('summary') as HTMLElement
const openRow = (title: string) => fireEvent.click(summaryOf(title))
const lp = catalogue.relays.find((r) => r.id === 'lunar-pathfinder') as RelayChoiceDTO
const altus = catalogue.relays.find((r) => r.id === 'altus-1') as RelayChoiceDTO

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

const more = (id: string, over: Partial<RelayChoiceDTO> = {}): RelayChoiceDTO => ({ ...lp, id, name: `Relay ${id}`, serves_missions: [], ...over })

describe('Compare a relay', () => {
  it('offers the catalogue’s relays that are not already counted for the mission, in the catalogue’s order', () => {
    expect(relaysToAdd(catalogue.relays, []).map((r) => r.id)).toEqual(['lunar-pathfinder', 'altus-1'])
    expect(relaysToAdd(catalogue.relays, ['altus-1']).map((r) => r.id)).toEqual(['lunar-pathfinder'])
    expect(relaysToAdd(catalogue.relays, ['altus-1', 'lunar-pathfinder'])).toEqual([])
    expect(sameRelays(['b', 'a'], ['a', 'b'])).toBe(true)
    expect(sameRelays(['a'], ['a', 'b'])).toBe(false)
  })

  it('shows each relay with its status in words and plan, and asks for the numbers again only when the choice changed', async () => {
    vi.spyOn(api, 'relays').mockResolvedValue(catalogue)
    const onApply = vi.fn()
    renderApp(<RelayCompare own={['altus-1']} applied={[]} onApply={onApply} />)
    await screen.findByText('Compare a relay')
    openRow('Compare a relay')
    const box = await screen.findByRole('checkbox', { name: /^Lunar Pathfinder/ })
    // Each relay says who runs it, where it stands and its launch plan; the mission's own relay is not offered.
    expect(box.closest('label')?.textContent).toMatch(/Surrey Satellite Technology Ltd/)
    expect(box.closest('label')?.textContent).toMatch(/Planned, not launched\. To fly on Firefly’s Blue Ghost Mission 2|Planned, not launched\. To fly on Firefly's Blue Ghost Mission 2/)
    expect(screen.queryByRole('checkbox', { name: /Altus-1/ })).toBeNull()
    expect(screen.getByText('none added')).toBeTruthy()
    // Nothing is worked out by ticking: the button is asked.
    const go = screen.getByRole('button', { name: 'Work out the numbers with these' }) as HTMLButtonElement
    expect(go.disabled).toBe(true)
    fireEvent.click(box)
    expect(go.disabled).toBe(false)
    expect(onApply).not.toHaveBeenCalled()
    fireEvent.click(go)
    expect(onApply).toHaveBeenCalledWith(['lunar-pathfinder'])
  })

  it('names what is added, starts open, and takes them out on request', async () => {
    vi.spyOn(api, 'relays').mockResolvedValue(catalogue)
    const onApply = vi.fn()
    renderApp(<RelayCompare own={[]} applied={['altus-1']} onApply={onApply} />)
    const row = (await screen.findByText('Compare a relay')).closest('details') as HTMLDetailsElement
    expect(row.open).toBe(true)
    expect(row.textContent).toContain('Altus-1 data-relay satellite')
    const box = (await screen.findByRole('checkbox', { name: /^Altus-1/ })) as HTMLInputElement
    expect(box.checked).toBe(true)
    fireEvent.click(box)
    fireEvent.click(screen.getByRole('button', { name: 'Work out the numbers without them' }))
    expect(onApply).toHaveBeenCalledWith([])
  })

  it('stops at three, and says when a relay’s orbit is not known well enough to work out', async () => {
    const many: RelayCatalogueDTO = {
      relays: [lp, altus, more('r3'), more('r4', { orbit_known: false, orbit_note: null })],
    }
    vi.spyOn(api, 'relays').mockResolvedValue(many)
    renderApp(<RelayCompare own={[]} applied={[]} onApply={() => {}} />)
    await screen.findByText('Compare a relay')
    openRow('Compare a relay')
    for (const name of [/^Lunar Pathfinder/, /^Altus-1/, /^Relay r3/]) fireEvent.click(await screen.findByRole('checkbox', { name }))
    expect(MAX_COMPARED).toBe(3)
    expect((screen.getByRole('checkbox', { name: /^Relay r4/ }) as HTMLInputElement).disabled).toBe(true)
    expect(screen.getByText(/Its orbit is not published, so no time through it can be worked out/)).toBeTruthy()
    // One taken out, and the fourth can be ticked instead.
    fireEvent.click(screen.getByRole('checkbox', { name: /^Relay r3/ }))
    expect((screen.getByRole('checkbox', { name: /^Relay r4/ }) as HTMLInputElement).disabled).toBe(false)
  })

  it('has nothing to show when every relay is counted already and none was added; says so when the list does not load', async () => {
    vi.spyOn(api, 'relays').mockResolvedValue(catalogue)
    const { container, unmount } = renderApp(<RelayCompare own={['lunar-pathfinder', 'altus-1']} applied={[]} onApply={() => {}} />)
    await waitFor(() => expect(api.relays).toHaveBeenCalled())
    await waitFor(() => expect(container.querySelector('details')).toBeNull())
    unmount()
    vi.spyOn(api, 'relays').mockRejectedValue(new Error('offline'))
    renderApp(<RelayCompare own={[]} applied={[]} onApply={() => {}} />)
    await screen.findByText('Compare a relay')
    openRow('Compare a relay')
    // The hook tries once more after a failure that is not a refusal, so the message comes a moment later.
    expect(await screen.findByText(/The list of relays could not be loaded: the service did not answer\./, {}, { timeout: 4000 })).toBeTruthy()
  })
})

const row = (id: string, name: string, adds: { lo: number | null; hi: number | null }): RelayRowDTO =>
  ({
    id,
    name,
    status: 'x',
    adds_h: { value: adds.lo, unit: 'h', provenance: 'assumed', pm: null, lo: adds.lo, hi: adds.hi, factor: null, open: false, no_margin_reason: null, missing_reason: null, source: null },
  }) as unknown as RelayRowDTO

describe('The contact plan download', () => {
  const t0 = Date.parse('2027-03-20T00:00:00Z')
  const t1 = Date.parse('2027-03-22T00:00:00Z')

  it('reads a data rate as people write it, and nothing that is not above zero', () => {
    expect(parseRate('2,000,000')).toBe(2_000_000)
    expect(parseRate(' 250 000 ')).toBe(250_000)
    expect(parseRate('1.5e6')).toBe(1_500_000)
    for (const bad of ['', '   ', '0', '-5', 'fast', '12 Mbps']) expect(parseRate(bad), bad).toBeNull()
  })

  it('addresses the plan for the dates on screen: the rate only for ION, the relays only when asked', () => {
    const base = 'http://localhost:8000/api/v1/missions/im-3/contact/plan'
    const dates = 'start=2027-03-20T00%3A00%3A00.000Z&end=2027-03-22T00%3A00%3A00.000Z'
    expect(planUrl('im-3', 'csv', t0, t1)).toBe(`${base}?format=csv&${dates}`)
    expect(planUrl('im-3', 'csv', t0, t1, { rateBps: 5, relays: [] })).toBe(`${base}?format=csv&${dates}`)
    expect(planUrl('im-3', 'ion', t0, t1, { rateBps: 2_000_000 })).toBe(`${base}?format=ion&${dates}&rate_bps=2000000`)
    expect(planUrl('im-3', 'ion', t0, t1, { rateBps: 2_000_000, relays: ['altus-1', 'lunar-pathfinder'] })).toBe(
      `${base}?format=ion&${dates}&rate_bps=2000000&relay=altus-1&relay=lunar-pathfinder`,
    )
  })

  it('offers the ION plan only with a data rate, and lists a planned relay’s contacts only when asked', () => {
    const relays = [row('altus-1', 'Altus-1 data-relay satellite', { lo: 0, hi: 2 }), row('x-relay', 'Relay X', { lo: null, hi: null })]
    expect(relays.map(listable)).toEqual([true, false])
    renderApp(<PlanDownload missionId="im-3" start={t0} end={t1} relays={relays} />)
    openRow('Download the contact plan')
    // No rate yet: no ION link, and the spreadsheet is a link at once.
    expect(screen.getByRole('button', { name: 'Contact plan for ION (DTN)' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByRole('link', { name: 'Spreadsheet (CSV)' }).getAttribute('href')).not.toContain('relay=')
    fireEvent.change(screen.getByLabelText('Data rate for the ION plan, bits per second'), { target: { value: '2,000,000' } })
    const ion = screen.getByRole('link', { name: 'Contact plan for ION (DTN)' })
    expect(ion.getAttribute('href')).toContain('format=ion')
    expect(ion.getAttribute('href')).toContain('rate_bps=2000000')
    expect(ion.getAttribute('href')).not.toContain('relay=')
    // Ask for the relay's contacts: both files name it; the one that cannot be listed is not asked for, and is said.
    fireEvent.click(screen.getByRole('checkbox', { name: /Include the contacts of the planned relay: Altus-1 data-relay satellite\./ }))
    expect(screen.getByRole('link', { name: 'Contact plan for ION (DTN)' }).getAttribute('href')).toContain('relay=altus-1')
    expect(screen.getByRole('link', { name: 'Spreadsheet (CSV)' }).getAttribute('href')).toContain('relay=altus-1')
    expect(screen.getByRole('link', { name: 'Spreadsheet (CSV)' }).getAttribute('href')).not.toContain('x-relay')
    expect(screen.getByText('No contacts can be listed for Relay X: its orbit is not known well enough.')).toBeTruthy()
    // Something that is not a number says so and takes the ION link away again.
    fireEvent.change(screen.getByLabelText('Data rate for the ION plan, bits per second'), { target: { value: 'fast' } })
    expect(screen.getByText('Give a number above zero.')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Contact plan for ION (DTN)' }).hasAttribute('disabled')).toBe(true)
  })
})
