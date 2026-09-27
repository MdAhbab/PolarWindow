import type { QuantityDTO } from '../../lib/api/lifecycle'
import { formatValue, quantityText, unitWords } from '../../lib/lifecycle/quantity'
import { Icon } from '../Icon'
import { ScrollRegion } from '../ui'

export interface LimitRow {
  id: string
  label: string
  value: QuantityDTO | null
  limit: QuantityDTO | null
}

/** Over the team's limit, counting the margin: certainly over, or not certainly. */
export function overBy(r: LimitRow): number | null {
  if (r.value?.value == null || r.limit?.value == null) return null
  const d = r.value.value - r.limit.value
  return d > 0 ? d : null
}

/**
 * Each measure against the team's limit (design-lifecycle.md §4, Return):
 * the value as a bar with its ± hatched, the limit as an ink rule. Over the
 * limit is magenta and a triangle and the words (invariant 4). No limit
 * entered: the bar alone, and it says so.
 *
 * Nothing moves, so this is also its own reduced-motion version.
 */
export function LimitBars({ rows }: { rows: LimitRow[] }) {
  return (
    <ul className="flex flex-col gap-4" aria-label="Measures against the team’s limits">
      {rows.map((r) => {
        const v = r.value?.value ?? null
        const pm = r.value?.pm ?? 0
        const lim = r.limit?.value ?? null
        const max = Math.max(1e-9, ...[v !== null ? v + pm : 0, lim ?? 0].map((x) => x * 1.25))
        const over = overBy(r)
        const unit = unitWords(r.value?.unit ?? r.limit?.unit ?? '').short
        return (
          <li key={r.id} className="flex flex-col gap-1.5">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3">
              <span className="text-small font-semibold text-ink">{r.label}</span>
              <span className={`flex items-center gap-1.5 text-small ${over ? 'font-semibold text-alert' : 'text-ink-2'}`}>
                {over && <Icon name="alert" size={14} strokeWidth={2.2} />}
                {v === null
                  ? (r.value?.missing_reason ?? 'No forecast')
                  : over
                    ? `${quantityText(r.value)}: ${formatValue(over)} ${unit} over the team’s limit`
                    : lim !== null
                      ? `${quantityText(r.value)}, under the team’s limit of ${quantityText(r.limit)}`
                      : `${quantityText(r.value)}; no limit entered by the team`}
              </span>
            </div>
            <div className="relative h-4 bg-dark-fill" aria-hidden="true">
              {v !== null && (
                <>
                  <span className="absolute inset-y-0 left-0 bg-terrain-high" style={{ width: `${(Math.max(0, v - pm) / max) * 100}%` }} />
                  {over !== null && lim !== null && (
                    <span className="hatch-alert absolute inset-y-0" style={{ left: `${(lim / max) * 100}%`, width: `${((v - lim) / max) * 100}%` }} />
                  )}
                  {pm > 0 && (
                    <span
                      className="hatch-uncertain absolute inset-y-0"
                      style={{ left: `${(Math.max(0, v - pm) / max) * 100}%`, width: `${((Math.min(max, v + pm) - Math.max(0, v - pm)) / max) * 100}%` }}
                    />
                  )}
                  <span className="absolute inset-y-0 w-0.5 bg-ink-2" style={{ left: `${(v / max) * 100}%` }} />
                </>
              )}
              {lim !== null && <span className="absolute -inset-y-1 w-[3px] bg-ink" style={{ left: `${(lim / max) * 100}%` }} />}
            </div>
          </li>
        )
      })}
    </ul>
  )
}

/** The bars' table twin. */
export function LimitTable({ rows }: { rows: LimitRow[] }) {
  const cell = 'px-3 py-2 text-small text-ink-2'
  const head = 'px-3 py-2.5 text-tag font-semibold tracking-caps-md text-ink-3 uppercase'
  return (
    <ScrollRegion label="Limits table, scrolls sideways" className="border border-line">
      <table className="w-full min-w-[640px] border-collapse text-left">
        <caption className="sr-only">Each measure, its value and margin, the team’s limit, who entered it, and whether the value is over it.</caption>
        <thead>
          <tr className="bg-inset">
            {['Measure', 'Value', 'Team limit', 'Limit entered by', 'Over the limit'].map((h) => (
              <th key={h} scope="col" className={head}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-t border-line">
              <th scope="row" className={`${cell} font-semibold text-ink`}>{r.label}</th>
              <td className={`${cell} font-mono`}>{r.value?.value != null ? quantityText(r.value) : 'none'}</td>
              <td className={`${cell} font-mono`}>{r.limit?.value != null ? quantityText(r.limit) : 'none entered'}</td>
              <td className={cell}>{r.limit?.value != null ? (r.limit.source ?? 'the team') : '—'}</td>
              <td className={cell}>{overBy(r) !== null ? 'Yes' : r.limit?.value != null && r.value?.value != null ? 'No' : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </ScrollRegion>
  )
}
