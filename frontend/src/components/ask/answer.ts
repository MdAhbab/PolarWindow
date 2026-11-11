import { ApiError } from '../../lib/api/client'
import type { ChatActionDTO, ChatResponseDTO } from '../../lib/api/experience.types'
import { answerText, type AskTurn } from './store'

/**
 * Reading an Ask answer for the dock: who wrote it, where its links may go,
 * and what a screen reader hears when it arrives. Pure, so it is tested
 * without the DOM.
 */

/**
 * Why an answer was put together by rules instead of written by a model, or
 * null when a model wrote it. `guard`: the model's answer failed the
 * grounding guard and was replaced; `no_model`: no model is set up on the
 * server; `unavailable`: a model is set up but did not answer.
 */
export type RuleReason = 'guard' | 'no_model' | 'unavailable'

export function answeredByRules(r: ChatResponseDTO): RuleReason | null {
  if (r.run_status === 'guard_rejected') return 'guard'
  if ((r.meta as { agents_configured?: unknown } | undefined)?.agents_configured === false) return 'no_model'
  if (r.status === 'degraded') return 'unavailable'
  return null
}

/** The server refused the question because nobody is signed in (or the session ended). */
export function isSignedOut(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401
}

/**
 * An action's link, only when it is a path inside this app ("/missions/im-3/launch").
 * Anything else (another site, `//host`, a script URL) is not shown.
 */
export function inAppHref(a: ChatActionDTO): string | null {
  const h = typeof a.href === 'string' ? a.href.trim() : ''
  return h.startsWith('/') && !h.startsWith('//') && !h.includes('\\') ? h : null
}

/** The links under an answer that can be followed in the app, each once. */
export function answerActions(r: ChatResponseDTO | null): { label: string; href: string }[] {
  const seen = new Set<string>()
  const out: { label: string; href: string }[] = []
  for (const a of r?.result?.actions ?? []) {
    const href = inAppHref(a)
    if (!href || seen.has(href) || !a.label?.trim()) continue
    seen.add(href)
    out.push({ label: a.label.trim(), href })
  }
  return out.slice(0, 3)
}

/** The next questions offered under an answer, without blanks or repeats. */
export function answerFollowUps(r: ChatResponseDTO | null): string[] {
  const out = (r?.result?.follow_ups ?? []).map((f) => (typeof f === 'string' ? f.trim() : '')).filter(Boolean)
  return [...new Set(out)].slice(0, 3)
}

/** What a screen reader is told about the newest question: once while it is worked out, once when it is answered. */
export function announcement(t: AskTurn | undefined): string {
  if (!t) return ''
  if (t.state === 'asking') return 'Working out an answer.'
  if (t.state === 'failed') {
    if (isSignedOut(t.error)) return 'Not answered: sign in to ask.'
    const title = (t.error as { title?: unknown } | null)?.title
    return `Not answered. ${typeof title === 'string' ? title : 'The question did not go through.'}`
  }
  const r = t.response
  if (r?.status === 'insufficient_data') return `Not enough data to answer. ${r.reason ?? ''}`.trim()
  const a = answerText(r)
  const rules = r && answeredByRules(r) ? ' Answered from rules, not a model.' : ''
  return a ? `Answer:${rules} ${a}` : 'The answer came back empty.'
}
