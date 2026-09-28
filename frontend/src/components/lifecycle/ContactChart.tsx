import type { ContactDTO, LinkDTO, NodeDTO, RelayLaunchStatus, RelayRowDTO } from '../../lib/api/lifecycle'
import { dateTimeWords, shortDate } from '../../lib/format'
import { formatValue, quantityText } from '../../lib/lifecycle/quantity'
import { ScrollRegion } from '../ui'

const HOUR = 3_600_000

export interface ContactRow {
  key: string
  label: string
  caption: string
  /** The links drawn on this row: one antenna, or every antenna of one complex. */
  links: LinkDTO[]
  /** Ground-station ids on this row, for its booked passes. */
  stations: string[]
  /** A relay with no real orbit: its time is a range, not a timeline (ADR-16). */
  planned: boolean
  relayId?: string
  /** An orbiter already flying: it could see the lander, but carries none of its data. */
  orbiter?: boolean
}

/** A relay's launch status in words, with a glyph beside them (never the glyph alone). */
export const RELAY_STATUS: Record<RelayLaunchStatus, { words: string; glyph: string }> = {
  operating: { words: 'In orbit', glyph: '●' },
  planned: { words: 'Planned, not launched', glyph: '○' },
  not_launched: { words: 'Not launched', glyph: '○' },
  launched_not_operating: { words: 'Launched, not working', glyph: '◐' },
}

/** A relay's launch status: the catalogue's (`launch_status`), else its node's. */
export function relayState(c: ContactDTO, id: string): { words: string; glyph: string } | null {
  const s = c.relays.find((r) => r.id === id)?.launch_status ?? c.nodes.find((n) => n.id === id)?.status
  return s ? RELAY_STATUS[s] : null
}

/** A planned relay's row in words: its range "if it flies as planned", or why it is not worked out. */
export function plannedWords(r: RelayRowDTO | undefined): string {
  if (!r) return 'If it flies as planned'
  const q = r.adds_h
  if (q.value === null && (q.lo === null || q.hi === null)) return `Not worked out: ${q.missing_reason ?? 'no orbit to work from'}`
  return `${quantityText(q)} somewhere in these dates, if it flies as planned`
}

/** The words that say an orbiter is not a relay for this lander. */
export const ORBITER_CAPTION = 'could see the lander; not a relay'

/**
 * The Deep Space Network's three complexes, by antenna number (DSS-1x and
 * 2x Goldstone, 3x and 4x Canberra, 5x and 6x Madrid). Their antennas see
 * the Moon at nearly the same times, so the chart draws one row per complex;
 * the table lists every antenna.
 */
export function complexOf(n: NodeDTO | undefined): { key: string; name: string } | null {
  const m = n?.id.match(/^dss-(\d+)$/i)
  if (!m) return null
  const k = Number(m[1])
  if (k >= 10 && k < 30) return { key: 'goldstone', name: 'Goldstone, California' }
  if (k >= 30 && k < 50) return { key: 'canberra', name: 'Canberra, Australia' }
  if (k >= 50 && k < 70) return { key: 'madrid', name: 'Madrid, Spain' }
  return null
}

/**
 * The chart's rows, in the order they are drawn: ground stations, then
 * relays, then orbiters that could see the lander (they carry none of its data).
 */
