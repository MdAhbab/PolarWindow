import { useEffect, useId, useRef, useState, type ReactNode, type Ref } from 'react'
import { useNavigate } from 'react-router-dom'
import type { AgentDTO, ProvenanceItemDTO } from '../lib/api/client'
import { useAgent, type AgentKind } from '../lib/api/queries'
import { useMission } from '../lib/store'
import { hasSite, siteById } from '../lib/sites'
import { Button, Disclosure, Panel, ScrollRegion, SectionLabel } from './ui'
import { Icon } from './Icon'
import { fieldWords, toolWords, verdictWord } from '../lib/fieldWords'
import { ProblemPanel, UncertaintyNote } from './States'

/**
 * The product's own agents (A1–A4), and the one card they all answer in.
 *
 * Rules the card enforces, each from handoff §10.5:
 *  - The body is the validated structured output rendered as *text*. React
 *    escapes it; nothing here uses innerHTML.
 *  - Numbers are printed exactly as the API sent them. Reformatting a number
 *    (rounding 437647.8 s to "122 h") would create one that is not in
 *    "Numbers used", and the grounding guard exists to prevent exactly that.
 *  - Every state is a real state: loading says what is being checked and can
 *    be cancelled, "not enough data" is not a partial answer, and a degraded
 *    or guard-replaced answer says so before it says anything else.
 */

/** What the card reads from any agent's mutation, whatever its request type. */
interface Agent {
  isIdle: boolean
  isPending: boolean
  isError: boolean
  error: unknown
  data?: AgentDTO
  cancel: () => void
}

const GUARD_COPY =
  "The AI's answer included a number we couldn't trace to a measurement, so we replaced it with a summary built from the measurements."

/**
 * Why the answer was replaced, from the guards that fired: a number that
 * could not be traced, a verdict word ("safe", "go"), or both.
 */
export function guardCopy(failures: AgentDTO['guard_failures']): string {
  const kinds = (failures ?? []).map((g) => g.kind)
  const verdict = (failures ?? []).find((g) => g.kind === 'verdict_word')
  if (!verdict) return GUARD_COPY
  const w = verdictWord(typeof verdict.detail === 'string' ? verdict.detail : null)
  const judged = `judged the whole${w ? ` (“${w}”)` : ''} instead of saying what each number shows`
  const number = kinds.some((k) => typeof k === 'string' && k.startsWith('ungrounded'))
  return `The AI's answer ${number ? `included a number we couldn't trace to a measurement and ${judged}` : judged}, so we replaced it with a summary built from the measurements. The decision is yours.`
}
const DEGRADED_COPY = "The AI didn't respond, so this summary was built directly from the measurements."
const NO_MODEL_COPY =
  'No AI model is set up on this server, so this summary was built directly from the measurements. Every number in it still comes from those measurements.'

/** The server says no model key is configured (`meta.agents_configured`). */
const notConfigured = (r: AgentDTO): boolean =>
  (r.meta as { agents_configured?: unknown } | undefined)?.agents_configured === false

function modelOf(r: AgentDTO): string {
  const m = (r.meta as { model?: unknown } | undefined)?.model
  return typeof m === 'string' && m ? m : 'model not reported'
}

/** Who wrote the answer, shown with the numbers it used. */
export function statusLine(r: AgentDTO): string {
  if (r.status === 'ok') return `AI answer · ${modelOf(r)} · ${(r.latency_ms / 1000).toFixed(1)} s`
  if (r.status === 'insufficient_data') return `AI answer · ${modelOf(r)} · not enough data`
  if (r.run_status === 'guard_rejected') return 'Summary from measurements (AI answer replaced)'
  return 'Summary from measurements (no AI)'
}

const str = (v: unknown): string | null => (typeof v === 'string' && v.trim() ? v : null)
const siteName = (id: unknown): string =>
  typeof id === 'string' ? (hasSite(id) ? siteById(id).name : id) : String(id)

/** A number from the API, printed as sent: no rounding, no unit conversion. */
const asSent = (v: unknown): string => (typeof v === 'number' ? String(v) : String(v ?? ''))

function ExplainBody({ result }: { result: Record<string, unknown> }) {
  const p = str(result.paragraph)
  return p ? <p className="max-w-[68ch] text-control leading-6 text-ink">{p}</p> : null
}

