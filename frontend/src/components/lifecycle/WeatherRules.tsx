import type { ModelSystem, RuleRowDTO, ShareDTO } from '../../lib/api/lifecycle'
import { hostWords, quantityView, shareView } from '../../lib/lifecycle/quantity'
import { Icon } from '../Icon'
import { ScrollRegion } from '../ui'

export const SYSTEMS: { id: ModelSystem; name: string; runsNote: string }[] = [
  { id: 'GEFS', name: 'NOAA GEFS', runsNote: 'US ensemble' },
  { id: 'ECMWF-ENS', name: 'ECMWF ENS', runsNote: 'European ensemble' },
  { id: 'AIFS-ENS', name: 'ECMWF AIFS', runsNote: 'European machine-learning ensemble' },
]

/** A single forecast, named as people know it, with its acronym spelled out where it first appears. */
export const FORECAST_NAMES: Record<RuleRowDTO['one_forecast'][number]['system'], string> = {
  NWS: 'National Weather Service (NWS)',
  HRRR: 'High-Resolution Rapid Refresh (HRRR)',
  'GEOS-FP': 'GEOS-FP, NASA’s global model',
}

/** What a forecast model can say about a rule (ADR-14), in words. */
export const CLASS_WORDS: Record<RuleRowDTO['class'], string> = {
  model: 'A forecast model can answer this',
  proxy: 'The model sees the ingredients only',
  observation: 'Observation only: no forecast number',
}

/**
 * A share of runs as a small bar: filled to k of n, with its 95 % range
 * hatched. Neutral ink: a share is evidence, not an alarm.
 */
function ShareBar({ share }: { share: ShareDTO }) {
  const f = share.k / share.n
  return (
    <span className="relative flex h-2 w-20 bg-dark-fill" aria-hidden="true">
      <span className="bg-ink-2" style={{ width: `${f * 100}%` }} />
      <span
        className="hatch-uncertain absolute inset-y-0"
        style={{ left: `${share.lo * 100}%`, width: `${Math.max(1, (share.hi - share.lo) * 100)}%` }}
      />
    </span>
  )
}

function SystemCell({ row, system, proxy }: { row: RuleRowDTO; system: ModelSystem; proxy: boolean }) {
  const cell = row.per_system.find((p) => p.system === system)
  if (!cell) return <span className="text-small text-ink-3">Not used for this rule</span>
  if (!cell.share) return <span className="text-small text-ink-3">{cell.missing_reason ?? 'No answer'}</span>
  const v = shareView(cell.share)
  const share = cell.share
  return (
    <span className="flex flex-col gap-1">
      <span className="text-small font-semibold text-ink tnum" aria-hidden="true">
        {share.k} of {share.n}
      </span>
      <span className="sr-only">{v.count}</span>
      <ShareBar share={cell.share} />
      <span className="text-caption leading-caption text-ink-3">{v.range}</span>
      <span className="sr-only">
        {proxy ? 'see the ingredients for this rule' : 'break the rule'}, {v.checked}
      </span>
    </span>
  )
}

/**
 * Whether the shares a rule shows have been checked against observations
 * (invariant 12): one phrase when they all have or none has, by system when
 * they differ; null when the rule shows no share.
 */
export function checkWords(row: Pick<RuleRowDTO, 'per_system'>): string | null {
  const shown = row.per_system.filter((p) => p.share)
  if (!shown.length) return null
  const done = shown.filter((p) => p.share?.checked)
  if (done.length === shown.length) return 'checked against observations'
  if (!done.length) return 'not yet checked against observations'
  const name = (p: (typeof shown)[number]) => SYSTEMS.find((s) => s.id === p.system)?.name ?? p.system
  return `checked against observations for ${done.map(name).join(' and ')}, not yet for ${shown.filter((p) => !p.share?.checked).map(name).join(' and ')}`
}

function RuleCell({ row }: { row: RuleRowDTO }) {
  const checked = checkWords(row)
  return (
    <span className="flex flex-col gap-1">
      <span className="text-body leading-5 font-semibold text-ink">{row.text}</span>
      <span className="text-caption leading-caption text-ink-3">
        {CLASS_WORDS[row.class]}
        {checked && ` · ${checked}`}
        {' · '}
        <a href={row.source_url} target="_blank" rel="noreferrer">
          {hostWords(row.source_url)}
        </a>
      </span>
      {(row.disagreement || row.disagreement_note) && (
        <span className="flex flex-col gap-0.5">
          <span className="flex items-center gap-1.5 text-caption font-semibold text-ink">
            <Icon name="uncertain" size={14} strokeWidth={2.2} />
            Models disagree
          </span>
          {row.disagreement_note && <span className="text-small leading-5 text-ink-2">{row.disagreement_note}</span>}
        </span>
      )}
    </span>
  )
}

/** A share as a percentage with enough digits to tell a small one from none: "0.4%", "12%". */
export function percentWords(share: number): string {
  const pct = share * 100
  if (pct === 0) return '0%'
  return `${pct < 10 ? pct.toFixed(1) : Math.round(pct)}%`
}

/** What was seen (lightning from space: clear or seen now, never at the launch time); with nothing seen, only why. */
export function observedWords(o: NonNullable<RuleRowDTO['observed']>): { lead?: string; detail: string } {
  if (o.state === 'clear') return { lead: 'Seen now: clear.', detail: o.detail }
  if (o.state === 'seen') return { lead: 'Seen now:', detail: o.detail }
  return { detail: o.detail }
}

/**
 * Past years in words: a wind rule's share over its limit, or, for a lightning
 * rule (seen, not forecast), how often thunder could be heard at the pad.
 */
