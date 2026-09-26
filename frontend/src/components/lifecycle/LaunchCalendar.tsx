import type { OpportunityDTO } from '../../lib/api/lifecycle'
import { clockWords, durationMargin, quantityText } from '../../lib/lifecycle/quantity'
import { dateWords } from '../../lib/format'
import { ScrollRegion } from '../ui'

const DAY = 86_400_000
const WEEKDAY = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTH = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

const t0ms = (o: OpportunityDTO) => (o.t0.value ?? 0) * 1000
const dayOf = (ms: number) => Math.floor(ms / DAY) * DAY

function dayLabel(ms: number): string {
  const d = new Date(ms)
  return `${WEEKDAY[d.getUTCDay()]} ${d.getUTCDate()} ${MONTH[d.getUTCMonth()]}`
}

/** A short pad name for a crowded mark: "LC-39A" → "39A". */
function padShort(name: string): string {
  const m = name.match(/(\d+[A-Z]?)$/)
  return m ? m[1] : name
}

/** The opportunities grouped by UTC day, with runs of empty days between them. */
export function calendarDays(opps: OpportunityDTO[]): ({ kind: 'day'; day: number; opps: OpportunityDTO[] } | { kind: 'gap'; days: number })[] {
  const sorted = [...opps].filter((o) => o.t0.value !== null).sort((a, b) => t0ms(a) - t0ms(b))
  const out: ({ kind: 'day'; day: number; opps: OpportunityDTO[] } | { kind: 'gap'; days: number })[] = []
  let last: number | null = null
  for (const o of sorted) {
    const d = dayOf(t0ms(o))
    if (last !== null && d === last) {
      ;(out[out.length - 1] as { opps: OpportunityDTO[] }).opps.push(o)
      continue
    }
    if (last !== null && d - last > DAY) out.push({ kind: 'gap', days: Math.round((d - last) / DAY) - 1 })
    out.push({ kind: 'day', day: d, opps: [o] })
    last = d
  }
  return out
}

export function opportunityName(o: OpportunityDTO): string {
  const ms = t0ms(o)
  return `${dateWords(ms)}, ${clockWords(o.t0.value ?? 0)}${o.t0.pm !== null ? ` ${durationMargin(o.t0.pm)}` : ''}, from ${o.pad_name}`
}

/**
 * The launch calendar (design-lifecycle.md §4, Launch): one row per day that
 * has an opportunity, a 24-hour track, and each opportunity a button at its
 * time. A launch period is a thin bar from its opening to its close. Choosing
 * one sets the four numbers and the weather row. Runs of days with none
 * collapse into one line, so the calendar stays as short as the answer.
 *
 * Nothing moves: this is also its own reduced-motion version.
 */
