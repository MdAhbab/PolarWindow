import { useState, type ReactNode } from 'react'
import { api, ApiError } from '../../lib/api/client'
import type { FeedDTO } from '../../lib/api/lifecycle'
import { useFeeds, useLifecycleWrite, useParameters, useRiskScales } from '../../lib/api/lifecycleQueries'
import { hasOwnName, useSession, SignInFailed } from '../../lib/session'
import { dateTimeWords } from '../../lib/format'
import { ageFromSeconds, hostWords, quantityText } from '../../lib/lifecycle/quantity'
import { Icon, type IconName } from '../Icon'
import { Button } from '../ui'
import { Field, TextInput } from './Forms'
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

/** The likelihood and consequence levels in use (read-only), with their source. */
export function RiskScalePanel({ enabled }: { enabled: boolean }) {
  const [open, setOpen] = useState(false)
  const q = useRiskScales(enabled && open)
  const scale = q.data?.scales.find((s) => s.id === q.data?.default_id) ?? q.data?.scales[0]
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
        </>
      )}
    </Row>
  )
}

/** The team's parameters, and who set them; shown only when the server offers them. */
export function ParametersPanel({ enabled }: { enabled: boolean }) {
  const [open, setOpen] = useState(true)
  const q = useParameters(enabled && open)
  if (q.error instanceof ApiError && q.error.status === 404) return null
  const params = q.data?.parameters ?? []
  return (
    <Row title="Parameters" meta={q.data ? String(params.length) : undefined} onOpen={() => setOpen(true)}>
      {q.isPending ? (
        <p className="text-small text-ink-3">Loading the parameters…</p>
      ) : q.error ? (
        <p className="text-small text-ink-2">The parameters could not be loaded.</p>
      ) : (
        <dl className="flex flex-col divide-y divide-line border-y border-line">
          {params.map((p) => (
            <div key={p.id} className="flex flex-col gap-0.5 py-2.5">
              <dt className="text-small font-semibold text-ink">{p.name}</dt>
              <dd className="text-small text-ink">{quantityText(p.value)}</dd>
              <dd className="text-caption leading-caption text-ink-3">
                {[
                  p.value.provenance === 'assumed' ? 'Assumed' : null,
                  p.value.no_margin_reason,
                  p.note,
                  p.changed_by ? `set by ${p.changed_by}${p.changed_at ? `, ${dateTimeWords(Date.parse(p.changed_at))}` : ''}` : null,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </Row>
  )
}
