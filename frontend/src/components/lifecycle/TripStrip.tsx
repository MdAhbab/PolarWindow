import { useRef } from 'react'
import type { StretchDTO, TripDTO } from '../../lib/api/lifecycle'
import { dateTimeWords, shortDate } from '../../lib/format'
import { formatValue, quantityText } from '../../lib/lifecycle/quantity'
import { useWidth } from '../../hooks/useWidth'
import { ScrollRegion } from '../ui'

const LEFT = 76
const RIGHT = 16
const TOP = 26
const PLOT_H = 150
const LANE_H = 18
const LANE_GAP = 10
const AXIS_H = 26

const HOUR = 3_600_000

export interface TripStretchRow {
  kind: 'shadow' | 'unheard' | 'nodata'
  start: number
  end: number
  openStart: boolean
  openEnd: boolean
}

/** The trip's first and last moments: its stated dates, else its first and last samples. */
export function tripSpan(trip: TripDTO): { t0: number; t1: number } {
  const first = trip.samples[0]
  const last = trip.samples[trip.samples.length - 1]
  const t0 = trip.start ? Date.parse(trip.start) : first ? Date.parse(first.t) : 0
  const t1 = trip.end ? Date.parse(trip.end) : last ? Date.parse(last.t) : t0
  return { t0, t1 }
}

/** Under a second is a rounding seam between two stretches, not a gap. */
const SEAM_MS = 1000

/**
 * The parts of the trip with data: the stretches NASA's reconstruction covers
 * (`covered`, exact from the service), inside the trip's dates, with rounding
 * seams closed. A trip that lists none (a designed one) is covered throughout.
 */
export function coveredParts(trip: TripDTO): [number, number][] {
  const { t0, t1 } = tripSpan(trip)
  if (!trip.covered?.length) return [[t0, t1]]
  const parts = trip.covered
    .map((c) => [Math.max(t0, Date.parse(c.start)), Math.min(t1, Date.parse(c.end))] as [number, number])
    .filter(([a, b]) => b > a)
    .sort((a, b) => a[0] - b[0])
  const out: [number, number][] = []
  for (const [a, b] of parts) {
    const last = out[out.length - 1]
    if (last && a - last[1] < SEAM_MS) last[1] = Math.max(last[1], b)
    else out.push([a, b])
  }
  return out
}

/**
 * The parts of the trip with no data: what the covered stretches leave out
 * between the trip's dates. NASA's reconstruction can come in separate
 * stretches (IM-1's does); the service lists them, so nothing is guessed from
 * the spacing of the samples.
 */
export function coverageGaps(trip: TripDTO): { start: number; end: number }[] {
  const { t0, t1 } = tripSpan(trip)
  const gaps: { start: number; end: number }[] = []
  let from = t0
  for (const [a, b] of coveredParts(trip)) {
    if (a - from >= SEAM_MS) gaps.push({ start: from, end: a })
    from = Math.max(from, b)
  }
  if (t1 - from >= SEAM_MS) gaps.push({ start: from, end: t1 })
  return gaps
}

/**
 * The stretches the two lanes are drawn from, and the table twin lists: in
 * shadow, not heard by any ground station (the complement of `heard` inside
 * the parts with data), and no data. One array for the picture and the table
 * (invariant 5).
 */
export function tripStretches(trip: TripDTO): TripStretchRow[] {
  const { t0, t1 } = tripSpan(trip)
  const toRow = (kind: TripStretchRow['kind']) => (x: StretchDTO) => ({
    kind,
    start: Date.parse(x.start),
    end: Date.parse(x.end),
    openStart: x.open_start,
    openEnd: x.open_end,
  })
  const shadow = trip.shadow.map(toRow('shadow'))
  const nodata: TripStretchRow[] = coverageGaps(trip).map((g) => ({ kind: 'nodata', start: g.start, end: g.end, openStart: false, openEnd: false }))
  const covered = coveredParts(trip)
  // Not heard = the gaps between heard stretches, inside each part with data.
  const heard = trip.heard.map((x) => [Date.parse(x.start), Date.parse(x.end)] as const).sort((a, b) => a[0] - b[0])
  const unheard: TripStretchRow[] = []
  const add = (a: number, b: number) => {
    if (b - a >= SEAM_MS) unheard.push({ kind: 'unheard', start: a, end: b, openStart: a === t0, openEnd: b === t1 })
  }
  for (const [a, b] of covered) {
    let cursor = a
    for (const [h0, h1] of heard) {
      if (h1 <= cursor || h0 >= b) continue
      if (h0 > cursor) add(cursor, h0)
      cursor = Math.max(cursor, h1)
    }
    if (cursor < b) add(cursor, b)
  }
  return [...shadow, ...unheard, ...nodata].sort((a, b) => a.start - b.start)
}