export function contactRows(c: ContactDTO): ContactRow[] {
  const node = (id: string) => c.nodes.find((n) => n.id === id)
  const rows = new Map<string, ContactRow>()
  for (const link of c.links) {
    const from = node(link.from)
    const to = node(link.to)
    const relay = [from, to].find((n) => n?.kind === 'relay')
    const planned = Boolean(relay && relay.orbit !== 'real')
    const complex = complexOf(to)
    const key = complex ? complex.key : `${link.from}-${link.to}`
    const row = rows.get(key)
    if (row) {
      row.links.push(link)
      if (to?.kind === 'station') row.stations.push(to.id)
      row.caption = `Deep Space Network, ${row.links.length} antennas`
      continue
    }
    rows.set(key, {
      key,
      label: complex ? complex.name : relay ? relay.name : (to?.name ?? link.to),
      caption: complex
        ? 'Deep Space Network, 1 antenna'
        : relay
          ? `relay${from?.kind === 'relay' ? ` to ${to?.name ?? link.to}` : ''} · ${(relayState(c, relay.id)?.words ?? relay.status).toLowerCase()}`
          : (to?.operator ?? ''),
      links: [link],
      stations: to?.kind === 'station' ? [to.id] : [],
      planned,
      relayId: relay?.id,
    })
  }
  // Links are direct only once relays are worked out (net-4): a relay with no link is its own planned row.
  for (const r of c.relays) {
    if ([...rows.values()].some((x) => x.relayId === r.id)) continue
    rows.set(`relay-${r.id}`, {
      key: `relay-${r.id}`,
      label: r.name,
      caption: `relay · ${(relayState(c, r.id)?.words ?? 'status not given').toLowerCase()}`,
      links: [],
      stations: [],
      planned: true,
      relayId: r.id,
    })
  }
  // Orbiters already flying: their passes are the row's one link, lander to orbiter.
  for (const o of c.orbiters ?? []) {
    rows.set(`orbiter-${o.id}`, {
      key: `orbiter-${o.id}`,
      label: o.name,
      caption: ORBITER_CAPTION,
      links: [{ from: 'lander', to: o.id, stretches: o.passes, data_rate_kbps: null, margin_db: null }],
      stations: [],
      planned: false,
      orbiter: true,
    })
  }
  const rank = (r: ContactRow) => (r.orbiter ? 3 : r.planned ? 2 : r.relayId ? 1 : 0)
  return [...rows.values()].sort((a, b) => rank(a) - rank(b))
}

