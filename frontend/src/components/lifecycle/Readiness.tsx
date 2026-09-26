import { useState } from 'react'
import type {
  ItemKind,
  LandingHistoryDTO,
  PartDTO,
  PartStatus,
  ReadyItemDTO,
  ReadyState,
  RiskCategory,
  RiskDTO,
  RiskScaleDTO,
  TestKind,
} from '../../lib/api/lifecycle'
import { usePartImpact } from '../../lib/api/lifecycleQueries'
import { isoDateWords, shortDate } from '../../lib/format'
import { hostWords } from '../../lib/lifecycle/quantity'
import { Icon, type IconName } from '../Icon'
import { Button, ScrollRegion, Segmented } from '../ui'

// ---------------------------------------------------------------------------
// Words
// ---------------------------------------------------------------------------

/** The readiness steps in order (ADR-17); "blocked" can come from any of them. */
export const READY_ORDER: Exclude<ReadyState, 'blocked'>[] = [
  'not_started',
  'in_build',
  'in_test',
  'test_passed',
  'delivered',
  'integrated',
  'verified_on_lander',
  'ready',
]

export const READY_WORDS: Record<ReadyState, string> = {
  not_started: 'Not started',
  in_build: 'In build',
  in_test: 'In test',
  test_passed: 'Test passed',
  delivered: 'Delivered to the lander provider',
  integrated: 'Integrated on the lander',
  verified_on_lander: 'Verified on the lander',
  ready: 'Ready',
  blocked: 'Blocked',
}

export const KIND_WORDS: Record<ItemKind, string> = {
  lander: 'Lander',
  payload: 'Payload',
  rover: 'Rover',
  launch_vehicle: 'Launch vehicle',
  range: 'Pad and range',
  ground_booking: 'Ground-station booking',
  relay_agreement: 'Relay agreement',
  ops_team: 'Operations team',
  licence: 'Licence',
}

export const TEST_WORDS: Record<TestKind, string> = {
  vibration: 'Vibration',
  shock: 'Shock',
  thermal_vacuum: 'Thermal vacuum',
  emi_emc: 'Radio interference (EMI/EMC)',
  functional: 'Working check after the tests',
}

export const PART_WORDS: Record<PartStatus, { words: string; icon: IconName }> = {
  installed: { words: 'Installed', icon: 'dot' },
  spare: { words: 'Spare', icon: 'ring' },
  in_test: { words: 'In test', icon: 'quarter' },
  damaged: { words: 'Damaged', icon: 'alert' },
  failed: { words: 'Failed', icon: 'alert' },
  lost: { words: 'Part lost', icon: 'alert' },
}

export const CATEGORY_WORDS: Record<RiskCategory, string> = {
  safety: 'Safety',
  technical: 'Technical',
  cost: 'Cost',
  schedule: 'Schedule',
}

export const TREND_WORDS: Record<RiskDTO['trend'], { words: string; glyph: string }> = {
  rising: { words: 'Rising', glyph: '↑' },
  steady: { words: 'Steady', glyph: '→' },
  falling: { words: 'Falling', glyph: '↓' },
}

const OUTCOME_WORDS: Record<string, { words: string; glyph: string }> = {
  landed_working: { words: 'Landed and worked', glyph: '✓' },
  landed_tipped_or_partial: { words: 'Landed, tipped or partly working', glyph: '◐' },
  failed: { words: 'Failed', glyph: '✕' },
}

/** Blocked first, then the least advanced, then by name. */
export function sortItems(items: ReadyItemDTO[]): ReadyItemDTO[] {
  const rank = (s: ReadyState) => (s === 'blocked' ? -1 : READY_ORDER.indexOf(s))
  return [...items].sort((a, b) => rank(a.state) - rank(b.state) || a.name.localeCompare(b.name))
}

const when = (iso: string | null) => (iso ? shortDate(Date.parse(iso)) : null)

// ---------------------------------------------------------------------------
// The readiness list
// ---------------------------------------------------------------------------

/**
 * How far along the fixed sequence an item is: eight steps, filled up to its
 * own. A position, not a score, and it carries no number (invariant 9).
 */
function Ladder({ state }: { state: ReadyState }) {
  const at = state === 'blocked' ? -1 : READY_ORDER.indexOf(state)
  return (
    <span className="flex gap-0.5" aria-hidden="true">
      {READY_ORDER.map((s, i) => (
        <span key={s} className={`h-2 w-3 ${i <= at ? 'bg-ink-2' : 'bg-dark-fill'} ${state === 'blocked' ? 'hatch-blocked' : ''}`} />
      ))}
    </span>
  )
}