/** One distance row a day, from the samples the lines are drawn from. */
export function dailyDistances(trip: TripDTO): { t: number; earthKm: number; moonKm: number }[] {
  const { t0 } = tripSpan(trip)
  const out: { t: number; earthKm: number; moonKm: number }[] = []
  let nextDay = 0
  for (const s of trip.samples) {
    const t = Date.parse(s.t)
    if (t - t0 >= nextDay * 24 * HOUR) {
      out.push({ t, earthKm: s.earth_km, moonKm: s.moon_km })
      nextDay = Math.floor((t - t0) / (24 * HOUR)) + 1
    }
  }
  const last = trip.samples[trip.samples.length - 1]
  if (last && out[out.length - 1]?.t !== Date.parse(last.t)) {
    out.push({ t: Date.parse(last.t), earthKm: last.earth_km, moonKm: last.moon_km })
  }
  return out
}

function niceMax(v: number): number {
  const p = 10 ** Math.floor(Math.log10(v))
  const m = v / p
  return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * p
}

/**
 * The trip, as a strip (design-lifecycle.md §4, Trip). Schematic and flat: no
 * 3D. Distance to Earth and to the Moon over time on one axis, the burns as
 * numbered ticks, when the Moon's pull wins, then two lanes on the same time
 * axis: sunlight (amber, hatched in shadow) and whether a ground station can
 * hear it (cyan, hatched when none can).
 *
 * Nothing moves, so this drawing is also its own reduced-motion version.
 */
