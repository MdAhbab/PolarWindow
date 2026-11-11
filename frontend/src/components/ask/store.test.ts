import { beforeEach, describe, expect, it } from 'vitest'
import type { ChatResponseDTO } from '../../lib/api/experience.types'
import { ApiError } from '../../lib/api/client'
import {
  MAX_MESSAGES,
  contextWords,
  historyFor,
  isAskShortcut,
  suggestionsFor,
  useAsk,
  type AskTurn,
} from './store'
import { announcement, answerActions, answerFollowUps, answeredByRules, isSignedOut } from './answer'

/** A chat answer as the service sends it, with only what a test changes spelled out. */
function reply(over: Partial<ChatResponseDTO> = {}, answer: string | null = 'IM-3 can launch from LC-39A.'): ChatResponseDTO {
  return {
    status: 'ok',
    run_status: 'ok',
    attempts: 1,
    latency_ms: 1200,
    provenance: [],
    tool_calls: [],
    run_id: 'run-1',
    meta: { model: 'light-model', agents_configured: true } as ChatResponseDTO['meta'],
    result:
      answer === null
        ? null
        : { answer, interpreted_as: 'About IM-3, Launch.', follow_ups: [], actions: [] },
    ...over,
  }
}

const ctx = { path: '/missions/im-3/launch', mission_id: 'im-3', section: 'launch' as const }

function turn(id: number, question: string, state: AskTurn['state'], response: ChatResponseDTO | null = null): AskTurn {
  return { id, question, context: ctx, about: null, state, response, error: null }
}

const key = (k: string, mods: Partial<{ ctrlKey: boolean; metaKey: boolean; altKey: boolean }> = {}) => ({
  key: k,
  ctrlKey: false,
  metaKey: false,
  altKey: false,
  ...mods,
})
const page = { typing: false, inDialog: false }

describe('the Ask shortcuts', () => {
  it('opens on / outside a field, and on Ctrl+K or Cmd+K anywhere outside a modal', () => {
    expect(isAskShortcut(key('/'), page, true)).toBe(true)
    expect(isAskShortcut(key('k', { ctrlKey: true }), page, true)).toBe(true)
    expect(isAskShortcut(key('K', { metaKey: true }), { typing: true, inDialog: false }, false)).toBe(true)
  })

  it('leaves / to a field, to a switched-off shortcut map and to an open modal', () => {
    expect(isAskShortcut(key('/'), { typing: true, inDialog: false }, true)).toBe(false)
    expect(isAskShortcut(key('/'), page, false)).toBe(false)
    expect(isAskShortcut(key('k', { ctrlKey: true }), { typing: false, inDialog: true }, true)).toBe(false)
    expect(isAskShortcut(key('/', { ctrlKey: true }), page, true)).toBe(false)
    expect(isAskShortcut(key('k'), page, true)).toBe(false)
  })
})

describe('the Ask store', () => {
  beforeEach(() => useAsk.setState({ isOpen: false, text: null, textId: 0, turns: [], nextId: 1 }))

  it('keeps the conversation: a question goes out, then is answered, fails, or is taken back without a trace', () => {
    const s = () => useAsk.getState()
    const a = s().begin('When can IM-3 launch?', ctx, 'About IM-3 · Launch')
    const b = s().begin('And land?', ctx)
    const c = s().begin('And talk to Earth?', ctx)
    expect([a, b, c]).toEqual([1, 2, 3])
    expect(s().turns.map((t) => [t.state, t.about])).toEqual([
      ['asking', 'About IM-3 · Launch'],
      ['asking', null],
      ['asking', null],
    ])
    const r = reply()
    s().answer(a, r)
    s().fail(b, new Error('no'))
    s().drop(c)
    expect(s().turns.map((t) => t.state)).toEqual(['answered', 'failed'])
    expect(s().turns[0].response).toBe(r)
    // Closing the dock keeps the conversation; starting over forgets it.
    s().close()
    expect(s().turns).toHaveLength(2)
    s().clear()
    expect(s().turns).toEqual([])
    expect(s().begin('Again?', ctx)).toBe(4)
  })

  it('opens, closes and toggles', () => {
    useAsk.getState().open()
    expect(useAsk.getState().isOpen).toBe(true)
    useAsk.getState().close()
    expect(useAsk.getState().isOpen).toBe(false)
    useAsk.getState().toggle()
    expect(useAsk.getState().isOpen).toBe(true)
  })

  it('carries the words it was opened with, and the same words twice arrive twice', () => {
    useAsk.getState().open('  When can IM-3 launch? ')
    expect(useAsk.getState()).toMatchObject({ isOpen: true, text: 'When can IM-3 launch?', textId: 1 })
    useAsk.getState().open('When can IM-3 launch?')
    expect(useAsk.getState().textId).toBe(2)
    useAsk.getState().open('   ')
    expect(useAsk.getState().textId).toBe(2)
  })
})

