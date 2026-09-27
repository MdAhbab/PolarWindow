import { useState, type ReactNode } from 'react'
import { api, ApiError } from '../../lib/api/client'
import type { AuditEntryDTO, FeedDTO, ParameterDTO, RiskScaleDTO } from '../../lib/api/lifecycle'
import { useFeeds, useHistory, useLifecycleWrite, useParameters, useRiskScales } from '../../lib/api/lifecycleQueries'
import { hasOwnName, useSession, SignInFailed } from '../../lib/session'
import { dateTimeWords } from '../../lib/format'
import { ageFromSeconds, formatValue, hostWords, quantityText, unitWords } from '../../lib/lifecycle/quantity'
import { Icon, type IconName } from '../Icon'
import { Button } from '../ui'
import { Field, HistoryList, TextArea, TextInput, useNamedWriter, WriteProblem } from './Forms'
import { CATEGORY_WORDS } from './Readiness'

/**
 * Settings → Project additions (design-lifecycle.md §6): who is signed in,
 * where the live data comes from and how fresh it is, the risk scale in use,
 * and the team's parameters. Each is a closed row, as the rest of the group.
 */

function Row({ title, meta, children, onOpen }: { title: string; meta?: string; children: ReactNode; onOpen?: () => void }) {
  return (
    <details
      className="group flex flex-col gap-3"
      onToggle={(e) => {
        if ((e.currentTarget as HTMLDetailsElement).open) onOpen?.()
      }}
    >
      <summary className="inline-flex min-h-12 cursor-pointer flex-wrap items-baseline gap-x-3 py-2 text-control font-semibold text-ink">
        {title}
        {meta && <span className="text-small font-normal text-ink-3">{meta}</span>}
      </summary>
      <div className="flex flex-col gap-3 pb-2">{children}</div>
    </details>
  )
}

/** ADR-17: a name on every change. Signing in again with a name is one small form. */
export function People() {
  const session = useSession((s) => s.session)
  const signIn = useSession((s) => s.signIn)
  const [name, setName] = useState(session?.user && hasOwnName(session) ? session.user.name : '')
  const [team, setTeam] = useState(session?.user?.team ?? '')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState<string | undefined>()
  return (
    <Row title="People" meta={hasOwnName(session) ? `you: ${session?.user?.name}` : 'no name given yet'}>
      <p className="text-caption leading-caption text-ink-3">
        Every readiness change, part, risk, booked pass and entered forecast is recorded with the name of the person who
        entered it. Reading needs no name.
      </p>
      <form
        className="flex flex-col gap-3"
        onSubmit={async (e) => {
          e.preventDefault()
          if (!name.trim()) {
            setErr('Enter your name.')
            return
          }
          setErr(undefined)
          setBusy(true)
          try {
            const s = await signIn({ name: name.trim(), team: team.trim() || null })
            setMsg(`Signed in as ${s.user?.name ?? name.trim()}.`)
          } catch (x) {
            setErr(x instanceof SignInFailed ? x.message : 'Signing in did not work.')
          } finally {
            setBusy(false)
          }
        }}
      >
        <Field label="Your name" error={err}>
          {(p) => <TextInput {...p} autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />}
        </Field>
        <Field label="Team (optional)">
          {(p) => <TextInput {...p} autoComplete="organization" value={team} onChange={(e) => setTeam(e.target.value)} />}
        </Field>
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" size="sm" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in with this name'}
          </Button>
          <p aria-live="polite" className="text-caption text-ink-2">
            {msg}
          </p>
        </div>
      </form>
    </Row>
  )
}

/** A feed's state as a shape and words (invariant 4). */
function feedState(f: FeedDTO): { icon: IconName; words: string } {
  if (f.breaker === 'open') return { icon: 'alert', words: 'Failing' }
  if (f.stale) return { icon: 'uncertain', words: 'Out of date' }
  return { icon: 'dot', words: 'Working' }
}

function errorWords(f: FeedDTO): string | null {
  if (f.last_error) return f.last_error
  const e = f.errors
  if (e === null || e === 0 || e === '') return null
  if (typeof e === 'number') return `${e} failed ${e === 1 ? 'try' : 'tries'} in a row`
  if (Array.isArray(e)) return e.length ? e[e.length - 1] : null
  return e
}

/** The worst of a provider's products decides its line: failing, then out of date, then working. */
function worst(feeds: FeedDTO[]): FeedDTO {
  const rank = (f: FeedDTO) => (f.breaker === 'open' ? 2 : f.stale ? 1 : 0)
  return feeds.reduce((w, f) => (rank(f) > rank(w) ? f : w), feeds[0])
}