function AskBody({ result }: { result: Record<string, unknown> }) {
  const answer = str(result.answer)
  const read = str(result.interpreted_as)
  const rows = Array.isArray(result.rows) ? (result.rows as { site_id: string; values?: Record<string, number> }[]) : []
  if (!answer && rows.length === 0) {
    // Nothing was looked up (the question needs the model to become tool
    // calls), so say that, rather than "this lists the measurements" over an
    // empty list.
    return (
      <p className="max-w-[68ch] text-control leading-6 text-ink">
        Without the AI, a question in your own words can’t be turned into measurements, so nothing was looked
        up and no number is claimed. The mission list, its filters and each mission’s page answer the same
        questions directly.
      </p>
    )
  }
  return (
    <div className="flex flex-col gap-3">
      {answer && <p className="max-w-[68ch] text-control leading-6 text-ink">{answer}</p>}
      {read && (
        <p className="text-small leading-5 text-ink-2">
          <span className="font-semibold text-ink">Read as: </span>
          {read}
        </p>
      )}
      {rows.length > 0 && (
        <ul className="flex flex-col gap-1.5">
          {rows.map((row, i) => (
            <li key={`${row.site_id}-${i}`} className="text-small leading-5 text-ink">
              <span className="font-semibold">{siteName(row.site_id)}</span>
              {row.values && Object.keys(row.values).length > 0 && (
                <span className="font-mono text-caption text-ink-2">
                  {' '}
                  {Object.entries(row.values)
                    .map(([k, v]) => `${fieldWords(k)} ${asSent(v)}`)
                    .join(' · ')}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

interface Check {
  requirement: string
  satisfied: boolean
  observed_value?: number | null
  observed_units?: string | null
  note?: string | null
}
interface Ranked {
  site_id: string
  rank: number
  satisfies_all: boolean
  checks: Check[]
  why: string
}

function AdviseBody({ result }: { result: Record<string, unknown> }) {
  const summary = str(result.requirement_summary)
  const none = str(result.nothing_satisfies_message)
  const ranked = Array.isArray(result.ranked) ? (result.ranked as Ranked[]) : []
  return (
    <div className="flex flex-col gap-3">
      {summary && (
        <p className="text-small leading-5 text-ink-2">
          <span className="font-semibold text-ink">Requirement read as: </span>
          {summary}
        </p>
      )}
      {result.any_satisfies !== true && none && (
        <p className="max-w-[68ch] text-control leading-6 text-ink">{none}</p>
      )}
      {ranked.length > 0 && (
        <ol className="flex flex-col gap-3">
          {ranked.map((r) => (
            <li key={r.site_id} className="flex flex-col gap-1 border-t border-line pt-3">
              <span className="text-body font-semibold text-ink">
                {asSent(r.rank)}. {siteName(r.site_id)} ·{' '}
                {r.satisfies_all ? 'meets every part' : 'does not meet every part'}
              </span>
              <span className="text-small leading-5 text-ink-2">{r.why}</span>
              {r.checks?.length > 0 && (
                <ul className="flex flex-col gap-0.5">
                  {r.checks.map((c, i) => (
                    <li key={i} className="text-caption leading-caption text-ink-2">
                      {c.satisfied ? 'Met' : 'Not met'}: {c.requirement}
                      {c.observed_value !== null && c.observed_value !== undefined && (
                        <span className="font-mono">
                          {' '}
                          (observed {asSent(c.observed_value)}
                          {c.observed_units ? ` ${c.observed_units}` : ''})
                        </span>
                      )}
                      {c.note ? `. ${c.note}` : ''}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

interface Doc {
  title: string
  body: string
  caveat: string
}

/**
 * Brief (A3): the memo. The service writes it together with two other
 * versions for other readers; one stakeholder reads this one.
 */
function BriefBody({ result }: { result: Record<string, unknown> }) {
  const d = (result.planner_memo as Doc) ?? null
  if (!d) return <p className="text-small text-ink-2">The memo was not written.</p>
  return (
    <div className="flex max-w-[72ch] flex-col gap-2">
      <div className="text-control font-semibold text-ink">{d.title}</div>
      <p className="text-body leading-6 text-ink">{d.body}</p>
      {d.caveat && <p className="text-caption leading-caption text-ink-3">Caveat: {d.caveat}</p>}
    </div>
  )
}

function ResultBody({ kind, result }: { kind: AgentKind; result: Record<string, unknown> }) {
  switch (kind) {
    case 'explain':
      return <ExplainBody result={result} />
    case 'ask':
      return <AskBody result={result} />
    case 'advise':
      return <AdviseBody result={result} />
    case 'brief':
      return <BriefBody result={result} />
  }
}

/** "Numbers used": each claim, the value, and the tool call and field it came from. */
function NumbersUsed({ items }: { items: ProvenanceItemDTO[] }) {
  if (!items.length) {
    return (
      <div className="flex flex-col gap-1.5">
        <SectionLabel as="h3">Numbers used</SectionLabel>
        <p className="text-small text-ink-2">This answer contains no numbers.</p>
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-2">
      <SectionLabel as="h3">Numbers used</SectionLabel>
      <ScrollRegion label="Numbers used, scrolls sideways" className="border border-line">
        <table className="w-full min-w-[520px] border-collapse text-left">
          <caption className="sr-only">
            Every number in the answer, the sentence it appears in, and the tool call and field it was
            checked against.
          </caption>
          <thead>
            <tr className="bg-inset">
              {['Claim', 'Value', 'From'].map((h) => (
                <th
                  key={h}
                  scope="col"
                  className="px-3 py-2 text-tag font-semibold tracking-caps-md text-ink-3 uppercase"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map((p, i) => (
              <tr key={i} className="border-t border-line align-top">
                <td className="px-3 py-2 text-caption leading-caption text-ink-2">…{p.claim}…</td>
                <td className="px-3 py-2 font-mono text-caption text-ink tnum">{asSent(p.value)}</td>
                <td className="px-3 py-2 font-mono text-caption text-ink-2">
                  {toolWords(p.tool)} · {fieldWords(p.field)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </ScrollRegion>
    </div>
  )
}

/**
 * The shared response card (§10.5), for every agent and every state.
 */
export function AgentCard({
  kind,
  agent,
  onRephrase,
  onRetry,
}: {
  kind: AgentKind
  agent: Agent
  /** Where "Rephrase" sends focus; omitted for agents with no free-text input. */
  onRephrase?: () => void
  onRetry?: () => void
}) {
  const navigate = useNavigate()
  const openRunLog = useMission((s) => s.openRunLog)

  if (agent.isIdle) return null

  if (agent.isPending) {
    return (
      <Panel className="flex flex-wrap items-center justify-between gap-3 p-4">
        <p role="status" className="text-small text-ink-3">
          Writing… every number is checked against the measurements
        </p>
        <Button onClick={agent.cancel}>Cancel</Button>
      </Panel>
    )
  }

  if (agent.isError) {
    return <ProblemPanel error={agent.error} fallbackTitle="The request did not complete" onRetry={onRetry} />
  }

  const r = agent.data
  if (!r) return null

  const howButton = r.run_id ? (
    <Button
      variant="ghost"
      onClick={(e) => {
        // Focus the opener first: Safari does not focus a clicked button, and
        // the drawer returns focus to whatever had it when it opened.
        e.currentTarget.focus()
        openRunLog(r.run_id ?? null)
      }}
      className="self-start"
    >
      <Icon name="log" size={16} strokeWidth={1.8} />
      How the AI got this
    </Button>
  ) : null

  if (r.status === 'insufficient_data') {
    return (
      <Panel className="flex flex-col gap-4 p-5" as="section">
        <div className="flex flex-col gap-2">
          <div className="text-title-lg font-semibold text-ink">Not enough data to answer</div>
          <p className="max-w-[60ch] text-body leading-6 text-ink-2">{r.reason ?? ''}</p>
        </div>
        <div className="flex flex-wrap gap-3">
          {onRephrase && (
            <Button variant="primary" onClick={onRephrase}>
              Rephrase
            </Button>
          )}
          <Button onClick={() => navigate('/missions')}>Browse missions</Button>
          {howButton}
        </div>
      </Panel>
    )
  }

  const result = r.result ?? null
  const replaced = r.status === 'degraded'
  return (
    <Panel className="flex flex-col gap-4 p-5" as="section">
      {replaced && (
        <UncertaintyNote title="Built from the measurements" hatchKey={false}>
          {r.run_status === 'guard_rejected'
            ? guardCopy(r.guard_failures)
            : notConfigured(r)
              ? NO_MODEL_COPY
              : DEGRADED_COPY}
          {r.reason && r.run_status !== 'guard_rejected' && !notConfigured(r) ? (
            <span className="mt-1 block text-ink-3">{r.reason}</span>
          ) : null}
        </UncertaintyNote>
      )}
      {result ? (
        <ResultBody kind={kind} result={result} />
      ) : (
        <p className="text-body text-ink-2">{r.reason ?? 'No summary could be built for this request.'}</p>
      )}
      <details className="group border-t border-line pt-3">
        <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 text-small text-ink-2 hover:text-ink [&::-webkit-details-marker]:hidden">
          <span>
            {statusLine(r)} · {(r.provenance ?? []).length} numbers, each checked against the measurements
          </span>
          <Icon name="chevron" size={16} strokeWidth={2} className="shrink-0 text-ink-3 transition-transform group-open:rotate-180" />
        </summary>
        <div className="flex flex-col gap-3 pt-2">
          <NumbersUsed items={r.provenance ?? []} />
          {howButton}
        </div>
      </details>
    </Panel>
  )
}

/** A textarea styled like `SearchField`: same border, height floor and focus ring. */
function PromptField({
  id,
  label,
  value,
  onChange,
  placeholder,
  fieldRef,
  onSubmit,
}: {
  id: string
  label: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  fieldRef?: Ref<HTMLTextAreaElement>
  onSubmit: () => void
}) {
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-small font-medium text-ink">
        {label}
      </label>
      <textarea
        id={id}
        ref={fieldRef}
        value={value}
        rows={2}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          // Enter asks; Shift+Enter is a new line, as in every chat box.
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            onSubmit()
          }
        }}
        className="min-h-12 w-full resize-y rounded-control border border-line-strong bg-panel px-3.5 py-3 text-body outline-none placeholder:text-ink-3 focus:border-focus"
      />
    </div>
  )
}

/** A4 — Ask, on Missions: a closed row until someone wants it. */
export function AskPanel() {
  const [q, setQ] = useState('')
  const field = useRef<HTMLTextAreaElement>(null)
  const id = useId()
  const agent = useAgent('ask')
  const submit = () => {
    if (!q.trim() || agent.isPending) return
    agent.mutate({ question: q.trim() })
  }
  return (
    <Disclosure title="Ask about missions and sites" onOpen={() => field.current?.focus()}>
      <PromptField
        id={`${id}-q`}
        label="Your question"
        value={q}
        onChange={setQ}
        placeholder="Which south-pole missions look for ice, and how long is their longest night?"
        fieldRef={field}
        onSubmit={submit}
      />
      <div>
        <Button variant="primary" onClick={submit} disabled={agent.isPending || !q.trim()}>
          Ask
        </Button>
      </div>
      <AgentCard kind="ask" agent={agent} onRephrase={() => field.current?.focus()} onRetry={submit} />
    </Disclosure>
  )
}

/** A2 — Advise, on Compare: a closed row until someone wants it. */
export function AdvisePanel({ start, end }: { start: string; end: string }) {
  const [req, setReq] = useState('')
  const field = useRef<HTMLTextAreaElement>(null)
  const id = useId()
  const agent = useAgent('advise')
  const submit = () => {
    if (!req.trim() || agent.isPending) return
    agent.mutate({ requirement: req.trim(), start, end })
  }
  return (
    <Disclosure title="Find sites that meet a requirement" onOpen={() => field.current?.focus()}>
      <PromptField
        id={`${id}-req`}
        label="The requirement, in your own words"
        value={req}
        onChange={setReq}
        placeholder="200 W solar and at least 4 hours of Earth contact per day"
        fieldRef={field}
        onSubmit={submit}
      />
      <div>
        <Button variant="primary" onClick={submit} disabled={agent.isPending || !req.trim()}>
          Find sites
        </Button>
      </div>
      <AgentCard kind="advise" agent={agent} onRephrase={() => field.current?.focus()} onRetry={submit} />
    </Disclosure>
  )
}

/** A1 — Explain, on Mission detail and Site, as a disclosure. */
export function ExplainPanel({
  siteId,
  start,
  end,
  summary = 'What is it like at this site?',
}: {
  siteId: string
  start: string
  end: string
  summary?: ReactNode
}) {
  const agent = useAgent('explain', [siteId])
  const { cancel } = agent
  const ask = () => agent.mutate({ site_id: siteId, start, end })

  // A new site or window is a new question: an answer about the old one must
  // not sit under the new numbers.
  useEffect(() => cancel(), [siteId, start, end, cancel])

  // Opening the row is the request: the description is written then, not
  // after a second click inside.
  return (
    <Disclosure
      title={summary}
      onOpen={() => {
        if (agent.isIdle) ask()
      }}
    >
      {/* After the dates or the site change, the old answer is gone: ask again. */}
      {agent.isIdle && (
        <div>
          <Button onClick={ask}>Describe it for these dates</Button>
        </div>
      )}
      <AgentCard kind="explain" agent={agent} onRetry={ask} />
    </Disclosure>
  )
}

/** A3 — Brief, on Report: a summary memo for the team, written on request. */
export function BriefPanel({ siteId, start, end }: { siteId: string; start: string; end: string }) {
  const agent = useAgent('brief', [siteId])
  const { cancel } = agent
  const write = () => agent.mutate({ site_id: siteId, start, end })
  useEffect(() => cancel(), [siteId, start, end, cancel])
  const name = hasSite(siteId) ? siteById(siteId).name : siteId
  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SectionLabel>Summary memo for {name}</SectionLabel>
        <Button onClick={write} disabled={agent.isPending}>
          Write a summary memo
        </Button>
      </div>
      <AgentCard kind="brief" agent={agent} onRetry={write} />
    </section>
  )
}
