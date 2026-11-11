import { useEffect } from 'react'
import { create } from 'zustand'
import { useMission } from '../../lib/store'
import type { ChatContextDTO, ChatMessageDTO, ChatResponseDTO } from '../../lib/api/experience.types'

/** Where a question stands: being answered, answered (any status the API gave), or not sent through. */
export type TurnState = 'asking' | 'answered' | 'failed'

/** One question and what came back, with the page it was asked from. */
export interface AskTurn {
  id: number
  question: string
  context: ChatContextDTO
  state: TurnState
  response: ChatResponseDTO | null
  error: unknown
}

/**
 * Whether the Ask dock is open, the words it should start with, and the
 * conversation so far.
 *
 * The shell's Ask button, the `/` and Ctrl/Cmd+K shortcuts and Home's Ask bar
 * all come here; the dock reads it. `text` is a question someone already typed
 * or picked, with `textId` changing each time one is sent, so the same chip
 * pressed twice still arrives twice.
 *
 * The conversation lasts the session (a reload starts over): it is held here,
 * not in the dock, so closing the dock or moving to another page keeps it.
 */
interface AskState {
  isOpen: boolean
  text: string | null
  textId: number
  turns: AskTurn[]
  nextId: number
  open: (text?: string) => void
  close: () => void
  toggle: () => void
  /** A question goes out: it is added as `asking`, and its id returned. */
  begin: (question: string, context: ChatContextDTO) => number
  answer: (id: number, response: ChatResponseDTO) => void
  fail: (id: number, error: unknown) => void
  /** A question taken back (cancelled) leaves no trace. */
  drop: (id: number) => void
  /** Start over: the conversation is forgotten. */
  clear: () => void
}

export const useAsk = create<AskState>((set) => ({
  isOpen: false,
  text: null,
  textId: 0,
  turns: [],
  nextId: 1,
  open: (text) =>
    set((s) => {
      const t = text?.trim()
      return t ? { isOpen: true, text: t, textId: s.textId + 1 } : { isOpen: true }
    }),
  close: () => set({ isOpen: false }),
  toggle: () => set((s) => ({ isOpen: !s.isOpen })),
  begin: (question, context) => {
    let id = 0
    set((s) => {
      id = s.nextId
      const turn: AskTurn = { id, question, context, state: 'asking', response: null, error: null }
      return { nextId: s.nextId + 1, turns: [...s.turns, turn] }
    })
    return id
  },
  answer: (id, response) =>
    set((s) => ({ turns: s.turns.map((t) => (t.id === id ? { ...t, state: 'answered', response, error: null } : t)) })),
  fail: (id, error) =>
    set((s) => ({ turns: s.turns.map((t) => (t.id === id ? { ...t, state: 'failed', error } : t)) })),
  drop: (id) => set((s) => ({ turns: s.turns.filter((t) => t.id !== id) })),
  clear: () => set({ turns: [] }),
}))

/** The most messages `POST /agents/chat` takes, the question included. */
export const MAX_MESSAGES = 12
/** The longest message it takes, in characters. */
export const MAX_TEXT = 2000

/** What an answer said, as the next question's history carries it; null when it said nothing. */
export function answerText(r: ChatResponseDTO | null): string | null {
  const a = r?.result?.answer
  return typeof a === 'string' && a.trim() ? a.trim() : null
}

/**
 * The messages for the next question: every question that was answered with
 * words and its answer, oldest first, then the question. At most twelve, and
 * never starting with an answer whose question was cut off. Questions that
 * failed, were cancelled or got no words back are left out, so the API never
 * sees two questions in a row.
 */
export function historyFor(turns: AskTurn[], question: string): ChatMessageDTO[] {
  const clip = (t: string) => t.slice(0, MAX_TEXT)
  const all: ChatMessageDTO[] = []
  for (const t of turns) {
    if (t.state !== 'answered') continue
    const a = answerText(t.response)
    if (!a) continue
    all.push({ role: 'user', text: clip(t.question) }, { role: 'assistant', text: clip(a) })
  }
  all.push({ role: 'user', text: clip(question.trim()) })
  const kept = all.slice(-MAX_MESSAGES)
  return kept[0]?.role === 'assistant' ? kept.slice(1) : kept
}

/** A step's name for the chip, by the id the service uses. */
const STEP_NAMES: Record<string, string> = {
  ready: 'Ready',
  launch: 'Launch',
  trip: 'Trip',
  landing: 'Surface',
  contact: 'Contact',
  return: 'Return',
}

/**
 * What "this" means to the chat, in words for the chip: "About IM-3 · Launch".
 * Null when the page is about nothing in particular.
 */
export function contextWords(ctx: ChatContextDTO, names: { mission?: string | null; site?: string | null } = {}): string | null {
  if (ctx.mission_id) {
    const name = names.mission || ctx.mission_id
    const step = ctx.section ? STEP_NAMES[ctx.section] : null
    return `About ${name}${step ? ` · ${step}` : ''}`
  }
  if (ctx.site_id) return `About ${names.site || ctx.site_id}`
  return null
}

/**
 * Questions to start with, about what is on screen: the step open first, then
 * the mission's other steps, or the site, or the app as a whole. Each is one
 * the chat can answer from the measurements.
 */
export function suggestionsFor(ctx: ChatContextDTO, names: { mission?: string | null; site?: string | null } = {}): string[] {
  const m = ctx.mission_id ? names.mission || ctx.mission_id : null
  if (m) {
    const by: [string, string][] = [
      ['launch', `When can ${m} launch?`],
      ['landing', `How much sunlight does ${m} get on the surface?`],
      ['contact', `When can the Deep Space Network hear ${m}?`],
      ['trip', `What does ${m} go through on the way?`],
    ]
    const first = by.find(([s]) => s === ctx.section)
    return [...(first ? [first] : []), ...by.filter((b) => b !== first)].slice(0, 3).map(([, q]) => q)
  }
  if (ctx.site_id) {
    const s = names.site || ctx.site_id
    return [`How much sunlight does ${s} get?`, `How long is the longest night at ${s}?`, 'What is the space weather now?']
  }
  return ['Which missions land near the south pole?', 'What is the space weather now?', 'Which missions are planned next?']
}

/** The keys a press is judged on: the event's, without the DOM. */
export interface KeyPress {
  key: string
  ctrlKey: boolean
  metaKey: boolean
  altKey: boolean
  shiftKey?: boolean
}

/** Where the press landed: typing in a field, or inside an open modal. */
export interface KeyTarget {
  typing: boolean
  inDialog: boolean
}

/**
 * Whether a key press opens Ask. Ctrl/Cmd+K works anywhere outside a modal,
 * since it is never a character. A bare `/` is a character, so it only counts
 * outside a field, and only while bare-key shortcuts are on (WCAG 2.1.4).
 */
export function isAskShortcut(e: KeyPress, at: KeyTarget, shortcutsOn: boolean): boolean {
  if (at.inDialog) return false
  if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 'k') return true
  if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey) return false
  return shortcutsOn && !at.typing
}

const TYPING = new Set(['INPUT', 'TEXTAREA', 'SELECT'])

/** Opens Ask on `/` or Ctrl/Cmd+K, from anywhere in the shell. */
export function useAskShortcuts() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement
      const at: KeyTarget = {
        typing: Boolean(el && (TYPING.has(el.tagName) || (el as HTMLElement).isContentEditable)),
        inDialog: el instanceof HTMLElement && Boolean(el.closest('dialog[open]')),
      }
      if (!isAskShortcut(e, at, useMission.getState().shortcuts)) return
      e.preventDefault()
      useAsk.getState().open()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
}
