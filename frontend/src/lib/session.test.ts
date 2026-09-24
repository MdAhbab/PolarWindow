// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * The session is read once, when the module loads, so each case loads a fresh
 * copy after arranging storage.
 */
async function fresh() {
  vi.resetModules()
  return import('./session')
}

beforeEach(() => localStorage.clear())
afterEach(() => vi.restoreAllMocks())

describe('session', () => {
  it('keeps a stored session that has not ended, and gives its token to the API client', async () => {
    const until = Date.now() + 3_600_000
    localStorage.setItem('pw-session', JSON.stringify({ token: 't', roleName: 'Project manager', expiresAt: until, offline: false }))
    const s = await fresh()
    expect(s.useSession.getState().session?.roleName).toBe('Project manager')
    expect(s.currentToken()).toBe('t')
  })

  it('drops a session that has ended, and anything it cannot read', async () => {
    localStorage.setItem('pw-session', JSON.stringify({ token: 't', roleName: 'Project manager', expiresAt: Date.now() - 1 }))
    expect((await fresh()).useSession.getState().session).toBeNull()
    localStorage.setItem('pw-session', '{not json')
    expect((await fresh()).useSession.getState().session).toBeNull()
    localStorage.setItem('pw-session', JSON.stringify({ token: 5, roleName: 'x', expiresAt: Date.now() + 1000 }))
    expect((await fresh()).useSession.getState().session).toBeNull()
  })

  it('signs in with one request and stores the answer', async () => {
    const expires = new Date(Date.now() + 3_600_000).toISOString()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ token: 'abc', role_name: 'Project manager', expires_at: expires }), { status: 200 }),
    )
    const s = await fresh()
    const got = await s.useSession.getState().signIn()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/auth\/demo$/)
    expect(got).toMatchObject({ token: 'abc', offline: false })
    expect(JSON.parse(localStorage.getItem('pw-session')!).token).toBe('abc')
  })

  it('opens the saved copy when no server answers, and says why when one refuses', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new TypeError('Failed to fetch'))
    let s = await fresh()
    expect(await s.useSession.getState().signIn()).toMatchObject({ token: null, offline: true })

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: { title: 'One-click sign-in is turned off', detail: 'Turned off here.' } }), { status: 403 }),
    )
    s = await fresh()
    await expect(s.useSession.getState().signIn()).rejects.toThrow('Turned off here.')
  })

  it('signs out by forgetting the session', async () => {
    localStorage.setItem('pw-session', JSON.stringify({ token: 't', roleName: 'Project manager', expiresAt: Date.now() + 60_000 }))
    const s = await fresh()
    s.useSession.getState().signOut()
    expect(s.useSession.getState().session).toBeNull()
    expect(localStorage.getItem('pw-session')).toBeNull()
  })
})
