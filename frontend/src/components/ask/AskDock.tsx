import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { LIVE_SERVICE, chatContextFor, homeApi } from '../../lib/api/home'
import type { ChatContextDTO, ChatResponseDTO } from '../../lib/api/experience.types'
import { ApiError } from '../../lib/api/client'
import { useMission as useMissionQuery } from '../../lib/api/queries'
import { useMission } from '../../lib/store'
import { useWindowParams } from '../../lib/mission'
import { hasSite, siteById } from '../../lib/sites'
import { fieldWords, toolWords } from '../../lib/fieldWords'
import { useMotionClass, useReducedMotion } from '../../hooks/useMotion'
import { Icon, type IconName } from '../Icon'
import { Sheet } from '../Sheet'
import { ProgressTrack, UncertaintyNote } from '../States'
import { guardCopy, statusLine } from '../Agents'
import { pillClass } from '../ui'
import { MAX_TEXT, answerText, contextWords, historyFor, suggestionsFor, useAsk, type AskTurn } from './store'
import { announcement, answerActions, answerFollowUps, answeredByRules, isSignedOut, type RuleReason } from './answer'

/** The dock's element on a wide screen, for the shell's Ask button (`aria-controls`). */
export const ASK_DOCK_ID = 'pw-ask-dock'

/** From 1024 px the dock is a panel beside the page; below, a modal sheet. */
const WIDE = '(min-width: 64rem)'