export function climatologyWords(row: Pick<RuleRowDTO, 'class' | 'climatology'>): string {
  const c = row.climatology
  if (!c) return ''
  return row.class === 'observation'
    ? `Past years (${c.years}): thunder could be heard at the pad ${percentWords(c.share)} of the time.`
    : `Past years (${c.years}): over the limit ${percentWords(c.share)} of the time.`
}

/**
 * One forecast in words, the answer first: "National Weather Service (NWS)
 * forecast: 5.87 mph, under the limit", then how the number was made (it has
 * no margin, and says why) and how that forecast did against a station's
 * record, or why it cannot be checked (the service's `note`).
 */
export function forecastLine(f: RuleRowDTO['one_forecast'][number]): { lead: string; answer: string; how: string | null; note: string | null } {
  const v = quantityView(f.value)
  return {
    lead: `${FORECAST_NAMES[f.system] ?? f.system} forecast:`,
    answer: `${v.sentence}, ${f.over ? 'over the limit' : 'under the limit'}.`,
    how: v.noMarginReason ?? null,
    note: f.note,
  }
}

function OtherCell({ row }: { row: RuleRowDTO }) {
  const lines: { key: string; lead?: string; text: string; strong?: boolean; captions?: string[] }[] = []
  for (const f of row.one_forecast) {
    const l = forecastLine(f)
    lines.push({ key: f.system, lead: l.lead, text: l.answer, strong: true, captions: [l.how, l.note].filter((x): x is string => Boolean(x)) })
  }
  if (row.observed) {
    const w = observedWords(row.observed)
    lines.push({ key: 'observed', lead: w.lead, text: w.detail, strong: row.observed.state === 'seen' })
  }
  if (row.climatology) lines.push({ key: 'climatology', lead: climatologyWords(row), text: row.climatology.source })
  if (!lines.length) return <span className="text-small text-ink-3">—</span>
  return (
    <ul className="flex flex-col gap-2">
      {lines.map((l) => (
        <li key={l.key} className="text-small leading-5 text-ink-2">
          {l.lead && <span className={`font-semibold ${l.strong ? 'text-ink' : 'text-ink-2'}`}>{l.lead} </span>}
          {l.text}
          {l.captions?.map((c) => (
            <span key={c} className="mt-0.5 block text-caption leading-caption text-ink-3">
              {c}
            </span>
          ))}
        </li>
      ))}
    </ul>
  )
}

/**
 * The weather rules for one launch opportunity (ADR-14): each rule on its
 * own row, each forecast system in its own column, never pooled and never
 * added up. A share says its sample and whether it has been checked
 * (invariant 12). A table from 768 px, one card per rule below it.
 */
export function WeatherRuleTable({ rules }: { rules: RuleRowDTO[] }) {
  const head = 'px-3 py-2.5 text-tag font-semibold tracking-caps-md text-ink-3 uppercase align-bottom'
  return (
    <>
      <div className="hidden md:block">
        <ScrollRegion label="Weather rules, scrolls sideways" className="border border-line">
          <table className="w-full min-w-[860px] border-collapse text-left">
            <caption className="sr-only">
              Each launch weather rule, the share of runs of each forecast system that break it at the launch time, one
              forecast, what was seen, and how often it happened in past years.
            </caption>
            <thead>
              <tr className="bg-inset">
                <th scope="col" className={`${head} w-[34%]`}>
                  Rule
                </th>
                {SYSTEMS.map((s) => (
                  <th key={s.id} scope="col" className={head}>
                    {s.name}
                    <span className="block font-normal tracking-normal normal-case">model runs that break it</span>
                  </th>
                ))}
                <th scope="col" className={head}>
                  One forecast, what was seen, past years
                </th>
              </tr>
            </thead>
            <tbody>
              {rules.map((r) => (
                <tr key={r.id} className="border-t border-line align-top">
                  <th scope="row" className="px-3 py-3 text-left font-normal">
                    <RuleCell row={r} />
                  </th>
                  {SYSTEMS.map((s) => (
                    <td key={s.id} className="px-3 py-3">
                      {r.class === 'observation' ? (
                        <span className="text-small text-ink-3">No forecast number</span>
                      ) : (
                        <SystemCell row={r} system={s.id} proxy={r.class === 'proxy'} />
                      )}
                    </td>
                  ))}
                  <td className="px-3 py-3">
                    <OtherCell row={r} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollRegion>
      </div>
      <ul className="flex flex-col divide-y divide-line border-y border-line md:hidden" aria-label="Weather rules">
        {rules.map((r) => (
          <li key={r.id} className="flex flex-col gap-3 py-3">
            <RuleCell row={r} />
            {r.class !== 'observation' && (
              <dl className="grid grid-cols-[max-content_1fr] items-start gap-x-4 gap-y-2">
                {SYSTEMS.map((s) => (
                  <div key={s.id} className="contents">
                    <dt className="text-caption font-semibold text-ink-3">{s.name}</dt>
                    <dd>
                      <SystemCell row={r} system={s.id} proxy={r.class === 'proxy'} />
                    </dd>
                  </div>
                ))}
              </dl>
            )}
            <OtherCell row={r} />
          </li>
        ))}
      </ul>
    </>
  )
}

/**
 * The row's closed-state summary: "4 rules; models disagree on 1; 1 checked
 * against observations". Never a total chance. A rule is checked when a share
 * of its model runs has been (`share.checked`).
 */
export function rulesSummary(rules: RuleRowDTO[]): string {
  const d = rules.filter((r) => r.disagreement).length
  const c = rules.filter((r) => r.per_system.some((p) => p.share?.checked)).length
  return `${rules.length} rule${rules.length === 1 ? '' : 's'}${d ? `; models disagree on ${d}` : ''}${c ? `; ${c} checked against observations` : ''}`
}
