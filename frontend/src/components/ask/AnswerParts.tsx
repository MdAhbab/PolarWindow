import { Link } from 'react-router-dom'
import type { ChatResponseDTO } from '../../lib/api/experience.types'
import type { ProvenanceItemDTO } from '../../lib/api/client'
import { fieldWords, toolWords } from '../../lib/fieldWords'
import { hasSite, siteById } from '../../lib/sites'
import { useMission } from '../../lib/store'
import { Icon, type IconName } from '../Icon'

/** A number from the API, printed as sent: no rounding, no unit conversion. */
const asSent = (v: unknown): string => (typeof v === 'number' ? String(v) : String(v ?? ''))

const UNIT_WORDS = { h: 'h', s: 's' } as const

/**
 * A tile's label: the figure's own name, as on the pages ("Longest night"), without where it
 * sat in the tool's result or the unit the tile already shows.
 */
function tileWords(field: string): string {
  const leaf = field.split('.').pop()?.replace(/\[\d+\]/g, '') ?? field
  const words = fieldWords(leaf).replace(/ \((hours|seconds|minutes|percent)\)$/, '')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/** Sun or Earth, from the field a number came from, for the tile's mark and bar colour. */
function bodyOf(field: string): 'sun' | 'earth' | null {
  if (/sun|sunlit|dark/.test(field)) return 'sun'
  if (/earth|contact|blackout/.test(field)) return 'earth'
  return null
}

/**
 * The answer's numbers as tiles, the way the pages show them: each duration
 * with the margin the lookup gave beside it (or that it gave none), and each
 * share of time as a day-and-night bar. Other numbers stay in the sentence.
 * Each tile opens the page the answer points to.
 */
export function AnswerTiles({ items, href, onLeave }: { items: ProvenanceItemDTO[]; href?: string; onLeave?: () => void }) {
  const seen = new Set<string>()
  const tiles = items.filter((p) => {
    const key = `${p.field}|${p.value}`
    // A margin is not a figure of its own: it shows on its figure's tile and in the sentence.
    if (/_tolerance_(h|s|min)$/.test(p.field)) return false
    if (seen.has(key) || !(p.unit || /_fraction_up$/.test(p.field))) return false
    seen.add(key)
    return true
  })
  if (!tiles.length) return null
  return (
    <ul aria-label="The numbers in this answer" className="grid grid-cols-2 gap-2">
      {tiles.slice(0, 6).map((p) => {
        const body = bodyOf(p.field)
        const share = /_fraction_up$/.test(p.field) && p.value >= 0 && p.value <= 1
        const inner = (
          <>
            <span className="flex items-center gap-1.5 text-caption leading-caption text-ink-3">
              {body && <Icon name={body} size={13} strokeWidth={2} className={body === 'sun' ? 'text-sun' : 'text-earth'} />}
              <span className="min-w-0 truncate">{tileWords(p.field)}</span>
            </span>
            <span className="font-mono text-control font-semibold text-ink tnum">
              {share ? `${Math.round(p.value * 100)}%` : `${asSent(p.value)} ${p.unit ? UNIT_WORDS[p.unit] : ''}`}
            </span>
            {share ? (
              // Up for this share of the time, down for the rest: seen as well as read.
              <span aria-hidden="true" className="flex h-1.5 overflow-hidden rounded-pill bg-inset">
                <span className={body === 'earth' ? 'bg-earth' : 'bg-sun'} style={{ width: `${p.value * 100}%` }} />
              </span>
            ) : (
              <span className="text-caption leading-caption text-ink-3">
                {p.margin != null ? `± ${asSent(p.margin)} ${p.unit ? UNIT_WORDS[p.unit] : ''}` : 'no margin given'}
              </span>
            )}
          </>
        )
        const cls = 'flex min-h-11 min-w-0 flex-col gap-1 rounded-control border border-line bg-panel px-3 py-2 text-ink no-underline'
        return (
          <li key={`${p.field}|${p.value}`} className="min-w-0">
            {href ? (
              <Link to={href} onClick={onLeave} className={`${cls} hover:border-line-strong hover:bg-inset`}>
                {inner}
              </Link>
            ) : (
              <div className={cls}>{inner}</div>
            )}
          </li>
        )
      })}
    </ul>
  )
}

const day = (v: unknown): string | null => {
  if (typeof v !== 'string' || !/^\d{4}-\d{2}-\d{2}/.test(v)) return null
  const d = new Date(`${v.slice(0, 10)}T00:00:00Z`)
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
}

/** One lookup in plain words: what was looked up, where, and over which dates. */
export function lookupWords(tool: string, args: Record<string, unknown>): string {
  const site = typeof args.site_id === 'string' ? (hasSite(args.site_id) ? siteById(args.site_id).name : args.site_id) : null
  const mission = typeof args.mission_id === 'string' ? args.mission_id.toUpperCase() : null
  const a = day(args.start)
  const b = day(args.end)
  return [toolWords(tool), site ?? mission, a && b ? `${a} to ${b}` : null].filter(Boolean).join(', ')
}

function Step({ n, icon, title, children }: { n: number; icon: IconName; title: string; children: React.ReactNode }) {
  return (
    <li className="grid grid-cols-[1.75rem_minmax(0,1fr)] gap-x-2.5">
      <span aria-hidden="true" className="flex size-7 items-center justify-center rounded-pill border border-line-strong bg-tray text-ink-2">
        <Icon name={icon} size={14} strokeWidth={2} />
      </span>
      <div className="flex min-w-0 flex-col gap-1.5 pt-0.5">
        <h4 className="text-small font-semibold text-ink">
          <span className="sr-only">Step {n}: </span>
          {title}
        </h4>
        {children}
      </div>
    </li>
  )
}

/**
 * How this answer was made, in three steps: what was looked up, that every
 * number was checked against those lookups, and what was written. The
 * model's name, the timing and the run itself sit under Technical details.
 */
export function HowThisWasMade({ r, words, rules }: { r: ChatResponseDTO; words: string | null; rules: boolean }) {
  const openRunLog = useMission((s) => s.openRunLog)
  const numbers = r.provenance ?? []
  const calls = r.tool_calls ?? []
  const replaced = r.run_status === 'guard_rejected'
  const model = (r.meta as { model?: unknown } | undefined)?.model
  return (
    <details className="group border-t border-line">
      <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between gap-3 py-1.5 hover:text-ink [&::-webkit-details-marker]:hidden">
        <span className="text-small font-semibold text-ink">How this answer was made</span>
        <Icon name="chevron" size={16} strokeWidth={2} className="pw-turn shrink-0 text-ink-3 group-open:rotate-180" />
      </summary>
      <div className="pw-disclosure-body flex flex-col gap-4 pt-1 pb-2">
        <ol className="flex flex-col gap-4">
          <Step n={1} icon="search" title="Looked up">
            {calls.length ? (
              <ul className="flex flex-col gap-1">
                {calls.map((c) => (
                  <li key={c.seq} className="text-caption leading-caption text-ink-2">
                    {lookupWords(c.tool, c.args ?? {})}:{' '}
                    <span className="text-ink-3">
                      {c.error ? 'did not answer' : `${c.number_count} ${c.number_count === 1 ? 'number' : 'numbers'}`}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-caption leading-caption text-ink-2">Nothing was looked up.</p>
            )}
          </Step>
          <Step n={2} icon="check" title="Checked">
            <p className="text-caption leading-caption text-ink-2">
              {replaced
                ? 'A number did not match a lookup, so the answer was replaced by a plain summary of the lookups.'
                : numbers.length
                  ? `Every number in the answer matches a lookup (${numbers.length} checked).`
                  : 'The answer has no numbers to check.'}
            </p>
            {numbers.length > 0 && (
              <ul className="flex flex-col gap-1.5">
                {numbers.map((p, i) => (
                  <li key={i} className="flex flex-col border-l-2 border-line-strong pl-2.5">
                    <span className="font-mono text-caption text-ink tnum">{asSent(p.value)}</span>
                    <span className="text-caption leading-caption text-ink-3">
                      {toolWords(p.tool)}, {fieldWords(p.field)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Step>
          <Step n={3} icon="pencil" title="Written">
            <p className="text-caption leading-caption text-ink-2">
              {rules ? 'Put together by fixed rules from the lookups.' : 'Written by the AI from the lookups.'}
              {words && r.result?.interpreted_as ? ` Question read as: ${r.result.interpreted_as.trim()}` : ''}
            </p>
          </Step>
        </ol>
        <details className="group/tech rounded-control border border-line px-3">
          <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 text-caption font-semibold text-ink-2 [&::-webkit-details-marker]:hidden">
            Technical details
            <Icon name="chevron" size={14} strokeWidth={2} className="pw-turn text-ink-3 group-open/tech:rotate-180" />
          </summary>
          <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 pb-3 font-mono text-caption text-ink-2">
            <dt className="text-ink-3">Model</dt>
            <dd className="min-w-0 break-words">{typeof model === 'string' && model ? model : rules ? 'none (rules)' : 'not reported'}</dd>
            <dt className="text-ink-3">Time</dt>
            <dd>{(r.latency_ms / 1000).toFixed(1)} s</dd>
            {calls.map((c) => (
              <div key={c.seq} className="contents">
                <dt className="text-ink-3">Tool {c.seq}</dt>
                <dd className="min-w-0 break-words">
                  {c.tool}, {c.latency_ms} ms
                </dd>
              </div>
            ))}
          </dl>
          {r.run_id && (
            <button
              type="button"
              onClick={(e) => {
                // Focus the opener first: Safari does not focus a clicked button, and
                // the drawer returns focus to whatever had it when it opened.
                e.currentTarget.focus()
                openRunLog(r.run_id ?? null)
              }}
              className="pw-press -ml-2 mb-2 inline-flex h-11 items-center gap-2 rounded-pill px-2 text-small font-semibold text-ink-2 hover:bg-inset hover:text-ink"
            >
              <Icon name="log" size={16} strokeWidth={1.8} />
              Open this run in the log, with token counts
            </button>
          )}
        </details>
      </div>
    </details>
  )
}
