import type { ModelSystem, RuleRowDTO, ShareDTO } from '../../lib/api/lifecycle'
import { hostWords, quantityText, shareView } from '../../lib/lifecycle/quantity'
import { Icon } from '../Icon'
import { ScrollRegion } from '../ui'

export const SYSTEMS: { id: ModelSystem; name: string; runsNote: string }[] = [
  { id: 'GEFS', name: 'NOAA GEFS', runsNote: 'US ensemble' },
  { id: 'ECMWF-ENS', name: 'ECMWF ENS', runsNote: 'European ensemble' },
  { id: 'AIFS-ENS', name: 'ECMWF AIFS', runsNote: 'European machine-learning ensemble' },
]

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

function RuleCell({ row }: { row: RuleRowDTO }) {
  const checked = row.per_system.some((p) => p.share?.checked)
  return (
    <span className="flex flex-col gap-1">
      <span className="text-body leading-5 font-semibold text-ink">{row.text}</span>
      <span className="text-caption leading-caption text-ink-3">
        {CLASS_WORDS[row.class]}
        {row.class !== 'observation' && ` · ${checked ? 'checked against observations' : 'not yet checked against observations'}`}
        {' · '}
        <a href={row.source_url} target="_blank" rel="noreferrer">
          {hostWords(row.source_url)}
        </a>
      </span>
      {row.disagreement && (
        <span className="flex items-center gap-1.5 text-caption font-semibold text-ink">
          <Icon name="uncertain" size={14} strokeWidth={2.2} />
          Models disagree
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

function OtherCell({ row }: { row: RuleRowDTO }) {
  const lines: { key: string; lead?: string; text: string; strong?: boolean }[] = []
  for (const f of row.one_forecast) {
    lines.push({ key: f.system, text: `${f.system} forecast: ${quantityText(f.value)}, ${f.over ? 'over the limit' : 'under the limit'}` })
  }
  if (row.observed) {
    const w = observedWords(row.observed)
    lines.push({ key: 'observed', lead: w.lead, text: w.detail, strong: row.observed.state === 'seen' })
  }
  if (row.climatology) {
    const c = row.climatology
    lines.push({ key: 'climatology', lead: `Past years (${c.years}): over the limit ${percentWords(c.share)} of the time.`, text: c.source })
  }
  if (!lines.length) return <span className="text-small text-ink-3">—</span>
  return (
    <ul className="flex flex-col gap-1.5">
      {lines.map((l) => (
        <li key={l.key} className="text-small leading-5 text-ink-2">
          {l.lead && <span className={`font-semibold ${l.strong ? 'text-ink' : 'text-ink-2'}`}>{l.lead} </span>}
          {l.text}
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

/** The row's closed-state summary: "4 rules; models disagree on 1". Never a total chance. */
export function rulesSummary(rules: RuleRowDTO[]): string {
  const d = rules.filter((r) => r.disagreement).length
  return `${rules.length} rule${rules.length === 1 ? '' : 's'}${d ? `; models disagree on ${d}` : ''}`
}