export function TripStrip({ trip, stretches }: { trip: TripDTO; stretches: TripStretchRow[] }) {
  const box = useRef<HTMLDivElement>(null)
  const width = Math.max(560, useWidth(box, 720))
  const { t0, t1 } = tripSpan(trip)
  const span = Math.max(1, t1 - t0)
  const gaps = stretches.filter((r) => r.kind === 'nodata')
  // A gap lies between two samples: the one before ends a stretch, the one after starts the next.
  const across = (prev: number, t: number) => gaps.some((g) => g.start >= prev - SEAM_MS && g.end <= t + SEAM_MS)
  const x = (t: number) => LEFT + ((t - t0) / span) * (width - LEFT - RIGHT)

  const { maxKm, earthPath, moonPath, labelAt } = (() => {
    const max = niceMax(Math.max(1, ...trip.samples.map((s) => Math.max(s.earth_km, s.moon_km))))
    const y = (km: number) => TOP + PLOT_H - (km / max) * PLOT_H
    const path = (pick: (s: TripDTO['samples'][number]) => number) =>
      // A new line after each gap in the data, so no line is drawn across it.
      trip.samples
        .map((s, i) => {
          const t = Date.parse(s.t)
          const line = i > 0 && !across(Date.parse(trip.samples[i - 1].t), t)
          return `${line ? 'L' : 'M'}${x(t).toFixed(1)} ${y(pick(s)).toFixed(1)}`
        })
        .join(' ')
    // Label the two lines where they are furthest apart, away from the edges,
    // so the words never sit on a crossing.
    const inner = trip.samples.filter((s) => {
      const sx = x(Date.parse(s.t))
      return sx > LEFT + 40 && sx < width - RIGHT - 40
    })
    const at = inner.reduce<(typeof inner)[number] | undefined>(
      (best, s) => (!best || Math.abs(s.earth_km - s.moon_km) > Math.abs(best.earth_km - best.moon_km) ? s : best),
      undefined,
    )
    return {
      maxKm: max,
      earthPath: path((s) => s.earth_km),
      moonPath: path((s) => s.moon_km),
      labelAt: at ? { x: x(Date.parse(at.t)), earthY: y(at.earth_km), moonY: y(at.moon_km) } : null,
    }
  })()

  const yKm = (km: number) => TOP + PLOT_H - (km / maxKm) * PLOT_H
  const labelAnchor = labelAt && labelAt.x > (LEFT + width) / 2 ? 'end' : 'start'
  const lane1 = TOP + PLOT_H + 18
  const lane2 = lane1 + LANE_H + LANE_GAP
  const axisY = lane2 + LANE_H + 8
  const height = axisY + AXIS_H
  const days = Math.floor(span / (24 * HOUR))
  // Labels at least 64 px apart, so "Day 1" never lands on the date.
  const pxPerDay = ((width - LEFT - RIGHT) * 24 * HOUR) / span
  const dayStep = Math.max(1, Math.ceil(64 / Math.max(1, pxPerDay)))
  const shadow = stretches.filter((s) => s.kind === 'shadow')
  const unheard = stretches.filter((s) => s.kind === 'unheard')
  const pull = trip.moon_pull?.t_equal_pull ? Date.parse(trip.moon_pull.t_equal_pull) : null
  const longestShadow = quantityText(trip.numbers.longest_shadow_h)

  const label = `The trip from ${dateTimeWords(t0)} to ${dateTimeWords(t1)}, ${formatValue(span / (24 * HOUR))} days. Distance from Earth rises to ${formatValue(
    Math.max(...trip.samples.map((s) => s.earth_km)),
  )} km while distance from the Moon falls to ${formatValue(Math.min(...trip.samples.map((s) => s.moon_km)))} km. ${shadow.length} stretch${
    shadow.length === 1 ? '' : 'es'
  } in shadow, the longest ${longestShadow}; ${unheard.length} stretch${unheard.length === 1 ? '' : 'es'} no ground station can hear.${
    gaps.length ? ` ${gaps.length} stretch${gaps.length === 1 ? '' : 'es'} with no data.` : ''
  }${trip.burns.length ? ` ${trip.burns.length} burns.` : ''} The table lists every stretch${trip.burns.length ? ' and burn' : ''}.`

  return (
    <ScrollRegion label="Trip chart, scrolls sideways" className="-mx-1 px-1">
      <div ref={box} className="min-w-[560px]">
        <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label} className="block">
          {/* Distance grid: hairlines, solid, one shade off the ground. */}
          {[0, 0.5, 1].map((f) => {
            const km = maxKm * f
            return (
              <g key={f}>
                <path d={`M${LEFT} ${yKm(km)} H${width - RIGHT}`} stroke="var(--color-line)" strokeWidth="1" />
                <text x={LEFT - 8} y={yKm(km) + 4} textAnchor="end" fontSize="11" fontFamily="var(--font-mono)" fill="var(--color-ink-3)">
                  {km >= 1000 ? `${formatValue(km / 1000)}k km` : `${km} km`}
                </text>
              </g>
            )
          })}

          {/* When the Moon's pull wins. */}
          {pull !== null && pull >= t0 && pull <= t1 && (
            <g>
              <path d={`M${x(pull)} ${TOP - 4} V${TOP + PLOT_H}`} stroke="var(--color-ink-3)" strokeWidth="1" />
              <text
                x={x(pull) + (x(pull) > width * 0.7 ? -6 : 6)}
                y={TOP + 8}
                textAnchor={x(pull) > width * 0.7 ? 'end' : 'start'}
                fontSize="11"
                fill="var(--color-ink-2)"
              >
                The Moon’s pull wins from here
              </text>
            </g>
          )}

          <path d={earthPath} fill="none" stroke="var(--color-ink)" strokeWidth="2" strokeLinejoin="round" />
          <path d={moonPath} fill="none" stroke="var(--color-terrain-high)" strokeWidth="2" strokeLinejoin="round" />
          {labelAt && (
            <>
              <text x={labelAt.x} y={labelAt.earthY - 8} textAnchor={labelAnchor} fontSize="12" fontWeight="600" fill="var(--color-ink)">
                from Earth
              </text>
              <text x={labelAt.x} y={labelAt.moonY - 8} textAnchor={labelAnchor} fontSize="12" fontWeight="600" fill="var(--color-ink-2)">
                from the Moon
              </text>
            </>
          )}

          {/* Burns: numbered ticks; the key below names them. */}
          {trip.burns.map((b, i) => {
            const bx = x(Date.parse(b.t))
            return (
              <g key={b.name + b.t}>
                <title>{`${b.name}, ${dateTimeWords(Date.parse(b.t))}, ${quantityText(b.dv_m_s)}`}</title>
                <path d={`M${bx} ${TOP - 6} V${lane2 + LANE_H}`} stroke="var(--color-ink-2)" strokeWidth="1" />
                <rect x={bx - 9} y={TOP - 24} width="18" height="18" fill="var(--color-ink)" />
                <text x={bx} y={TOP - 11} textAnchor="middle" fontSize="11" fontWeight="700" fill="var(--color-canvas)">
                  {i + 1}
                </text>
              </g>
            )
          })}

          {/* Lane 1: sunlight. Amber lit, hatched in shadow. */}
          <text x={LEFT - 8} y={lane1 + 13} textAnchor="end" fontSize="11" fill="var(--color-ink-2)">
            Sunlight
          </text>
          <rect x={LEFT} y={lane1} width={width - LEFT - RIGHT} height={LANE_H} fill="var(--color-sun-fill)" />
          {shadow.map((s) => (
            <rect
              key={`s${s.start}`}
              x={x(s.start)}
              y={lane1}
              width={Math.max(2, x(s.end) - x(s.start))}
              height={LANE_H}
              fill="url(#pw-blocked)"
            >
              <title>{`In shadow ${formatValue((s.end - s.start) / HOUR)} h from ${dateTimeWords(s.start)}`}</title>
            </rect>
          ))}

          {/* Lane 2: a ground station can hear it. Cyan heard, hatched when none can. */}
          <text x={LEFT - 8} y={lane2 + 13} textAnchor="end" fontSize="11" fill="var(--color-ink-2)">
            Heard
          </text>
          <rect x={LEFT} y={lane2} width={width - LEFT - RIGHT} height={LANE_H} fill="var(--color-earth-fill)" />
          {unheard.map((s) => (
            <rect
              key={`u${s.start}`}
              x={x(s.start)}
              y={lane2}
              width={Math.max(2, x(s.end) - x(s.start))}
              height={LANE_H}
              fill="url(#pw-blocked)"
            >
              <title>{`No ground station can hear it: ${formatValue((s.end - s.start) / HOUR)} h from ${dateTimeWords(s.start)}`}</title>
            </rect>
          ))}

          {/* No data: both lanes left empty, outlined, so neither lit nor heard is implied. */}
          {gaps.map((g) => (
            <rect
              key={`n${g.start}`}
              x={x(g.start)}
              y={lane1}
              width={Math.max(2, x(g.end) - x(g.start))}
              height={lane2 + LANE_H - lane1}
              fill="var(--color-panel)"
              stroke="var(--color-line-strong)"
              strokeDasharray="3 3"
            >
              <title>{`No data: ${formatValue((g.end - g.start) / HOUR)} h from ${dateTimeWords(g.start)}`}</title>
            </rect>
          ))}

          {/* Days from launch. */}
          {Array.from({ length: Math.floor(days / dayStep) + 1 }, (_, k) => k * dayStep).map((d) => {
            const dx = x(t0 + d * 24 * HOUR)
            return (
              <g key={d}>
                <path d={`M${dx} ${axisY - 4} V${axisY}`} stroke="var(--color-line-strong)" strokeWidth="1" />
                <text x={dx} y={axisY + 14} textAnchor={d === 0 ? 'start' : 'middle'} fontSize="11" fontFamily="var(--font-mono)" fill="var(--color-ink-3)">
                  {d === 0 ? shortDate(t0).replace(/ \d{4}$/, '') : `Day ${d}`}
                </text>
              </g>
            )
          })}
        </svg>
      </div>
    </ScrollRegion>
  )
}