describe('the history sent with a question', () => {
  it('carries each answered question and its answer, oldest first, then the question', () => {
    const turns = [
      turn(1, 'When can IM-3 launch?', 'answered', reply()),
      turn(2, 'Is it safe?', 'failed'),
      turn(3, 'And the trip?', 'answered', reply({}, null)),
      turn(4, 'Still asking', 'asking'),
    ]
    expect(historyFor(turns, '  And landing?  ')).toEqual([
      { role: 'user', text: 'When can IM-3 launch?' },
      { role: 'assistant', text: 'IM-3 can launch from LC-39A.' },
      { role: 'user', text: 'And landing?' },
    ])
  })

  it('sends at most twelve messages and never starts on an answer', () => {
    const turns = Array.from({ length: 9 }, (_, i) => turn(i + 1, `Question ${i + 1}`, 'answered', reply({}, `Answer ${i + 1}`)))
    const sent = historyFor(turns, 'Last one')
    expect(sent.length).toBeLessThanOrEqual(MAX_MESSAGES)
    expect(sent[0]).toEqual({ role: 'user', text: 'Question 5' })
    expect(sent.at(-1)).toEqual({ role: 'user', text: 'Last one' })
    // Questions and answers alternate all the way.
    expect(sent.every((m, i) => m.role === (i % 2 === 0 ? 'user' : 'assistant'))).toBe(true)
  })

  it('cuts a long message to what the service takes', () => {
    expect(historyFor([], 'x'.repeat(2500))[0].text).toHaveLength(2000)
  })
})

describe('what "this" means to Ask', () => {
  it('names the mission and step, or the site, for the chip', () => {
    expect(contextWords(ctx, { mission: 'IM-3' })).toBe('About IM-3 · Launch')
    expect(contextWords({ path: '/missions/im-3', mission_id: 'im-3' })).toBe('About im-3')
    expect(contextWords({ path: '/site', site_id: 'shackleton-rim' }, { site: 'Shackleton rim' })).toBe('About Shackleton rim')
    expect(contextWords({ path: '/home' })).toBeNull()
  })

  it('offers questions about the step open first, then the others', () => {
    expect(suggestionsFor({ ...ctx, section: 'contact' }, { mission: 'IM-3' })).toEqual([
      'When can the Deep Space Network hear IM-3?',
      'When can IM-3 launch?',
      'How much sunlight does IM-3 get on the surface?',
    ])
    expect(suggestionsFor({ path: '/home' })).toHaveLength(3)
  })
})

describe('reading an answer', () => {
  it('says when rules, not a model, put the answer together, and why', () => {
    expect(answeredByRules(reply())).toBeNull()
    expect(answeredByRules(reply({ status: 'degraded', run_status: 'guard_rejected' }))).toBe('guard')
    expect(
      answeredByRules(reply({ status: 'degraded', run_status: 'degraded', meta: { agents_configured: false } as ChatResponseDTO['meta'] })),
    ).toBe('no_model')
    expect(answeredByRules(reply({ status: 'degraded', run_status: 'timeout' }))).toBe('unavailable')
  })

  it('follows only links inside the app, each once, and offers each next question once', () => {
    const r = reply({
      result: {
        answer: 'a',
        interpreted_as: 'b',
        follow_ups: ['When can IM-3 launch?', ' ', 'When can IM-3 launch?', 'What about the trip?'],
        actions: [
          { label: 'IM-3 · Launch', href: '/missions/im-3/launch' },
          { label: 'Elsewhere', href: 'https://example.com' },
          { label: 'Sneaky', href: '//example.com/x' },
          { label: 'Script', href: 'javascript:alert(1)' },
          { label: 'IM-3 again', href: '/missions/im-3/launch' },
          { label: 'IM-3', href: '/missions/im-3' },
        ],
      },
    })
    expect(answerActions(r)).toEqual([
      { label: 'IM-3 · Launch', href: '/missions/im-3/launch' },
      { label: 'IM-3', href: '/missions/im-3' },
    ])
    expect(answerFollowUps(r)).toEqual(['When can IM-3 launch?', 'What about the trip?'])
  })

  it('tells a screen reader where the newest question stands, and a refused session apart from other failures', () => {
    const signedOut = new ApiError(401, { detail: { title: 'Sign in first' } })
    expect(isSignedOut(signedOut)).toBe(true)
    expect(isSignedOut(new ApiError(503, null))).toBe(false)
    expect(announcement(undefined)).toBe('')
    expect(announcement(turn(1, 'q', 'asking'))).toBe('Working out an answer.')
    expect(announcement({ ...turn(1, 'q', 'failed'), error: signedOut })).toBe('Not answered: sign in to ask.')
    expect(announcement(turn(1, 'q', 'answered', reply()))).toBe('Answer: IM-3 can launch from LC-39A.')
    expect(
      announcement(turn(1, 'q', 'answered', reply({ status: 'degraded', run_status: 'timeout' }))),
    ).toBe('Answer: Answered from rules, not a model. IM-3 can launch from LC-39A.')
  })
})
