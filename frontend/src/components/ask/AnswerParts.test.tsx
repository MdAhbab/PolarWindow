// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, screen } from '@testing-library/react'
import type { ProvenanceItemDTO } from '../../lib/api/client'
import { AnswerTiles, lookupWords } from './AnswerParts'
import { renderApp } from '../../test/render'

afterEach(cleanup)

const item = (field: string, value: number, extra: Partial<ProvenanceItemDTO> = {}): ProvenanceItemDTO => ({
  claim: '…',
  value,
  tool: 'get_site_metrics',
  call_seq: 1,
  field,
  ...extra,
})

describe('AnswerTiles', () => {
  it('shows durations with their margin, shares as a bar, and leaves other numbers in the sentence', () => {
    renderApp(
      <AnswerTiles
        href="/missions/im-2/surface"
        items={[
          item('longest_dark_h', 122.5, { margin: 0.4, unit: 'h' }),
          item('longest_blackout_h', 40, { margin: null, unit: 'h' }),
          item('sun_fraction_up', 0.62),
          item('count', 3),
        ]}
      />,
    )
    const tiles = screen.getAllByRole('link')
    expect(tiles).toHaveLength(3)
    expect(tiles[0].textContent).toContain('122.5 h')
    expect(tiles[0].textContent).toContain('± 0.4 h')
    expect(tiles[1].textContent).toContain('no margin given')
    expect(tiles[2].textContent).toContain('62%')
    expect(tiles[0].getAttribute('href')).toBe('/missions/im-2/surface')
  })

  it('draws nothing when the answer has no durations or shares', () => {
    const { container } = renderApp(<AnswerTiles items={[item('count', 3)]} />)
    expect(container.querySelector('ul')).toBeNull()
  })
})

describe('lookupWords', () => {
  it('says what was looked up and over which dates', () => {
    const w = lookupWords('get_site_metrics', { start: '2026-06-01T00:00:00Z', end: '2026-06-30T00:00:00Z' })
    expect(w).toMatch(/1 Jun 2026 to 30 Jun 2026$/)
  })
})