function StateWords({ item }: { item: ReadyItemDTO }) {
  if (item.state === 'blocked') {
    return (
      <span className="flex items-start gap-1.5 text-small font-semibold text-ink">
        <Icon name="alert" size={15} strokeWidth={2.2} className="mt-0.5 shrink-0" />
        <span>
          Blocked{item.blocked_reason ? <span className="font-normal text-ink-2">: {item.blocked_reason}</span> : null}
        </span>
      </span>
    )
  }
  return (
    <span className="flex items-center gap-1.5 text-small text-ink">
      {item.state === 'ready' ? <Icon name="check" size={15} strokeWidth={2.4} className="shrink-0" /> : null}
      {READY_WORDS[item.state]}
    </span>
  )
}

function Evidence({ url, name }: { url: string | null; name: string }) {
  if (!url)
    return (
      <span className="text-small text-ink-3">
        <span aria-hidden="true">—</span>
        <span className="sr-only">No evidence linked</span>
      </span>
    )
  return (
    <a href={url} target="_blank" rel="noreferrer" className="text-small" aria-label={`Evidence for ${name}: ${hostWords(url)}`}>
      {hostWords(url)}
    </a>
  )
}

/**
 * Every readiness item, blocked first (design-lifecycle.md §4, Ready): its
 * state as words and a ladder, since when and by whom, and its evidence.
 * A table from 768 px, one card per item below it.
 */