/** The key under the strip: each mark beside its words, and the burns by number. */
export function TripLegendItems(trip: TripDTO) {
  return [
    { swatch: <span className="h-0.5 w-5 bg-ink" />, label: 'Distance from Earth' },
    { swatch: <span className="h-0.5 w-5 bg-terrain-high" />, label: 'Distance from the Moon' },
    { swatch: <span className="h-3 w-5 bg-sun-fill" />, label: 'In sunlight' },
    { swatch: <span className="hatch-blocked h-3 w-5" />, label: 'In shadow, or no station can hear it' },
    { swatch: <span className="h-3 w-5 bg-earth-fill" />, label: 'A ground station can hear it' },
    ...(coverageGaps(trip).length ? [{ swatch: <span className="h-3 w-5 border border-dashed border-line-strong" />, label: 'No data' }] : []),
    ...burnKeys(trip.burns.map((b) => b.name)).map((k) => ({
      swatch: (
        <span className="inline-flex h-4 min-w-4 items-center justify-center bg-ink px-0.5 text-micro font-bold text-canvas">{k.marks}</span>
      ),
      label: k.label,
    })),
  ]
}

/**
 * The burns' key, with a run of numbered burns of one kind said once:
 * "Correction 1" … "Correction 7" become one key, "1–7 Corrections".
 */
