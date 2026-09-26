import type { ContactDTO, LinkDTO, NodeDTO } from '../../lib/api/lifecycle'
import { dateTimeWords, shortDate } from '../../lib/format'
import { formatValue, quantityText } from '../../lib/lifecycle/quantity'
import { ScrollRegion } from '../ui'

const HOUR = 3_600_000

export interface ContactRow {
  link: LinkDTO
  from: NodeDTO | undefined
  to: NodeDTO | undefined
  /** A relay with no real orbit: its time is a range, not a timeline (ADR-16). */
  planned: boolean
  label: string
}

/** The chart's rows, in the order they are drawn: direct to stations, then relays. */
export function contactRows(c: ContactDTO): ContactRow[] {
  const node = (id: string) => c.nodes.find((n) => n.id === id)
  return c.links
    .map((link) => {
      const from = node(link.from)
      const to = node(link.to)
      const planned = [from, to].some((n) => n?.kind === 'relay' && n.orbit !== 'real')
      return { link, from, to, planned, label: `${from?.name ?? link.from} to ${to?.name ?? link.to}` }
    })
    .sort((a, b) => Number(a.planned) - Number(b.planned) || Number(a.to?.kind === 'relay') - Number(b.to?.kind === 'relay'))
}

/**
 * Who can hear whom, over these dates (design-lifecycle.md §4, Contact): one
 * row per link, cyan where it is up. A planned relay has no real timeline,
 * so its row is the −45° hatch across the dates with its range in words,
 * "if it flies as planned". Booked passes are outlined and labelled.
 *
 * Nothing moves, so this drawing is also its own reduced-motion version.
 */
export function ContactChart({ contact, rows, start, end }: { contact: ContactDTO; rows: ContactRow[]; start: number; end: number }) {
  const span = Math.max(1, end - start)
  const pct = (t: number) => `${(Math.min(Math.max(t, start), end) - start) / span * 100}%`
  const width = (a: number, b: number) => `${Math.max(0.3, ((Math.min(b, end) - Math.max(a, start)) / span) * 100)}%`
  const days = Math.max(1, Math.round(span / (24 * HOUR)))
  const tickEvery = days > 20 ? 7 : days > 8 ? 2 : 1
  const relayFor = (r: ContactRow) => contact.relays.find((x) => x.id === r.to?.id || x.id === r.from?.id)
  const label = `Contact over ${formatValue(span / (24 * HOUR))} days from ${dateTimeWords(start)}: ${rows
    .map((r) =>
      r.planned
        ? `${r.label}, ${quantityText(relayFor(r)?.adds_h)} somewhere in these dates if it flies as planned`
        : `${r.label}, ${r.link.stretches.length} passes`,
    )
    .join('; ')}. ${contact.bookings.length} booked passes. The table lists every pass.`

  return (
    <ScrollRegion label="Contact chart, scrolls sideways">
      <div className="flex min-w-[560px] flex-col" role="img" aria-label={label}>
        {rows.map((r) => {
          const booked = contact.bookings.filter((b) => b.station === r.to?.id || b.station === r.from?.id)
          const relay = relayFor(r)
          return (
            <div key={`${r.link.from}-${r.link.to}`} className="flex items-center border-t border-line first:border-t-0">
              <div className="w-44 shrink-0 py-2 pr-3 text-small leading-4 text-ink-2">
                <span className="block text-ink">{r.to?.name ?? r.link.to}</span>
                <span className="text-caption text-ink-3">
                  {r.to?.kind === 'relay' ? 'relay' : (r.to?.operator ?? '')}
                  {r.from?.kind === 'relay' ? ` · from ${r.from.name}` : ''}
                </span>
              </div>
              <div className="relative h-7 grow bg-dark-fill">
                {r.planned ? (
                  <>
                    <span className="hatch-uncertain absolute inset-0 border border-uncertain" />
                    <span className="absolute inset-y-0 left-2 flex items-center">
                      <span className="bg-panel px-1.5 text-caption font-semibold text-ink">
                        {relay ? `${quantityText(relay.adds_h)} somewhere in these dates, if it flies as planned` : 'If it flies as planned'}
                      </span>
                    </span>
                  </>
                ) : (
                  r.link.stretches.map((s) => {
                    const a = Date.parse(s.start)
                    const b = Date.parse(s.end)
                    return (
                      <span
                        key={s.start}
                        className="absolute inset-y-1 bg-earth-fill"
                        style={{ left: pct(a), width: width(a, b) }}
                        title={`${r.label}: ${dateTimeWords(a)} to ${dateTimeWords(b)}, ${formatValue((b - a) / HOUR)} h`}
                      />
                    )
                  })
                )}
                {booked.map((b) => {
                  const a = Date.parse(b.start)
                  const z = Date.parse(b.end)
                  return (
                    <span
                      key={b.start}
                      className="absolute -inset-y-0.5 border-2 border-ink"
                      style={{ left: pct(a), width: width(a, z) }}
                      title={`Booked by ${b.entered_by}: ${dateTimeWords(a)} to ${dateTimeWords(z)}`}
                    />
                  )
                })}
              </div>
            </div>
          )
        })}
        <div className="flex pt-1.5" aria-hidden="true">
          <div className="w-44 shrink-0" />
          <div className="relative h-4 grow">
            {Array.from({ length: Math.floor(days / tickEvery) + 1 }, (_, k) => k * tickEvery).map((d) => (
              <span
                key={d}
                className="absolute top-0 font-mono text-micro whitespace-nowrap text-ink-3"
                style={{ left: `${(d / Math.max(1, span / (24 * HOUR))) * 100}%`, transform: d ? 'translateX(-50%)' : undefined }}
              >
                {d === 0 ? shortDate(start) : `Day ${d}`}
              </span>
            ))}
          </div>
        </div>
      </div>
    </ScrollRegion>
  )
}