export function ReadinessList({
  items,
  onChange,
}: {
  items: ReadyItemDTO[]
  /** Given only to a session that can write. */
  onChange?: (item: ReadyItemDTO) => void
}) {
  const sorted = sortItems(items)
  const head = 'px-3 py-2.5 text-tag font-semibold tracking-caps-md text-ink-3 uppercase'
  return (
    <>
      <div className="hidden md:block">
        <table className="w-full border-collapse text-left" aria-label="Readiness items">
          <thead>
            <tr className="bg-inset">
              <th scope="col" className={head}>Item</th>
              <th scope="col" className={head}>State</th>
              <th scope="col" className={head}>Since</th>
              <th scope="col" className={head}>Evidence</th>
              {onChange && (
                <th scope="col" className={head}>
                  <span className="sr-only">Change</span>
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {sorted.map((it) => (
              <tr key={it.id} className="border-t border-line align-top">
                <th scope="row" className="px-3 py-3 text-left font-normal">
                  <span className="block text-body font-semibold text-ink">{it.name}</span>
                  <span className="block text-caption text-ink-3">
                    {[KIND_WORDS[it.kind], it.organisation].filter(Boolean).join(' · ')}
                  </span>
                </th>
                <td className="px-3 py-3">
                  <span className="flex flex-col gap-1.5">
                    <Ladder state={it.state} />
                    <StateWords item={it} />
                  </span>
                </td>
                <td className="px-3 py-3 text-small text-ink-2">
                  {when(it.changed_at) ?? 'Not recorded'}
                  {it.changed_by && <span className="block text-caption text-ink-3">{it.changed_by}</span>}
                </td>
                <td className="px-3 py-3">
                  <Evidence url={it.evidence_url} name={it.name} />
                </td>
                {onChange && (
                  <td className="px-3 py-2 text-right">
                    <ChangeButton onClick={() => onChange(it)} name={it.name} />
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="flex flex-col divide-y divide-line border-y border-line md:hidden" aria-label="Readiness items">
        {sorted.map((it) => (
          <li key={it.id} className="flex flex-col gap-1.5 py-3">
            <span className="text-body font-semibold text-ink">{it.name}</span>
            <span className="text-caption text-ink-3">{[KIND_WORDS[it.kind], it.organisation].filter(Boolean).join(' · ')}</span>
            <Ladder state={it.state} />
            <StateWords item={it} />
            <span className="text-caption text-ink-3">
              {[when(it.changed_at) ? `Since ${when(it.changed_at)}` : null, it.changed_by].filter(Boolean).join(' · ') || 'Not recorded'}
            </span>
            {it.evidence_url && <Evidence url={it.evidence_url} name={it.name} />}
            {onChange && (
              <div>
                <ChangeButton onClick={() => onChange(it)} name={it.name} />
              </div>
            )}
          </li>
        ))}
      </ul>
    </>
  )
}

function ChangeButton({ onClick, name }: { onClick: () => void; name: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-haspopup="dialog"
      aria-label={`Change ${name}`}
      className="inline-flex h-12 items-center gap-2 rounded-control px-3 text-small font-semibold text-ink-2 hover:bg-inset hover:text-ink"
    >
      <Icon name="pencil" size={15} />
      Change
    </button>
  )
}

/** The readiness list's table twin: every field, tests included. */
export function ReadinessTable({ items }: { items: ReadyItemDTO[] }) {
  const cell = 'px-3 py-2 text-small text-ink-2 align-top'
  const head = 'px-3 py-2.5 text-tag font-semibold tracking-caps-md text-ink-3 uppercase'
  return (
    <ScrollRegion label="Readiness table, scrolls sideways" className="border border-line">
      <table className="w-full min-w-[860px] border-collapse text-left">
        <caption className="sr-only">Every readiness item with its state, when and by whom it was set, its evidence and its tests.</caption>
        <thead>
          <tr className="bg-inset">
            {['Item', 'Kind', 'Organisation', 'State', 'Since', 'By', 'Evidence', 'Tests', 'Record'].map((h) => (
              <th key={h} scope="col" className={head}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sortItems(items).map((it) => (
            <tr key={it.id} className="border-t border-line">
              <th scope="row" className={`${cell} font-semibold text-ink`}>{it.name}</th>
              <td className={cell}>{KIND_WORDS[it.kind]}</td>
              <td className={cell}>{it.organisation ?? 'Not given'}</td>
              <td className={cell}>
                {READY_WORDS[it.state]}
                {it.blocked_reason ? `: ${it.blocked_reason}` : ''}
              </td>
              <td className={cell}>{when(it.changed_at) ?? 'Not recorded'}</td>
              <td className={cell}>{it.changed_by ?? 'Not recorded'}</td>
              <td className={cell}>{it.evidence_url ? <a href={it.evidence_url}>{hostWords(it.evidence_url)}</a> : 'None'}</td>
              <td className={cell}>
                {it.tests.length
                  ? it.tests
                      .map((t) => `${TEST_WORDS[t.kind]}: ${t.result === 'not_done' ? 'not done' : t.result}${t.date ? ` (${isoDateWords(t.date)})` : ''}`)
                      .join('; ')
                  : 'None recorded'}
              </td>
              <td className={cell}>{it.source === 'public' ? 'From the public record' : 'Entered by the team'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </ScrollRegion>
  )
}

// ---------------------------------------------------------------------------
// Risks: a grid per category, and a table. Never multiplied (ADR-17).
// ---------------------------------------------------------------------------

/**
 * Likelihood up the side, consequence along the bottom, one category at a
 * time. Each risk is a numbered mark with its trend arrow. The cells carry no
 * colour: shading cells by likelihood times consequence would be a score.
 */
export function RiskGrid({ risks, scale }: { risks: RiskDTO[]; scale: RiskScaleDTO | undefined }) {
  const cats = (['safety', 'technical', 'cost', 'schedule'] as RiskCategory[]).filter((c) =>
    risks.some((r) => r.ratings.some((x) => x.category === c)),
  )
  const [cat, setCat] = useState<RiskCategory>(cats[0] ?? 'technical')
  const levels = [1, 2, 3, 4, 5]
  const lWords = (n: number) => scale?.likelihood.find((l) => l.level === n)?.words
  const cWords = (n: number) => scale?.consequence.find((c) => c.category === cat)?.levels.find((l) => l.level === n)?.words
  const at = (l: number, c: number) =>
    risks
      .map((r, i) => ({ r, i, rating: r.ratings.find((x) => x.category === cat) }))
      .filter((x) => x.rating && x.rating.likelihood === l && x.rating.consequence === c)
  const placed = risks.filter((r) => r.ratings.some((x) => x.category === cat)).length

  return (
    <div className="flex flex-col gap-3">
      {cats.length > 1 && (
        <Segmented
          label="Consequence category"
          value={cat}
          onChange={setCat}
          options={cats.map((c) => ({ value: c, label: CATEGORY_WORDS[c] }))}
        />
      )}
      <div
        role="img"
        aria-label={`${CATEGORY_WORDS[cat]} risks by likelihood and consequence: ${placed} of ${risks.length} risks are rated for this category. ${risks
          .map((r, i) => {
            const x = r.ratings.find((y) => y.category === cat)
            return x ? `Risk ${i + 1}, ${r.title}: likelihood ${x.likelihood}, consequence ${x.consequence}, ${TREND_WORDS[r.trend].words.toLowerCase()}.` : ''
          })
          .join(' ')} The table lists every rating.`}
        className="grid grid-cols-[auto_repeat(5,minmax(0,1fr))] gap-px"
      >
        {[...levels].reverse().map((l) => (
          <div key={`row${l}`} className="contents">
            <div className="flex items-center justify-end pr-2 text-caption text-ink-3" title={lWords(l)}>
              {l}
            </div>
            {levels.map((c) => (
              <div key={c} className="flex min-h-12 flex-wrap content-start gap-1 border border-line bg-panel p-1">
                {at(l, c).map(({ r, i }) => (
                  <span
                    key={r.id}
                    title={`${r.title} (${TREND_WORDS[r.trend].words.toLowerCase()})`}
                    className="inline-flex h-6 items-center gap-0.5 bg-ink px-1.5 text-tag font-bold text-canvas"
                  >
                    {i + 1}
                    <span aria-hidden="true">{TREND_WORDS[r.trend].glyph}</span>
                  </span>
                ))}
              </div>
            ))}
          </div>
        ))}
        <div />
        {levels.map((c) => (
          <div key={`c${c}`} className="pt-1 text-center text-caption text-ink-3" title={cWords(c)}>
            {c}
          </div>
        ))}
      </div>
      <p className="text-caption leading-caption text-ink-3">
        Up: likelihood, 1 {lWords(1)?.toLowerCase() ?? 'least likely'} to 5 {lWords(5)?.toLowerCase() ?? 'most likely'}. Along:
        consequence, 1 {cWords(1)?.toLowerCase() ?? 'least'} to 5 {cWords(5)?.toLowerCase() ?? 'most'}. The two are never
        multiplied into a score.
      </p>
    </div>
  )
}

export function RiskTable({ risks, onChange }: { risks: RiskDTO[]; onChange?: (r: RiskDTO) => void }) {
  const cell = 'px-3 py-2 text-small text-ink-2 align-top'
  const head = 'px-3 py-2.5 text-tag font-semibold tracking-caps-md text-ink-3 uppercase'
  const rating = (r: RiskDTO, c: RiskCategory) => {
    const x = r.ratings.find((y) => y.category === c)
    return x ? `L ${x.likelihood} · C ${x.consequence}` : '—'
  }
  return (
    <ScrollRegion label="Risk table, scrolls sideways" className="border border-line">
      <table className="w-full min-w-[900px] border-collapse text-left">
        <caption className="sr-only">
          Every risk with its likelihood (L) and consequence (C) for each category, its trend, owner and mitigation.
        </caption>
        <thead>
          <tr className="bg-inset">
            {['#', 'Risk', 'Safety', 'Technical', 'Cost', 'Schedule', 'Trend', 'Owner', 'Mitigation'].map((h) => (
              <th key={h} scope="col" className={head}>
                {h}
              </th>
            ))}
            {onChange && (
              <th scope="col" className={head}>
                <span className="sr-only">Change</span>
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {risks.map((r, i) => (
            <tr key={r.id} className="border-t border-line">
              <td className={`${cell} font-mono`}>{i + 1}</td>
              <th scope="row" className={`${cell} text-left font-normal`}>
                <span className="block font-semibold text-ink">{r.title}</span>
                <span className="block">If {r.cause.charAt(0).toLowerCase() + r.cause.slice(1)}: {r.consequence_text.toLowerCase()}</span>
              </th>
              {(['safety', 'technical', 'cost', 'schedule'] as RiskCategory[]).map((c) => (
                <td key={c} className={`${cell} font-mono whitespace-nowrap`}>
                  {rating(r, c)}
                </td>
              ))}
              <td className={cell}>
                <span aria-hidden="true">{TREND_WORDS[r.trend].glyph} </span>
                {TREND_WORDS[r.trend].words}
              </td>
              <td className={cell}>{r.owner ?? 'No owner'}</td>
              <td className={cell}>{r.mitigation ?? 'None recorded'}</td>
              {onChange && (
                <td className="px-3 py-1">
                  <ChangeButton onClick={() => onChange(r)} name={r.title} />
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </ScrollRegion>
  )
}

// ---------------------------------------------------------------------------
// Parts
// ---------------------------------------------------------------------------

/** Parts, and for each one what stops working if it is lost (asked for on request). */
export function PartsTable({
  parts,
  items,
  onChange,
}: {
  parts: PartDTO[]
  items: ReadyItemDTO[]
  onChange?: (p: PartDTO) => void
}) {
  const [asked, setAsked] = useState<string | null>(null)
  const impact = usePartImpact(asked)
  const itemName = (id: string | null) => items.find((i) => i.id === id)?.name ?? (id ? 'Unknown item' : 'Not attached')
  return (
    <ul className="flex flex-col divide-y divide-line border-y border-line">
      {parts.map((p) => {
        const s = PART_WORDS[p.status]
        const bad = p.status === 'lost' || p.status === 'failed' || p.status === 'damaged'
        return (
          <li key={p.id} className="flex flex-col gap-2 py-3">
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <span className="text-body font-semibold text-ink">
                {p.name}
                {p.serial && <span className="font-mono text-caption font-normal text-ink-3"> · {p.serial}</span>}
              </span>
              <span className={`flex items-center gap-1.5 text-small ${bad ? 'font-semibold text-ink' : 'text-ink-2'}`}>
                <Icon name={s.icon} size={14} strokeWidth={2} />
                {s.words}
              </span>
            </div>
            <span className="text-caption text-ink-3">
              {[`Part of ${itemName(p.parent_item_id)}`, p.part_number, p.location].filter(Boolean).join(' · ')}
            </span>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="ghost" expanded={asked === p.id} onClick={() => setAsked(asked === p.id ? null : p.id)}>
                If this part is lost, what stops working?
              </Button>
              {onChange && <ChangeButton onClick={() => onChange(p)} name={`${p.name}${p.serial ? ` ${p.serial}` : ''}`} />}
            </div>
            {asked === p.id && (
              <div aria-live="polite" className="border-l-2 border-line-strong pl-3 text-small leading-5 text-ink-2">
                {impact.isPending ? (
                  'Following what depends on it…'
                ) : impact.error ? (
                  'This could not be worked out just now.'
                ) : impact.data?.stops_working.length ? (
                  <>
                    <span className="font-semibold text-ink">Stops working:</span>{' '}
                    {impact.data.stops_working.map((x) => x.name).join(', ')}.
                  </>
                ) : (
                  'Nothing else depends on it.'
                )}
              </div>
            )}
          </li>
        )
      })}
    </ul>
  )
}

// ---------------------------------------------------------------------------
// Landing history: counts, never a success probability (ADR-17)
// ---------------------------------------------------------------------------

export function landingCountsSentence(h: LandingHistoryDTO): string {
  const c = h.counts
  const first = h.attempts.length ? new Date(Date.parse(h.attempts.map((a) => a.date).sort()[0])).getUTCFullYear() : null
  return `${c.attempts} landing attempts${first ? ` since ${first}` : ''}: ${c.landed_working} landed and worked, ${c.landed_tipped_or_partial} landed tipped or partly working, ${c.failed} failed.`
}

export function LandingHistoryTable({ history }: { history: LandingHistoryDTO }) {
  const cell = 'px-3 py-2 text-small text-ink-2 align-top'
  const head = 'px-3 py-2.5 text-tag font-semibold tracking-caps-md text-ink-3 uppercase'
  return (
    <ScrollRegion label="Landing history, scrolls sideways" className="border border-line">
      <table className="w-full min-w-[720px] border-collapse text-left">
        <caption className="sr-only">Every Moon landing attempt since 2013, its outcome and its published cause.</caption>
        <thead>
          <tr className="bg-inset">
            {['Date', 'Mission', 'Agency', 'Outcome', 'Cause', 'Source'].map((h) => (
              <th key={h} scope="col" className={head}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {[...history.attempts]
            .sort((a, b) => b.date.localeCompare(a.date))
            .map((a) => {
              const o = OUTCOME_WORDS[a.outcome] ?? { words: a.outcome.replace(/_/g, ' '), glyph: '' }
              return (
                <tr key={`${a.mission}${a.date}`} className="border-t border-line">
                  <td className={`${cell} whitespace-nowrap`}>{isoDateWords(a.date)}</td>
                  <th scope="row" className={`${cell} font-semibold text-ink`}>{a.mission}</th>
                  <td className={cell}>{a.agency}</td>
                  <td className={cell}>
                    <span aria-hidden="true">{o.glyph} </span>
                    {o.words}
                  </td>
                  <td className={cell}>{a.cause ?? '—'}</td>
                  <td className={cell}>
                    {a.source_url ? (
                      <a href={a.source_url} target="_blank" rel="noreferrer">
                        {hostWords(a.source_url)}
                      </a>
                    ) : (
                      'Not given'
                    )}
                  </td>
                </tr>
              )
            })}
        </tbody>
      </table>
    </ScrollRegion>
  )
}