/** Every stretch of a row's links, merged where they overlap: when any antenna on the row can hear. */
export function rowStretches(r: ContactRow): { start: number; end: number }[] {
  const all = r.links
    .flatMap((l) => l.stretches.map((s) => ({ start: Date.parse(s.start), end: Date.parse(s.end) })))
    .sort((a, b) => a.start - b.start)
  const out: { start: number; end: number }[] = []
  for (const s of all) {
    const last = out[out.length - 1]
    if (last && s.start <= last.end) last.end = Math.max(last.end, s.end)
    else out.push({ ...s })
  }
  return out
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
  const relayFor = (r: ContactRow) => contact.relays.find((x) => x.id === r.relayId)
  const label = `Who can hear the lander over ${formatValue(span / HOUR)} hours from ${dateTimeWords(start)}: ${rows
    .map((r) =>
      r.planned
        ? `${r.label}, ${plannedWords(relayFor(r))}`
        : `${r.label}${r.orbiter ? ` (${ORBITER_CAPTION})` : ''}, ${rowStretches(r).length} ${r.orbiter ? 'pass' : 'stretch'}${rowStretches(r).length === 1 ? '' : 'es'}`,
    )
    .join('; ')}. ${contact.bookings.length} booked passes. The table lists every pass of every antenna.`

  return (
    <ScrollRegion label="Contact chart, scrolls sideways">
      <div className="flex min-w-[560px] flex-col" role="img" aria-label={label}>
        {rows.map((r) => {
          const booked = contact.bookings.filter((b) => r.stations.includes(b.station))
          const relay = relayFor(r)
          return (
            <div key={r.key} className="flex items-center border-t border-line first:border-t-0">
              <div className="w-44 shrink-0 py-2 pr-3 text-small leading-4 text-ink-2">
                <span className="block text-ink">{r.label}</span>
                <span className="text-caption text-ink-3">{r.caption}</span>
              </div>
              <div className="relative h-7 grow bg-dark-fill">
                {r.planned ? (
                  <>
                    <span className="hatch-uncertain absolute inset-0 border border-uncertain" />
                    <span className="absolute inset-y-0 left-2 flex items-center">
                      <span className="bg-panel px-1.5 text-caption font-semibold text-ink">
                        {plannedWords(relay)}
                      </span>
                    </span>
                  </>
                ) : (
                  rowStretches(r).map(({ start: a, end: b }) => {
                    return (
                      <span
                        key={a}
                        // An orbiter's pass is an outline: it could see the lander, but carries none of its data.
                        className={`absolute inset-y-1 ${r.orbiter ? 'border border-dashed border-earth' : 'bg-earth-fill'}`}
                        style={{ left: pct(a), width: width(a, b) }}
                        title={`${r.label}${r.orbiter ? ' could see the lander' : ''}: ${dateTimeWords(a)} to ${dateTimeWords(b)}, ${formatValue((b - a) / HOUR)} h`}
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
            {axisTicks(start, end).map((t, i) => (
              <span
                key={t.at}
                className="absolute top-0 font-mono text-micro whitespace-nowrap text-ink-3"
                style={{ left: `${((t.at - start) / span) * 100}%`, transform: i ? 'translateX(-50%)' : undefined }}
              >
                {t.label}
              </span>
            ))}
          </div>
        </div>
      </div>
    </ScrollRegion>
  )
}

/**
 * Axis labels that stay inside the dates: the first date, then whole days
 * for a long span, or clock hours (UTC) for a day or two.
 */
export function axisTicks(start: number, end: number): { at: number; label: string }[] {
  const span = end - start
  const ticks = [{ at: start, label: shortDate(start) }]
  const pad = (n: number) => String(n).padStart(2, '0')
  if (span <= 2 * 24 * HOUR) {
    const step = (span <= 18 * HOUR ? 3 : 6) * HOUR
    for (let t = Math.ceil((start + step / 2) / step) * step; t < end - step / 2; t += step) {
      ticks.push({ at: t, label: `${pad(new Date(t).getUTCHours())}:00` })
    }
    return ticks
  }
  const days = span / (24 * HOUR)
  const every = days > 20 ? 7 : days > 8 ? 2 : 1
  for (let d = every; d < days - every / 2; d += every) ticks.push({ at: start + d * 24 * HOUR, label: `Day ${d}` })
  return ticks
}

/** The contact chart's table twin: every pass, and every booked one. */
export function ContactTable({ contact, rows }: { contact: ContactDTO; rows: ContactRow[] }) {
  const cell = 'px-3 py-2 text-small text-ink-2 whitespace-nowrap'
  const head = 'px-3 py-2.5 text-tag font-semibold tracking-caps-md text-ink-3 uppercase'
  const name = (id: string) => contact.nodes.find((n) => n.id === id)?.name ?? id
  const passes = rows.flatMap((r) =>
    r.links.flatMap((l) =>
      l.stretches.map((s) => {
        const a = Date.parse(s.start)
        const b = Date.parse(s.end)
        const booked = contact.bookings.some((x) => (x.station === l.to || x.station === l.from) && Date.parse(x.start) < b && Date.parse(x.end) > a)
        const label = r.orbiter ? `${r.label} could see the lander (not a relay)` : `${name(l.from)} to ${name(l.to)}`
        return { label, a, b, s, booked }
      }),
    ),
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
            .map(({ label, a, b, s, booked }) => (
              <tr key={`${label}${s.start}`} className="border-t border-line">
                <th scope="row" className={`${cell} font-semibold text-ink`}>{label}</th>
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
                <th scope="row" className={`${cell} font-semibold text-ink`}>
                  {r.label}, {r.caption}
                </th>
                <td className={cell} colSpan={3}>
                  {plannedWords(contact.relays.find((x) => x.id === r.relayId))}
                </td>
                <td className={cell}>—</td>
              </tr>
            ))}
        </tbody>
      </table>
    </ScrollRegion>
  )
}