/** Wide unless the screen says otherwise (and where there is no layout to ask, as in tests). */
function useWide(): boolean {
  const [wide, setWide] = useState(() => typeof matchMedia === 'undefined' || matchMedia(WIDE).matches)
  useEffect(() => {
    if (typeof matchMedia === 'undefined') return
    const mq = matchMedia(WIDE)
    const on = () => setWide(mq.matches)
    on()
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  return wide
}

/** What "this" means on the page open now, and the names the chip says it in. */
function usePageContext() {
  const { pathname, search } = useLocation()
  const siteId = useMission((s) => s.siteId)
  const { start, end } = useWindowParams()
  const context = useMemo(
    () => chatContextFor(pathname, search, { siteId, start, end }),
    [pathname, search, siteId, start, end],
  )
  const mission = useMissionQuery(context.mission_id ?? undefined)
  const site = context.site_id ? (hasSite(context.site_id) ? siteById(context.site_id).name : context.site_id) : null
  const names = { mission: mission.data?.name ?? null, site }
  return { context, names, about: contextWords(context, names) }
}

interface Sender {
  /** Sends a question; false when it cannot go now (blank, a saved copy, or one already being answered). */
  ask: (question: string) => boolean
  /** Takes a question back while it is being answered: it leaves no trace. */
  cancel: (id: number) => void
  /** Forgets the conversation, calling off anything still being answered. */
  clear: () => void
}

/**
 * Sending lives with the dock's mount in the shell, not with the panel, so
 * closing the dock or moving to another page while a question is answered
 * still brings the answer into the conversation.
 */
function useAskSender(context: ChatContextDTO, about: string | null): Sender {
  const controllers = useRef(new Map<number, AbortController>())
  const page = useRef({ context, about })
  useEffect(() => {
    page.current = { context, about }
  }, [context, about])

  const ask = useCallback((question: string) => {
    const q = question.trim().slice(0, MAX_TEXT)
    const store = useAsk.getState()
    if (!q || !LIVE_SERVICE || store.turns.some((t) => t.state === 'asking')) return false
    const { context: ctx, about: words } = page.current
    const messages = historyFor(store.turns, q)
    const id = store.begin(q, ctx, words)
    const ac = new AbortController()
    controllers.current.set(id, ac)
    homeApi
      .chat({ messages, context: ctx }, ac.signal)
      .then(
        (r) => {
          if (!ac.signal.aborted) useAsk.getState().answer(id, r)
        },
        (e: unknown) => {
          if (!ac.signal.aborted) useAsk.getState().fail(id, e)
        },
      )
      .finally(() => controllers.current.delete(id))
    return true
  }, [])

  const cancel = useCallback((id: number) => {
    controllers.current.get(id)?.abort()
    controllers.current.delete(id)
    useAsk.getState().drop(id)
  }, [])

  const clear = useCallback(() => {
    controllers.current.forEach((c) => c.abort())
    controllers.current.clear()
    useAsk.getState().clear()
  }, [])

  return useMemo(() => ({ ask, cancel, clear }), [ask, cancel, clear])
}

/**
 * Ask (docs/experience-plan.md, stream C): a short answer about whatever is
 * on screen, grounded and checked like every AI answer in the app. Mounted
 * once in the shell. From 1024 px a panel at the right edge that leaves the
 * page usable beside it (the page makes room); on a phone a modal sheet.
 *
 * The input has focus when it opens, Esc closes it, and focus goes back to
 * whatever opened it. Words sent from elsewhere (Home's Ask bar, a chip) are
 * asked as they arrive.
 */
export function AskDock() {
  const isOpen = useAsk((s) => s.isOpen)
  const close = useAsk((s) => s.close)
  const text = useAsk((s) => s.text)
  const textId = useAsk((s) => s.textId)
  const wide = useWide()
  const { context, names, about } = usePageContext()
  const sender = useAskSender(context, about)
  const [draft, setDraft] = useState('')

  const handled = useRef(textId)
  useEffect(() => {
    if (textId === handled.current) return
    handled.current = textId
    // One question at a time: words that cannot go yet wait in the field.
    if (text && !sender.ask(text)) setDraft(text)
  }, [text, textId, sender])

  const body = (
    <DockBody
      open={isOpen}
      about={about}
      scenario={Boolean(context.scenario_id)}
      suggestions={suggestionsFor(context, names)}
      draft={draft}
      setDraft={setDraft}
      sender={sender}
      // A link followed from the modal sheet closes it; the panel stays open beside the page.
      onLeave={wide ? undefined : close}
    />
  )
  if (wide) return isOpen ? <DockPanel onClose={close}>{body}</DockPanel> : null
  return (
    <Sheet open={isOpen} onClose={close} title="Ask">
      {body}
    </Sheet>
  )
}

/** The panel at the right edge, below the island, clear of the guide card. Not modal: the page stays in reach. */
function DockPanel({ onClose, children }: { onClose: () => void; children: ReactNode }) {
  const titleId = useId()
  const slide = useMotionClass('pw-dock-in')
  // Whatever had focus as it opened: the Ask button, the field on Home, a link on the page.
  const [opener] = useState(() =>
    typeof document !== 'undefined' && document.activeElement instanceof HTMLElement ? document.activeElement : null,
  )
  useEffect(
    () => () => {
      // Closed with focus inside it (Esc, the close button): focus would fall to
      // the page's top, so it goes back to the opener. Closed from the Ask
      // button, focus is already there.
      const a = document.activeElement
      if ((!a || a === document.body) && opener && document.contains(opener)) opener.focus()
    },
    [opener],
  )
  return (
    <aside
      id={ASK_DOCK_ID}
      aria-labelledby={titleId}
      onKeyDown={(e) => {
        if (e.key !== 'Escape' || e.defaultPrevented) return
        e.preventDefault()
        onClose()
      }}
      className={`pw-on-raised fixed top-[5.25rem] right-3 bottom-[calc(0.75rem+var(--pw-guide-h,0px))] z-30 flex w-[24rem] flex-col overflow-hidden rounded-sheet border border-line-strong bg-raised text-ink shadow-overlay ${slide}`}
    >
      <div className="flex shrink-0 items-center gap-3 border-b border-line py-2.5 pr-2.5 pl-5">
        <h2 id={titleId} className="grow text-title-lg font-semibold tracking-title">
          Ask
        </h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close Ask"
          title="Close (Esc)"
          className="pw-press inline-flex size-12 items-center justify-center rounded-pill border border-line-strong bg-tray text-ink hover:border-ink-3 hover:bg-inset"
        >
          <Icon name="close" size={18} strokeWidth={1.8} />
        </button>
      </div>
      {children}
    </aside>
  )
}

function DockBody({
  open,
  about,
  scenario,
  suggestions,
  draft,
  setDraft,
  sender,
  onLeave,
}: {
  open: boolean
  about: string | null
  scenario: boolean
  suggestions: string[]
  draft: string
  setDraft: (v: string) => void
  sender: Sender
  onLeave?: () => void
}) {
  const turns = useAsk((s) => s.turns)
  const busy = turns.some((t) => t.state === 'asking')
  const field = useRef<HTMLTextAreaElement>(null)
  const scroller = useRef<HTMLDivElement>(null)
  const reduced = useReducedMotion()
  const fieldId = useId()
  const hintId = useId()

  // The field has focus once the dock is open (after the sheet has put it on its close button).
  useEffect(() => {
    if (!open || !LIVE_SERVICE || typeof requestAnimationFrame === 'undefined') return
    const raf = requestAnimationFrame(() => field.current?.focus())
    return () => cancelAnimationFrame(raf)
  }, [open])

  // Opened on a conversation, it shows the newest; a new question scrolls to its top.
  useLayoutEffect(() => {
    const el = scroller.current
    if (el) el.scrollTop = el.scrollHeight
  }, [])
  const count = turns.length
  const before = useRef(count)
  useEffect(() => {
    const grew = count > before.current
    before.current = count
    const el = scroller.current
    const last = el?.querySelector<HTMLElement>('[data-turn]:last-child')
    if (!grew || !el || !last || typeof el.scrollTo !== 'function') return
    const top = last.getBoundingClientRect().top - el.getBoundingClientRect().top + el.scrollTop - 16
    el.scrollTo({ top, behavior: reduced ? 'auto' : 'smooth' })
  }, [count, reduced])

  const submit = (q: string) => {
    if (sender.ask(q)) setDraft('')
  }
  const startOver = () => {
    sender.clear()
    setDraft('')
    field.current?.focus()
  }

  return (
    <div className="flex h-full min-h-0 grow flex-col">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-x-3 gap-y-2 px-5 pt-3">
        <ContextChip about={about} scenario={scenario} />
        {turns.length > 0 && (
          <button
            type="button"
            onClick={startOver}
            className="pw-press -mr-2 inline-flex h-11 items-center gap-1.5 rounded-pill px-3 text-small font-semibold text-ink-2 hover:bg-inset hover:text-ink"
          >
            <Icon name="undo" size={15} strokeWidth={2} />
            Start over
          </button>
        )}
      </div>

      <div ref={scroller} className="relative min-h-0 grow overflow-y-auto px-5 pt-5 pb-6">
        {!LIVE_SERVICE ? (
          <SavedCopy />
        ) : turns.length === 0 ? (
          <Start suggestions={suggestions} onPick={submit} />
        ) : (
          <ol className="flex flex-col">
            {turns.map((t, i) => (
              <TurnItem
                key={t.id}
                turn={t}
                last={i === turns.length - 1}
                showAbout={i === 0 ? t.about !== about : t.about !== turns[i - 1].about}
                busy={busy}
                onAsk={submit}
                onCancel={() => {
                  sender.cancel(t.id)
                  if (!draft.trim()) setDraft(t.question)
                  field.current?.focus()
                }}
                onRetry={() => {
                  sender.cancel(t.id)
                  sender.ask(t.question)
                }}
                onLeave={onLeave}
              />
            ))}
          </ol>
        )}
      </div>

      {/* Said once when a question goes out and once when its answer is in. */}
      <p role="status" className="sr-only">
        {announcement(turns[turns.length - 1])}
      </p>

      {LIVE_SERVICE && (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            submit(draft)
          }}
          className="shrink-0 border-t border-line px-4 pt-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))]"
        >
          <label htmlFor={fieldId} className="sr-only">
            Your question
          </label>
          <div className="flex items-end gap-2 rounded-card border border-field bg-panel py-1.5 pr-1.5 pl-3.5 has-[textarea:focus-visible]:outline-2 has-[textarea:focus-visible]:outline-offset-2 has-[textarea:focus-visible]:outline-focus">
            <textarea
              id={fieldId}
              ref={field}
              rows={1}
              maxLength={MAX_TEXT}
              value={draft}
              aria-describedby={hintId}
              placeholder={about ? 'Ask about this page' : 'Ask about a mission, a site or a date'}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                // Enter asks; Shift+Enter is a new line, as in every chat box.
                if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault()
                  submit(draft)
                }
              }}
              className="field-sizing-content max-h-40 min-h-11 grow resize-none bg-transparent py-2.5 text-body leading-6 text-ink outline-none placeholder:text-ink-3"
            />
            <button
              type="submit"
              disabled={busy || !draft.trim()}
              className="pw-press inline-flex h-11 shrink-0 items-center rounded-pill bg-ink px-4 text-body font-semibold text-canvas hover:bg-ink-2 disabled:bg-inset disabled:text-ink-3"
            >
              Ask
            </button>
          </div>
          <p id={hintId} className="pt-2 pl-1 text-caption leading-caption text-ink-3">
            {busy
              ? 'One question at a time: the next goes once this answer is in.'
              : 'Enter asks. Shift+Enter starts a new line.'}
          </p>
        </form>
      )}
    </div>
  )
}

