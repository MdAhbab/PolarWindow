// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, screen, waitFor } from '@testing-library/react'
import { MissionsScreen } from './MissionsScreen'
import { renderApp } from '../test/render'
import listFixture from '../lib/api/__fixtures__/missions.list.json'

type Reply = { status: number; body: unknown } | 'pending'

/** Answers the app's requests by path; anything else stays pending. */
function stubApi(missions: (url: URL) => Reply) {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url = new URL(String(input))
      let reply: Reply = 'pending'
      if (url.pathname.endsWith('/missions')) reply = missions(url)
      else if (url.pathname.endsWith('/sites')) reply = { status: 200, body: { items: [], total: 0, meta: listFixture.meta } }
      if (reply === 'pending') return new Promise(() => {})
      const r = reply
      return Promise.resolve(new Response(JSON.stringify(r.body), { status: r.status, headers: { 'content-type': 'application/json' } }))
    }),
  )
}

const filtered = (url: URL) => url.searchParams.has('status') || url.searchParams.has('provider') || url.searchParams.has('payload_type')

beforeEach(() => vi.unstubAllGlobals())
afterEach(cleanup)

describe('the mission list', () => {
  it('loading: a progress panel in the list column, not a spinner', () => {
    stubApi(() => 'pending')
    renderApp(<MissionsScreen />, { route: '/missions' })
    expect(screen.getByText('Loading CLPS missions')).toBeTruthy()
    expect(screen.getByRole('progressbar')).toBeTruthy()
  })

  it('names every row from the data, in the handoff order, and counts them in a live region', async () => {
    stubApi(() => ({ status: 200, body: listFixture }))
    renderApp(<MissionsScreen />, { route: '/missions' })
    const im2 = await screen.findByRole('link', {
      name: /^IM-2, Intuitive Machines, landed 6 March 2025, 17:30 UTC, Partly successful, carries volatiles, technology demonstration, laser retroreflector/,
    })
    expect(im2.getAttribute('href')).toBe('/missions/im-2')
    expect(screen.getByRole('link', { name: /^CS-8, provider unconfirmed, landing date unconfirmed, Planned/ })).toBeTruthy()
    const count = screen.getByText((_, el) => el?.getAttribute('aria-live') === 'polite' && /missions$/.test(el.textContent ?? ''))
    expect(count.textContent).toBe('Showing 4 of 4 missions')
  })

  it('empty: says which filters excluded everything and relaxes them in one click', async () => {
    stubApi((url) =>
      filtered(url) ? { status: 200, body: { ...listFixture, items: [], total: 0 } } : { status: 200, body: listFixture },
    )
    renderApp(<MissionsScreen />, { route: '/missions?status=flown&provider=Blue%20Origin' })
    expect(await screen.findByText('No missions match these filters')).toBeTruthy()
    expect(screen.getByText(/status Flown; provider Blue Origin/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Clear filters' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Remove Blue Origin' })).toBeTruthy()
  })

  it('error: the server problem, never a loader', async () => {
    stubApi(() => ({
      status: 503,
      body: { detail: { title: 'The mission table is not loaded', detail: 'Run make seed.', ui: { still_works: 'Sites and their numbers are unaffected.', retryable: true } } },
    }))
    renderApp(<MissionsScreen />, { route: '/missions' })
    expect(await screen.findByText('The mission table is not loaded')).toBeTruthy()
    expect(screen.getByText('Sites and their numbers are unaffected.')).toBeTruthy()
    await waitFor(() => expect(screen.queryByText('Loading CLPS missions')).toBeNull())
  })
})