export function burnKeys(names: string[]): { marks: string; label: string }[] {
  const out: { first: number; last: number; base: string; name: string }[] = []
  names.forEach((name, i) => {
    const base = name.replace(/\s+\d+$/, '')
    const prev = out[out.length - 1]
    if (prev && base !== name && prev.base === base && prev.last === i) prev.last = i + 1
    else out.push({ first: i + 1, last: i + 1, base: base === name ? '' : base, name })
  })
  return out.map((r) =>
    r.first === r.last
      ? { marks: String(r.first), label: r.name }
      : { marks: `${r.first}–${r.last}`, label: /s$/.test(r.base) ? r.base : `${r.base}s` },
  )
}

/** The strip's table twin: every stretch and every burn, and the distance once a day. */
export function TripTable({ trip, stretches }: { trip: TripDTO; stretches: TripStretchRow[] }) {
  const daily = dailyDistances(trip)
  const cell = 'px-3 py-2 text-small text-ink-2'
  const head = 'px-3 py-2.5 text-tag font-semibold tracking-caps-md text-ink-3 uppercase'
  return (
    <div className="flex flex-col gap-5">
      <ScrollRegion label="Stretches and burns, scrolls sideways" className="border border-line">
        <table className="w-full min-w-[600px] border-collapse text-left">
          <caption className="sr-only">Every stretch in shadow, out of reach of a ground station or with no data, and every burn, in time order.</caption>
          <thead>
            <tr className="bg-inset">
              <th scope="col" className={head}>What</th>
              <th scope="col" className={head}>Start</th>
              <th scope="col" className={head}>End</th>
              <th scope="col" className={`${head} text-right`}>Length</th>
            </tr>
          </thead>
          <tbody>
            {[
              ...stretches.map((s) => ({
                t: s.start,
                row: (
                  <tr key={`${s.kind}${s.start}`} className="border-t border-line">
                    <th scope="row" className={`${cell} font-semibold text-ink`}>
                      {s.kind === 'shadow' ? 'In shadow' : s.kind === 'unheard' ? 'No ground station can hear it' : 'No data'}
                    </th>
                    <td className={cell}>{s.openStart ? `from launch, ${dateTimeWords(s.start)}` : dateTimeWords(s.start)}</td>
                    <td className={cell}>{s.openEnd ? `to arrival, ${dateTimeWords(s.end)}` : dateTimeWords(s.end)}</td>
                    <td className={`${cell} text-right font-mono tnum text-ink`}>{formatValue((s.end - s.start) / HOUR)} h</td>
                  </tr>
                ),
              })),
              ...trip.burns.map((b) => ({
                t: Date.parse(b.t),
                row: (
                  <tr key={`b${b.t}`} className="border-t border-line">
                    <th scope="row" className={`${cell} font-semibold text-ink`}>
                      Burn: {b.name}
                    </th>
                    <td className={cell}>{dateTimeWords(Date.parse(b.t))}</td>
                    <td className={cell}>—</td>
                    <td className={`${cell} text-right font-mono tnum text-ink`}>{quantityText(b.dv_m_s)}</td>
                  </tr>
                ),
              })),
            ]
              .sort((a, b) => a.t - b.t)
              .map((r) => r.row)}
          </tbody>
        </table>
      </ScrollRegion>
      <ScrollRegion label="Distance once a day, scrolls sideways" className="border border-line">
        <table className="w-full min-w-[480px] border-collapse text-left">
          <caption className="sr-only">Distance from Earth and from the Moon, once a day, from the samples the lines are drawn from.</caption>
          <thead>
            <tr className="bg-inset">
              <th scope="col" className={head}>When</th>
              <th scope="col" className={`${head} text-right`}>From Earth</th>
              <th scope="col" className={`${head} text-right`}>From the Moon</th>
            </tr>
          </thead>
          <tbody>
            {daily.map((d) => (
              <tr key={d.t} className="border-t border-line">
                <th scope="row" className={`${cell} font-normal`}>{dateTimeWords(d.t)}</th>
                <td className={`${cell} text-right font-mono tnum text-ink`}>{formatValue(d.earthKm)} km</td>
                <td className={`${cell} text-right font-mono tnum text-ink`}>{formatValue(d.moonKm)} km</td>
              </tr>
            ))}
          </tbody>
        </table>
      </ScrollRegion>
    </div>
  )
}
