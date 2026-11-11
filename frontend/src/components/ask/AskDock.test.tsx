// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, screen } from '@testing-library/react'
import { renderApp } from '../../test/render'
import type { ChatResponseDTO } from '../../lib/api/experience.types'
import { AskDock } from './AskDock'
import { useAsk } from './store'

const answer: ChatResponseDTO = {
  status: 'ok',
  run_status: 'ok',
  attempts: 1,
  latency_ms: 1400,
  run_id: 'run-7',
  provenance: [{ claim: 'opens on 20 January 2027 with 3 days', value: 3, tool: 'get_mission_section', call_seq: 1, field: 'data.windows' }],
  tool_calls: [{ seq: 1, tool: 'get_mission_section', args: { mission_id: 'im-3' }, latency_ms: 40, number_count: 12 }],
  meta: { model: 'light-model', agents_configured: true } as ChatResponseDTO['meta'],
  result: {
    answer: 'The first launch window opens on 20 January 2027 with 3 days in it.',
    interpreted_as: 'About IM-3, Launch.',
    follow_ups: ['When can the Deep Space Network hear IM-3?'],
    actions: [
      { label: 'IM-3 · Launch', href: '/missions/im-3/launch' },
      { label: 'Not ours', href: 'https://example.com/' },
    ],
  },
}

type Reply = { status: number; body: unknown } | 'pending'

/** The service: the chat answers `chat`; the mission record never arrives (the chip falls back to the id). */
function stubApi(chat: Reply, others: Reply = 'pending') {
  const fetchMock = vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
    const path = new URL(String(input)).pathname
    const r = path.endsWith('/agents/chat') ? chat : others
    if (r === 'pending') return new Promise<Response>(() => {})
    return Promise.resolve(new Response(JSON.stringify(r.body), { status: r.status, headers: { 'content-type': 'application/json' } }))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const chatBodies = (f: ReturnType<typeof stubApi>) =>
  f.mock.calls
    .filter(([input]) => String(input).endsWith('/agents/chat'))
    .map(([, init]) => JSON.parse(String(init?.body)))

function ask(question: string) {
  fireEvent.change(screen.getByLabelText('Your question'), { target: { value: question } })
  fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
}

describe('the Ask dock', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
    useAsk.setState({ isOpen: true, text: null, textId: 0, turns: [], nextId: 1 })
  })
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('answers about the page open, with where to read more, what to ask next and how the AI got it', async () => {
    const f = stubApi({ status: 200, body: answer })
    renderApp(<AskDock />, { route: '/missions/im-3/launch' })

    const dock = screen.getByRole('complementary', { name: 'Ask' })
    expect(dock.textContent).toContain('About im-3 · Launch')
    // Empty, it offers questions about the step open first.
    expect(screen.getByRole('button', { name: 'When can im-3 launch?' })).toBeTruthy()

    ask('When can IM-3 launch?')
    expect(await screen.findByText('The first launch window opens on 20 January 2027 with 3 days in it.')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Open IM-3 · Launch' }).getAttribute('href')).toBe('/missions/im-3/launch')
    // A link out of the app is never offered.
    expect(screen.queryByText('Not ours')).toBeNull()
    expect(screen.getByText('How the AI got this')).toBeTruthy()
    expect(dock.textContent).toContain('AI answer · light-model · 1.4 s')
    expect(dock.textContent).toContain('Read as: About IM-3, Launch.')
    expect(screen.queryByText('Answered from rules, not a model')).toBeNull()
    expect(screen.getByRole('status').textContent).toContain('Answer: The first launch window opens')

    // A follow-up asks at once, with the conversation so far.
    fireEvent.click(screen.getByRole('button', { name: 'When can the Deep Space Network hear IM-3?' }))
    await screen.findAllByText('The first launch window opens on 20 January 2027 with 3 days in it.')
    const [first, second] = chatBodies(f)
    expect(first.messages).toEqual([{ role: 'user', text: 'When can IM-3 launch?' }])
    expect(first.context).toMatchObject({ path: '/missions/im-3/launch', mission_id: 'im-3', section: 'launch' })
    expect(second.messages.map((m: { role: string }) => m.role)).toEqual(['user', 'assistant', 'user'])
    expect(second.messages[2].text).toBe('When can the Deep Space Network hear IM-3?')
  })

  it('says sign-in is needed when the service refuses the session, and links to the front page', async () => {
    stubApi({ status: 401, body: { detail: { title: 'Sign in first', detail: 'No session.' } } }, { status: 401, body: {} })
    renderApp(<AskDock />, { route: '/home' })
    expect(screen.getByRole('complementary', { name: 'Ask' }).textContent).toContain('About any mission or site')

    ask('What is the space weather now?')
    expect(await screen.findByText('Sign in to ask')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Go to sign-in' }).getAttribute('href')).toBe('/')
    expect(screen.getByRole('status').textContent).toBe('Not answered: sign in to ask.')
    expect(screen.queryByText('How the AI got this')).toBeNull()
  })

  it('closes on Esc and gives focus back to what opened it', () => {
    stubApi('pending')
    useAsk.setState({ isOpen: false })
    renderApp(
      <>
        <button type="button">Opener</button>
        <AskDock />
      </>,
      { route: '/home' },
    )
    const opener = screen.getByRole('button', { name: 'Opener' })
    opener.focus()
    act(() => useAsk.getState().open())
    const field = screen.getByLabelText('Your question')
    field.focus()
    fireEvent.keyDown(field, { key: 'Escape' })
    expect(useAsk.getState().isOpen).toBe(false)
    expect(screen.queryByRole('complementary', { name: 'Ask' })).toBeNull()
    expect(document.activeElement).toBe(opener)
  })
})