/**
 * What "this" means to the answer: the mission and step, or the site, open
 * now. A scenario being read wears the scenario's own dashed edge and hatch,
 * never a hue.
 */
function ContextChip({ about, scenario }: { about: string | null; scenario: boolean }) {
  const words = `${about ?? 'About any mission or site'}${scenario ? ', in the scenario open' : ''}`
  return (
    <p
      title={words}
      className={`inline-flex min-h-8 max-w-full min-w-0 items-center gap-1.5 rounded-pill border px-3 py-1 text-small leading-5 text-ink-2 ${
        scenario ? 'pw-scenario' : 'border-line-strong bg-tray'
      }`}
    >
      <Icon name={about ? 'pin' : 'moon'} size={13} strokeWidth={2} className="shrink-0 text-ink-3" />
      <span className="min-w-0 truncate">{words}</span>
    </p>
  )
}

function SavedCopy() {
  return (
    <div className="flex items-start gap-3">
      <Icon name="offline" size={20} strokeWidth={1.8} className="mt-0.5 shrink-0 text-ink-2" />
      <div className="flex min-w-0 flex-col gap-1">
        <p className="text-control font-semibold text-ink">This is a saved copy</p>
        <p className="text-body leading-6 text-ink-2">
          Ask needs the live service, so a saved copy sends no questions. Every page here still shows the
          answers saved with it.
        </p>
      </div>
    </div>
  )
}