export function LaunchCalendar({
  opportunities,
  selected,
  onSelect,
}: {
  opportunities: OpportunityDTO[]
  selected: string | null
  onSelect: (id: string) => void
}) {
  const rows = calendarDays(opportunities)
  const pads = new Set(opportunities.map((o) => o.pad_id))
  return (
    <ScrollRegion label="Launch calendar, scrolls sideways">
      <div className="flex min-w-[520px] flex-col" role="group" aria-label="Launch opportunities by day">
        {/* Hours of the day, UTC. */}
        <div className="flex pb-1" aria-hidden="true">
          <div className="w-20 shrink-0 sm:w-28" />
          <div className="relative h-4 grow">
            {[0, 6, 12, 18, 24].map((h) => (
              <span
                key={h}
                className="absolute top-0 font-mono text-micro text-ink-3"
                style={{ left: `${(h / 24) * 100}%`, transform: h === 24 ? 'translateX(-100%)' : h ? 'translateX(-50%)' : undefined }}
              >
                {String(h).padStart(2, '0')}:00
              </span>
            ))}
          </div>
        </div>
        {rows.map((r, i) =>
          r.kind === 'gap' ? (
            <div key={`gap${i}`} className="flex border-t border-line py-1.5">
              <div className="w-20 shrink-0 sm:w-28" />
              <p className="text-caption text-ink-3">
                No opportunity for {r.days} day{r.days === 1 ? '' : 's'}
              </p>
            </div>
          ) : (
            <div key={r.day} className="flex items-stretch border-t border-line">
              <div className="flex w-20 shrink-0 sm:w-28 items-center text-small font-medium text-ink-2">{dayLabel(r.day)}</div>
              <div className="relative h-14 grow">
                {[6, 12, 18].map((h) => (
                  <span key={h} aria-hidden="true" className="absolute inset-y-0 w-px bg-line" style={{ left: `${(h / 24) * 100}%` }} />
                ))}
                {r.opps.map((o) => {
                  const ms = t0ms(o)
                  const f = (ms - r.day) / DAY
                  const on = o.id === selected
                  const open = o.window_open ? (Date.parse(o.window_open) - r.day) / DAY : null
                  const close = o.window_close ? (Date.parse(o.window_close) - r.day) / DAY : null
                  const pm = o.t0.pm !== null ? o.t0.pm / 86400 : 0
                  // Kept inside the track: a mark near midnight hangs inward.
                  const anchor = f < 0.08 ? 'translateX(0)' : f > 0.92 ? 'translateX(-100%)' : 'translateX(-50%)'
                  return (
                    <div key={o.id}>
                      {open !== null && close !== null && (
                        <span
                          aria-hidden="true"
                          className="absolute top-1/2 h-0.5 -translate-y-1/2 bg-ink-3"
                          style={{ left: `${Math.max(0, open) * 100}%`, width: `${Math.max(0.3, (Math.min(1, close) - Math.max(0, open)) * 100)}%` }}
                        />
                      )}
                      {pm > 0 && (
                        <span
                          aria-hidden="true"
                          className="hatch-uncertain absolute top-1 bottom-1"
                          style={{ left: `${Math.max(0, f - pm) * 100}%`, width: `${Math.max(0.4, 2 * pm * 100)}%` }}
                        />
                      )}
                      <button
                        type="button"
                        aria-pressed={on}
                        aria-label={`${opportunityName(o)}${o.kind === 'window' ? ', a launch period' : ''}`}
                        onClick={() => onSelect(o.id)}
                        className={`absolute top-1 h-12 rounded-control border px-2.5 font-mono text-small font-semibold whitespace-nowrap ${
                          on ? 'border-ink bg-ink text-canvas' : 'border-line-strong bg-panel text-ink hover:bg-inset'
                        }`}
                        style={{ left: `${f * 100}%`, transform: anchor }}
                      >
                        {clockWords(o.t0.value ?? 0).replace(' UTC', '')}
                        {pads.size > 1 ? ` · ${padShort(o.pad_name)}` : ''}
                      </button>
                    </div>
                  )
                })}
              </div>
            </div>
          ),
        )}
      </div>
    </ScrollRegion>
  )
}

/** The calendar's table twin: every opportunity and what landing it would give. */
export function LaunchTable({ opportunities }: { opportunities: OpportunityDTO[] }) {
  const cell = 'px-3 py-2 text-small text-ink-2 whitespace-nowrap'
  const head = 'px-3 py-2.5 text-tag font-semibold tracking-caps-md text-ink-3 uppercase'
  const sorted = [...opportunities].sort((a, b) => t0ms(a) - t0ms(b))
  return (
    <ScrollRegion label="Launch opportunities table, scrolls sideways" className="border border-line">
      <table className="w-full min-w-[980px] border-collapse text-left">
        <caption className="sr-only">Every launch opportunity in these dates, and the landing each one gives.</caption>
        <thead>
          <tr className="bg-inset">
            {['Day', 'Launch time', 'Pad', 'Kind', 'Flight time', 'Landing', 'Sun height', 'Sunlight after', 'Earth up', 'Weather'].map((h) => (
              <th key={h} scope="col" className={head}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((o) => (
            <tr key={o.id} className="border-t border-line">
              <td className={cell}>{dayLabel(dayOf(t0ms(o)))}</td>
              <th scope="row" className={`${cell} font-mono font-semibold text-ink`}>
                {clockWords(o.t0.value ?? 0)}
                {o.t0.pm !== null ? ` ${durationMargin(o.t0.pm)}` : ''}
              </th>
              <td className={cell}>{o.pad_name}</td>
              <td className={cell}>{o.kind === 'window' ? 'Launch period' : 'One instant'}</td>
              <td className={`${cell} font-mono`}>{quantityText(o.transfer.flight_days)}</td>
              <td className={cell}>{quantityText(o.landing.time)}</td>
              <td className={`${cell} font-mono`}>{quantityText(o.landing.sun_elevation_deg)}</td>
              <td className={`${cell} font-mono`}>{quantityText(o.landing.sunlight_after_h)}</td>
              <td className={cell}>{o.landing.earth_up ? 'Yes' : 'No'}</td>
              <td className={cell}>{o.weather === 'forecast' ? 'Forecast' : o.weather === 'climatology' ? 'History only' : 'None'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </ScrollRegion>
  )
}