/**
 * Every live feed, one line per provider (invariant 11): whether it works,
 * how old each product's data is, when it runs next, its licence, and
 * "Refresh now". A provider with many products stays one line until opened.
 */
export function DataSources({ enabled, live }: { enabled: boolean; live: boolean }) {
  const [open, setOpen] = useState(false)
  const q = useFeeds(enabled && open && live)
  const refresh = useLifecycleWrite((provider: string) => api.refreshFeed(provider))
  const session = useSession((s) => s.session)
  const feeds = q.data?.feeds ?? []
  const failing = feeds.filter((f) => f.breaker === 'open').length
  const stale = feeds.filter((f) => f.stale && f.breaker !== 'open').length
  const groups = [...feeds.reduce((m, f) => m.set(f.provider, [...(m.get(f.provider) ?? []), f]), new Map<string, FeedDTO[]>())]
  return (
    <Row
      title="Data sources"
      meta={
        q.data
          ? `${feeds.length} products from ${groups.length} providers: ${feeds.length - failing - stale} working, ${stale} out of date, ${failing} failing`
          : undefined
      }
      onOpen={() => setOpen(true)}
    >
      {!live ? (
        <p className="text-small leading-5 text-ink-2">This copy runs from saved answers; the live feeds need the service.</p>
      ) : q.isPending ? (
        <p className="text-small text-ink-3">Loading the feeds…</p>
      ) : q.error ? (
        <p className="text-small leading-5 text-ink-2">
          {q.error instanceof ApiError && q.error.status === 404
            ? 'This server does not report its live feeds yet.'
            : `The feeds could not be loaded: ${(q.error as ApiError).title ?? String(q.error)}`}
        </p>
      ) : (
        <ul className="flex flex-col divide-y divide-line border-y border-line">
          {groups.map(([provider, list]) => {
            const st = feedState(worst(list))
            const next = list.map((f) => (f.next_run ? Date.parse(f.next_run) : NaN)).filter((n) => !Number.isNaN(n))
            return (
              <li key={provider} className="flex flex-col gap-1.5 py-2.5">
                <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                  <span className="text-small font-semibold text-ink">{list[0].provider_name ?? provider}</span>
                  <span className="flex items-center gap-1.5 text-small text-ink">
                    <Icon name={st.icon} size={14} strokeWidth={2} />
                    {st.words}
                  </span>
                </div>
                <ul className="flex flex-col gap-0.5">
                  {list.map((f) => {
                    const s = feedState(f)
                    const err = errorWords(f)
                    return (
                      <li key={`${f.product}-${f.location ?? ''}`} className="text-caption leading-caption text-ink-3">
                        <span className="text-ink-2">
                          {f.product}
                          {f.location ? `, ${f.location}` : ''}
                        </span>
                        {' · '}
                        {f.age_s !== null ? `data from ${ageFromSeconds(f.age_s)}` : 'no data yet'}
                        {s.words !== 'Working' ? ` · ${s.words.toLowerCase()}` : ''}
                        {err ? ` · ${err}` : ''}
                      </li>
                    )
                  })}
                </ul>
                <span className="text-caption leading-caption text-ink-3">
                  {[next.length ? `Next run ${dateTimeWords(Math.min(...next))}` : null, list[0].licence ? `licence: ${list[0].licence}` : null]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
                {session && !session.offline && (
                  <div>
                    <Button size="sm" variant="ghost" disabled={refresh.isPending} onClick={() => refresh.mutate(provider)}>
                      Refresh now
                      <span className="sr-only">: {list[0].provider_name ?? provider}</span>
                    </Button>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
      {refresh.error ? (
        <p role="alert" className="text-caption text-ink-2">
          {(refresh.error as ApiError).title ?? 'Refresh failed'}
        </p>
      ) : null}
    </Row>
  )
}

/** True when every level's words say no more than its number ("1, lowest", "2"). */
export function levelsHaveNoWords(scale: RiskScaleDTO): boolean {
  const all = [...scale.likelihood, ...scale.consequence.flatMap((c) => c.levels)]
  return all.every((l) => new RegExp(`^${l.level}(,?\\s*(the\\s+)?(lowest|highest))?\\.?$`, 'i').test(l.words.trim()))
}

/** "safety, technical, cost and schedule". */
function listWords(xs: string[]): string {
  return xs.length < 2 ? (xs[0] ?? '') : `${xs.slice(0, -1).join(', ')} and ${xs[xs.length - 1]}`
}

/** The likelihood and consequence levels in use (read-only), with their source. */
export function RiskScalePanel({ enabled }: { enabled: boolean }) {
  const [open, setOpen] = useState(false)
  const q = useRiskScales(enabled && open)
  const scale = q.data?.scales.find((s) => s.id === q.data?.default_id) ?? q.data?.scales[0]
  const numbersOnly = scale ? levelsHaveNoWords(scale) : false
  return (
    <Row title="Risk scale" meta={scale?.name} onOpen={() => setOpen(true)}>
      {q.isPending ? (
        <p className="text-small text-ink-3">Loading the scale…</p>
      ) : !scale ? (
        <p className="text-small leading-5 text-ink-2">
          {q.error instanceof ApiError && q.error.status === 404 ? 'This server does not offer a risk scale yet.' : 'The scale could not be loaded.'}
        </p>
      ) : (
        <>
          <p className="text-caption leading-caption text-ink-3">
            Likelihood and consequence are rated separately for each category and never multiplied into a score.
            {scale.source_url && (
              <>
                {' Source: '}
                <a href={scale.source_url} target="_blank" rel="noreferrer">
                  {hostWords(scale.source_url)}
                </a>
                .
              </>
            )}
          </p>
          {scale.notes?.length ? (
            <ul className="flex list-disc flex-col gap-1 pl-5 text-caption leading-caption text-ink-3">
              {scale.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          ) : null}
          {numbersOnly ? (
            <p className="text-small leading-5 text-ink-2">
              {scale.likelihood.length} likelihood levels, and {scale.likelihood.length} consequence levels for each of{' '}
              {listWords(scale.consequence.map((c) => CATEGORY_WORDS[c.category].toLowerCase()))}, 1 the lowest. No words
              are entered for the levels yet, so each is shown as its number.
            </p>
          ) : (
            <table className="w-full border-collapse text-left text-small">
              <caption className="sr-only">Likelihood levels, and consequence levels for each category.</caption>
              <thead>
                <tr className="border-b border-line">
                  <th scope="col" className="py-1.5 pr-2 font-semibold text-ink-3">Level</th>
                  <th scope="col" className="py-1.5 pr-2 font-semibold text-ink-3">Likelihood</th>
                  {scale.consequence.map((c) => (
                    <th key={c.category} scope="col" className="py-1.5 pr-2 font-semibold text-ink-3">
                      {CATEGORY_WORDS[c.category]}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {scale.likelihood.map((l) => (
                  <tr key={l.level} className="border-b border-line align-top">
                    <th scope="row" className="py-1.5 pr-2 font-mono text-ink">{l.level}</th>
                    <td className="py-1.5 pr-2 text-ink-2">{l.words}</td>
                    {scale.consequence.map((c) => (
                      <td key={c.category} className="py-1.5 pr-2 text-ink-2">
                        {c.levels.find((x) => x.level === l.level)?.words ?? '—'}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </Row>
  )
}

/** "96 h", "12°": a parameter's value with its unit, as the rest of the screens write it. */
function valueWithUnit(v: unknown, unit: string): string {
  if (typeof v !== 'number') return 'none'
  const u = unitWords(unit)
  return `${formatValue(v)}${u.joined || !u.short ? '' : ' '}${u.short}`
}

/** One line for a parameter's change: "Set to 96 h" or "120 h → 96 h". */
export function parameterChangeWords(e: AuditEntryDTO, unit: string): string {
  const before = (e.before ?? null) as { value?: unknown } | null
  const after = (e.after ?? null) as { value?: unknown } | null
  if (!after) return 'Cleared'
  if (!before || typeof before.value !== 'number') return `Set to ${valueWithUnit(after.value, unit)}`
  if (before.value === after.value) return `Note changed; the value stays ${valueWithUnit(after.value, unit)}`
  return `${valueWithUnit(before.value, unit)} → ${valueWithUnit(after.value, unit)}`
}

/** The note a change was saved with: the audit note, else the parameter's own note. */
function withNote(entries: AuditEntryDTO[] | undefined): AuditEntryDTO[] | undefined {
  return entries?.map((e) => ({ ...e, note: e.note ?? ((e.after as { note?: string | null } | null)?.note || null) }))
}

/**
 * Enter or change one parameter, in place under it: the value in its unit,
 * a note saying where it comes from, one Save, and its change history.
 */
function ParameterForm({ p, id }: { p: ParameterDTO; id: string }) {
  const writer = useNamedWriter()
  const save = useLifecycleWrite((body: { value: number; note: string | null }) => api.setParameter(p.id, body))
  const history = useHistory('parameter', p.id)
  const [value, setValue] = useState(p.value.value === null ? '' : String(p.value.value))
  const [note, setNote] = useState(p.note ?? '')
  const [err, setErr] = useState<string | undefined>()
  const [saved, setSaved] = useState(false)
  const u = unitWords(p.value.unit)
  return (
    <div id={id} className="flex flex-col gap-4 border-l-2 border-line-strong pl-3">
      <form
        className="flex flex-col gap-3"
        onSubmit={async (e) => {
          e.preventDefault()
          setSaved(false)
          const v = Number(value.trim())
          if (!value.trim() || !Number.isFinite(v)) {
            setErr('Enter a number.')
            return
          }
          setErr(undefined)
          if (!(await writer.ensure())) return
          try {
            await save.mutateAsync({ value: v, note: note.trim() || null })
            setSaved(true)
          } catch {
            // shown below, in the server's words
          }
        }}
      >
        {writer.fields}
        <Field label={u.spoken ? `Value, in ${u.spoken}` : 'Value'} error={err}>
          {(a) => <TextInput {...a} inputMode="decimal" autoComplete="off" value={value} onChange={(e) => setValue(e.target.value)} />}
        </Field>
        <Field label="Note (optional)" hint="Where the value comes from, for example the power budget and its revision.">
          {(a) => <TextArea {...a} value={note} onChange={(e) => setNote(e.target.value)} />}
        </Field>
        <WriteProblem error={save.error} />
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" size="sm" variant="primary" disabled={save.isPending || writer.offline}>
            {save.isPending ? 'Saving…' : 'Save'}
          </Button>
          <p aria-live="polite" className="text-caption text-ink-2">
            {saved && !save.error ? 'Saved.' : ''}
          </p>
        </div>
      </form>
      <div className="flex flex-col gap-2">
        <HistoryList
          entries={withNote(history.data)}
          pending={history.isPending}
          error={history.error}
          describe={(e) => parameterChangeWords(e, p.value.unit)}
        />
      </div>
    </div>
  )
}

/**
 * The values the project sets (battery limit, landing Sun heights, days on
 * the surface): each with its value or why it has none, who set it and when,
 * and a way to enter or change it. Shown only when the server offers them.
 */
export function ParametersPanel({ enabled }: { enabled: boolean }) {
  const q = useParameters(enabled)
  const session = useSession((s) => s.session)
  const [editing, setEditing] = useState<string | null>(null)
  if (q.error instanceof ApiError && q.error.status === 404) return null
  const params = q.data?.parameters ?? []
  const entered = params.filter((p) => p.value.value !== null).length
  const canWrite = Boolean(session && !session.offline)
  return (
    <Row title="Parameters" meta={q.data ? `${entered} of ${params.length} entered` : undefined}>
      <p className="text-caption leading-caption text-ink-3">
        Values the project sets. The sections use them once entered; until then each says what is missing.
      </p>
      {q.isPending ? (
        <p className="text-small text-ink-3">Loading the parameters…</p>
      ) : q.error ? (
        <p className="text-small text-ink-2">The parameters could not be loaded.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-line border-y border-line">
          {params.map((p) => {
            const missing = p.value.value === null
            const open = editing === p.id
            const meta = missing
              ? [p.value.missing_reason]
              : [
                  p.value.no_margin_reason,
                  p.note,
                  p.changed_by ? `set by ${p.changed_by}${p.changed_at ? `, ${dateTimeWords(Date.parse(p.changed_at))}` : ''}` : null,
                ]
            return (
              <li key={p.id} className="flex flex-col gap-1.5 py-2.5">
                <span className="text-small font-semibold text-ink">{p.name}</span>
                <span className="text-small text-ink">{missing ? 'Not entered yet' : quantityText(p.value)}</span>
                <span className="text-caption leading-caption text-ink-3">{meta.filter(Boolean).join(' · ')}</span>
                {canWrite && (
                  <div>
                    <Button
                      size="sm"
                      variant="ghost"
                      expanded={open}
                      controls={open ? `param-${p.id}` : undefined}
                      onClick={() => setEditing(open ? null : p.id)}
                    >
                      {missing ? 'Enter a value' : 'Change'}
                      <span className="sr-only"> for {p.name}</span>
                    </Button>
                  </div>
                )}
                {open && <ParameterForm p={p} id={`param-${p.id}`} />}
              </li>
            )
          })}
        </ul>
      )}
    </Row>
  )
}