function Start({ suggestions, onPick }: { suggestions: string[]; onPick: (q: string) => void }) {
  const id = useId()
  return (
    <div className="flex flex-col gap-6">
      <p className="text-body leading-6 text-ink-2">
        Ask about what is on screen, or any mission or site. The answer comes from the same measurements as the
        pages, and every number in it is checked against them.
      </p>
      {suggestions.length > 0 && (
        <div className="flex flex-col gap-2.5">
          <h3 id={id} className="text-small font-semibold text-ink">
            Questions to start with
          </h3>
          <ul aria-labelledby={id} className="flex flex-col items-start gap-2">
            {suggestions.map((s) => (
              <li key={s} className="max-w-full">
                <button
                  type="button"
                  onClick={() => onPick(s)}
                  className="pw-press inline-flex min-h-11 max-w-full items-center rounded-pill border border-line-strong bg-tray px-4 py-2 text-left text-body leading-5 text-ink-2 hover:bg-inset hover:text-ink"
                >
                  {s}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

/** A question's mark on the conversation's line: the journey's shapes, with the words always beside it. */
function markOf(t: AskTurn): { icon: IconName; look: string } {
  if (t.state === 'asking') return { icon: 'quarter', look: 'border-2 border-ink bg-raised text-ink' }
  if (t.state === 'failed') return { icon: 'alert', look: 'border-2 border-alert bg-raised text-alert' }
  if (t.response?.status === 'insufficient_data') return { icon: 'ring', look: 'border-2 border-ink bg-raised text-ink' }
  return { icon: 'dot', look: 'bg-ink text-canvas' }
}

/**
 * One question and what came back. The questions sit on one line, as the
 * steps sit on the mission's path: each mark says where its question stands
 * (being answered, answered, not answered) by shape, and the words under it
 * say it again.
 */
function TurnItem({
  turn,
  last,
  showAbout,
  busy,
  onAsk,
  onCancel,
  onRetry,
  onLeave,
}: {
  turn: AskTurn
  last: boolean
  showAbout: boolean
  busy: boolean
  onAsk: (q: string) => void
  onCancel: () => void
  onRetry: () => void
  onLeave?: () => void
}) {
  // Asked while this was on screen: its answer arrives, once. Reopened later, it is simply there.
  const [live] = useState(turn.state === 'asking')
  const arrive = useMotionClass('pw-arrive')
  const mark = markOf(turn)
  return (
    <li data-turn className={`relative grid grid-cols-[1.75rem_minmax(0,1fr)] gap-x-3 ${last ? '' : 'pb-8'}`}>
      {!last && <span aria-hidden="true" className="absolute top-8 bottom-1 left-[13px] w-0.5 bg-line-strong" />}
      <span
        aria-hidden="true"
        className={`relative z-[1] flex size-7 items-center justify-center rounded-pill shadow-[0_0_0_4px_var(--color-raised)] ${mark.look}`}
      >
        <Icon name={mark.icon} size={14} strokeWidth={2.2} />
      </span>
      <div className="flex min-w-0 flex-col gap-3">
        <div className="flex flex-col gap-0.5 pt-0.5">
          {showAbout && turn.about && <p className="text-caption leading-caption text-ink-3">{turn.about}</p>}
          <h3 className="text-control leading-6 font-semibold break-words text-ink">{turn.question}</h3>
        </div>
        {turn.state === 'asking' ? (
          <div className="flex flex-col gap-2.5">
            <p className="text-small leading-5 text-ink-2">Working it out. Every number is checked against the measurements.</p>
            <ProgressTrack label="Working out an answer" fraction={null} />
            <button
              type="button"
              onClick={onCancel}
              className="pw-press -ml-3 inline-flex h-11 items-center self-start rounded-pill px-3 text-small font-semibold text-ink-2 hover:bg-inset hover:text-ink"
            >
              Cancel<span className="sr-only">: {turn.question}</span>
            </button>
          </div>
        ) : (
          <div className={`flex min-w-0 flex-col gap-3.5 ${live ? arrive : ''}`}>
            {turn.state === 'failed' ? (
              <NotAnswered error={turn.error} onRetry={onRetry} onLeave={onLeave} />
            ) : turn.response ? (
              <Answer r={turn.response} busy={busy} onAsk={onAsk} onLeave={onLeave} />
            ) : null}
          </div>
        )}
      </div>
    </li>
  )
}

/** The question did not go through: nobody signed in, or the service said why. */
function NotAnswered({ error, onRetry, onLeave }: { error: unknown; onRetry: () => void; onLeave?: () => void }) {
  if (isSignedOut(error)) {
    return (
      <div className="flex flex-col items-start gap-2.5">
        <p className="text-body font-semibold text-ink">Sign in to ask</p>
        <p className="text-small leading-5 text-ink-2">
          Answers are written by the AI, which needs you signed in. Sign in on the front page, then ask again.
        </p>
        <Link to="/" onClick={onLeave} className={pillClass('secondary')}>
          Go to sign-in
        </Link>
      </div>
    )
  }
  const e = error instanceof ApiError ? error : null
  const title = e?.title ?? 'The question did not go through'
  const detail = e ? e.detail : String((error as Error)?.message ?? '')
  const retry = e ? e.retryable || e.status === 0 : true
  return (
    <div className="flex flex-col items-start gap-2.5">
      <p className="flex items-start gap-2 text-body font-semibold text-ink">
        <Icon name="alert" size={16} strokeWidth={2.2} className="mt-0.5 shrink-0 text-alert" />
        {title}
      </p>
      {detail && <p className="text-small leading-5 text-ink-2">{detail}</p>}
      {e?.problem && e.stillWorks && <p className="text-small leading-5 text-ink-3">{e.stillWorks}</p>}
      {retry && (
        <button
          type="button"
          onClick={onRetry}
          className="pw-press inline-flex h-11 items-center rounded-pill border border-line-strong bg-tray px-4 text-small font-semibold text-ink hover:border-ink-3 hover:bg-inset"
        >
          Ask again
        </button>
      )}
    </div>
  )
}

const RULES_COPY: Record<Exclude<RuleReason, 'guard'>, string> = {
  no_model:
    'No AI model is set up on this server, so this was put together from the measurements by fixed rules. Every number in it still comes from them.',
  unavailable:
    'The AI did not answer, so this was put together from the measurements by fixed rules. Every number in it still comes from them.',
}

function Answer({
  r,
  busy,
  onAsk,
  onLeave,
}: {
  r: ChatResponseDTO
  busy: boolean
  onAsk: (q: string) => void
  onLeave?: () => void
}) {
  const rules = answeredByRules(r)
  const actions = answerActions(r)
  const followUps = answerFollowUps(r)
  const words = answerText(r)
  return (
    <>
      {rules && (
        <UncertaintyNote title="Answered from rules, not a model">
          {rules === 'guard' ? guardCopy(r.guard_failures) : RULES_COPY[rules]}
        </UncertaintyNote>
      )}
      {r.status === 'insufficient_data' ? (
        <div className="flex flex-col gap-1">
          <p className="text-body font-semibold text-ink">Not enough data to answer</p>
          {r.reason && <p className="text-small leading-5 text-ink-2">{r.reason}</p>}
        </div>
      ) : (
        <p className="text-body leading-6 break-words whitespace-pre-line text-ink">
          {words ?? r.reason ?? 'The answer came back empty.'}
        </p>
      )}
      {actions.length > 0 && (
        <ul aria-label="Where the full answer is" className="-my-1 flex flex-col">
          {actions.map((a) => (
            <li key={a.href}>
              <Link
                to={a.href}
                onClick={onLeave}
                className="group inline-flex min-h-11 items-center gap-2 text-body font-semibold text-ink no-underline"
              >
                <Icon name="arrow" size={15} strokeWidth={2} className="shrink-0 text-ink-3 group-hover:text-ink" />
                {/* The space between the two is said, never drawn (a flex row drops it). */}
                <span className="sr-only">Open</span>{' '}
                <span className="underline decoration-line-strong underline-offset-4 group-hover:decoration-ink">
                  {a.label}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      {followUps.length > 0 && (
        <ul aria-label="Questions to ask next" className="flex flex-wrap gap-2">
          {followUps.map((f) => (
            <li key={f} className="max-w-full">
              <button
                type="button"
                disabled={busy}
                onClick={() => onAsk(f)}
                className="pw-press inline-flex min-h-11 max-w-full items-center rounded-pill border border-line-strong bg-tray px-3.5 py-2 text-left text-small leading-5 text-ink-2 hover:bg-inset hover:text-ink disabled:cursor-not-allowed disabled:opacity-60"
              >
                {f}
              </button>
            </li>
          ))}
        </ul>
      )}
      <HowItGotThis r={r} />
    </>
  )
}

/** A number from the API, printed as sent: no rounding, no unit conversion. */
const asSent = (v: unknown): string => (typeof v === 'number' ? String(v) : String(v ?? ''))

/**
 * On every answer: who wrote it and how long it took (or that rules did),
 * how the question was read, each number with the sentence it is in and the
 * lookup it came from, what was looked up, and the run itself in the log.
 */
function HowItGotThis({ r }: { r: ChatResponseDTO }) {
  const openRunLog = useMission((s) => s.openRunLog)
  const numbers = r.provenance ?? []
  const calls = r.tool_calls ?? []
  const read = r.result?.interpreted_as?.trim()
  return (
    <details className="group border-t border-line">
      <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between gap-3 py-1.5 hover:text-ink [&::-webkit-details-marker]:hidden">
        <span className="flex min-w-0 flex-col">
          <span className="text-small font-semibold text-ink">How the AI got this</span>
          <span className="text-caption leading-caption text-ink-3">{statusLine({ ...r, result: null })}</span>
        </span>
        <Icon
          name="chevron"
          size={16}
          strokeWidth={2}
          className="shrink-0 text-ink-3 transition-transform duration-[var(--pw-dur-base)] group-open:rotate-180"
        />
      </summary>
      <div className="pw-disclosure-body flex flex-col gap-4 pt-1 pb-2">
        {read && (
          <p className="text-small leading-5 text-ink-2">
            <span className="font-semibold text-ink">Read as: </span>
            {read}
          </p>
        )}
        <div className="flex flex-col gap-2">
          <h4 className="text-small font-semibold text-ink">Numbers used</h4>
          {numbers.length ? (
            <ul className="flex flex-col gap-2.5">
              {numbers.map((p, i) => (
                <li key={i} className="flex flex-col gap-0.5 border-l-2 border-line-strong pl-2.5">
                  <span className="font-mono text-small text-ink tnum">{asSent(p.value)}</span>
                  <span className="text-caption leading-caption text-ink-2">…{p.claim}…</span>
                  <span className="text-caption leading-caption text-ink-3">
                    From {toolWords(p.tool)}, {fieldWords(p.field)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-small text-ink-2">This answer contains no numbers.</p>
          )}
        </div>
        {calls.length > 0 && (
          <div className="flex flex-col gap-2">
            <h4 className="text-small font-semibold text-ink">Looked up</h4>
            <ul className="flex flex-col gap-1">
              {calls.map((c) => (
                <li key={c.seq} className="text-caption leading-caption text-ink-2">
                  {toolWords(c.tool)}
                  {c.error ? ': did not answer' : `, ${c.number_count} ${c.number_count === 1 ? 'number' : 'numbers'}`}
                </li>
              ))}
            </ul>
          </div>
        )}
        {r.run_id && (
          <button
            type="button"
            onClick={(e) => {
              // Focus the opener first: Safari does not focus a clicked button, and
              // the drawer returns focus to whatever had it when it opened.
              e.currentTarget.focus()
              openRunLog(r.run_id ?? null)
            }}
            className="pw-press -ml-3 inline-flex h-11 items-center gap-2 self-start rounded-pill px-3 text-small font-semibold text-ink-2 hover:bg-inset hover:text-ink"
          >
            <Icon name="log" size={16} strokeWidth={1.8} />
            Open this run in the log
          </button>
        )}
      </div>
    </details>
  )
}