/** The contact chart's table twin: every pass, and every booked one. */
export function ContactTable({ contact, rows }: { contact: ContactDTO; rows: ContactRow[] }) {
  const cell = 'px-3 py-2 text-small text-ink-2 whitespace-nowrap'
  const head = 'px-3 py-2.5 text-tag font-semibold tracking-caps-md text-ink-3 uppercase'
  const passes = rows.flatMap((r) =>
    r.link.stretches.map((s) => {
      const a = Date.parse(s.start)
      const b = Date.parse(s.end)
      const booked = contact.bookings.some((x) => (x.station === r.to?.id || x.station === r.from?.id) && Date.parse(x.start) < b && Date.parse(x.end) > a)
      return { r, a, b, s, booked }
    }),
  )
  return (
    <ScrollRegion label="Contact table, scrolls sideways" className="border border-line">
      <table className="w-full min-w-[720px] border-collapse text-left">
        <caption className="sr-only">Every pass on every link over these dates, and whether a ground-station pass is booked over it.</caption>
        <thead>
          <tr className="bg-inset">
            {['Link', 'Start', 'End', 'Length', 'Booked'].map((h) => (
              <th key={h} scope="col" className={head}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {passes
            .sort((x, y) => x.a - y.a)
            .map(({ r, a, b, s, booked }) => (
              <tr key={`${r.label}${s.start}`} className="border-t border-line">
                <th scope="row" className={`${cell} font-semibold text-ink`}>{r.label}</th>
                <td className={cell}>{s.open_start ? `before ${dateTimeWords(a)}` : dateTimeWords(a)}</td>
                <td className={cell}>{s.open_end ? `after ${dateTimeWords(b)}` : dateTimeWords(b)}</td>
                <td className={`${cell} font-mono text-ink`}>
                  {s.open_start || s.open_end ? '≥' : ''}
                  {formatValue((b - a) / HOUR)} h
                </td>
                <td className={cell}>{booked ? 'Booked' : '—'}</td>
              </tr>
            ))}
          {rows
            .filter((r) => r.planned)
            .map((r) => (
              <tr key={`${r.label}planned`} className="border-t border-line">
                <th scope="row" className={`${cell} font-semibold text-ink`}>{r.label}</th>
                <td className={cell} colSpan={3}>
                  {quantityText(contact.relays.find((x) => x.id === r.to?.id || x.id === r.from?.id)?.adds_h)} somewhere in
                  these dates, if it flies as planned
                </td>
                <td className={cell}>—</td>
              </tr>
            ))}
        </tbody>
      </table>
    </ScrollRegion>
  )
}
