import { useState, type KeyboardEvent, type PointerEvent } from 'react'
import type { EnergyResponseDTO, TimeQuantityDTO } from '../../lib/api/surface.types'
import { bandPath, linePath, linear, niceDomain, niceTicks, num, runs, utcWords } from './helpers'
import { useWidth } from './parts'

const L = 52
const R = 14
const TITLE = 24
const PH = 104
const GAP = 18
const AXIS = 30
const ROW = TITLE + PH + GAP

const TICK = { fill: 'var(--color-ink-3)', fontFamily: 'var(--font-sans)', fontSize: 12 } as const
const TITLE_TEXT = { fontFamily: 'var(--font-sans)', fontSize: 12, fontWeight: 600, letterSpacing: 1.4 } as const

/**
 * Power, battery charge and bus temperature on one time axis, stacked so a
 * night lines up with the charge falling and the bus cooling. Each band is the
 * range between the cold and warm ends of the ground temperature; thresholds
 * are labelled lines, never a coloured zone; a crossing is a dashed line with
 * its own words. Drawn in real pixels so the text stays 12 px at 390 wide.
 */
export function EnergyCharts({
  data,
  operationalC,
  survivalC,
  capacityWh,
}: {
  data: EnergyResponseDTO
  operationalC: number | null
  survivalC: number | null
  capacityWh: number | null
}) {
  const [ref, W] = useWidth<HTMLDivElement>()
  const [cursor, setCursor] = useState<number | null>(null)
  const s = data.series
  const n = s.t_s.length
  const startMs = Date.parse(data.start ?? s.t_utc[0] ?? '')
  const totalS = n > 1 ? s.t_s[n - 1] : 1
  const x = linear(0, totalS, L, W - R)
  const xs = s.t_s.map(x)
  const H = ROW * 3 - GAP + AXIS

  const top = (i: number) => i * ROW + TITLE
  const pDomain = niceDomain([0, ...s.p_gen_w])
  const socVals = [...s.soc_wh.lo, ...s.soc_wh.hi, ...s.soc_wh.value].filter((v): v is number => v !== null)
  const sDomain = niceDomain([0, ...socVals, ...(capacityWh !== null ? [capacityWh] : [])])
  const tVals = [...s.t_bus_c.lo, ...s.t_bus_c.hi, ...s.t_bus_c.value].filter((v): v is number => v !== null)
  const tDomain = niceDomain([...tVals, ...(operationalC !== null ? [operationalC] : []), ...(survivalC !== null ? [survivalC] : [])])
  const yP = linear(pDomain[0], pDomain[1], top(0) + PH, top(0))
  const yS = linear(sDomain[0], sDomain[1], top(1) + PH, top(1))
  const yT = linear(tDomain[0], tDomain[1], top(2) + PH, top(2))

  const darkRuns = runs(s.lit, (v) => v < 0.5)
  const edge = (i: number) => (i + 1 < n ? xs[i + 1] : W - R)
  const warmUnknown = s.t_bus_c.hi.some((v) => v === null) || s.soc_wh.hi.some((v) => v === null)
  const hiOr = (hi: (number | null)[], val: (number | null)[]) => hi.map((h, i) => (h === null ? val[i] : h))

  const timeTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * totalS)
  const withTime = totalS < 4 * 86_400

  const empty = data.key.battery_empty_at
  const crossed = data.key.survival_threshold_crossed_at

  const pick = (px: number) => {
    let best = 0
    for (let i = 1; i < n; i++) if (Math.abs(xs[i] - px) < Math.abs(xs[best] - px)) best = i
    setCursor(best)
  }
  const onPointer = (e: PointerEvent<SVGRectElement>) => {
    const box = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect()
    pick(e.clientX - box.left)
  }
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = e.shiftKey ? 10 : 1
    const at = cursor ?? -1
    let next: number | null = null
    if (e.key === 'ArrowRight') next = Math.min(n - 1, at + step)
    else if (e.key === 'ArrowLeft') next = Math.max(0, (cursor ?? n) - step)
    else if (e.key === 'Home') next = 0
    else if (e.key === 'End') next = n - 1
    else if (e.key === 'Escape') setCursor(null)
    if (next !== null) {
      e.preventDefault()
      setCursor(next)
    }
  }

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <Readout data={data} i={cursor} startMs={startMs} />
      <div
        ref={ref}
        tabIndex={0}
        role="group"
        aria-label="Power, battery charge and bus temperature over the dates. Use the left and right arrow keys to read a moment; Shift moves ten steps."
        onKeyDown={onKey}
        className="min-w-0 rounded-md focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[var(--color-focus)]"
      >
        <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={chartSummary(data, operationalC, survivalC)} className="block max-w-full">
          {/* 1. Power generated, with the nights hatched behind it */}
          <text x={L} y={top(0) - 8} fill="var(--color-sun)" {...TITLE_TEXT}>
            POWER GENERATED, W
          </text>
          {darkRuns.map(([a, b]) => (
            <rect key={`d${a}`} x={xs[a]} y={top(0)} width={Math.max(1, edge(b) - xs[a])} height={PH} fill="url(#pw-blocked)" opacity={0.7} />
          ))}
          <path d={`${linePath(xs, s.p_gen_w.map(yP))}L${xs[n - 1]} ${yP(0)}L${xs[0]} ${yP(0)}Z`} fill="var(--color-sun-fill)" opacity={0.16} />
          <path d={linePath(xs, s.p_gen_w.map(yP))} fill="none" stroke="var(--color-sun)" strokeWidth={2} strokeLinejoin="round" />
          <YAxis ticks={niceTicks(pDomain[0], pDomain[1], 3)} y={yP} W={W} />

          {/* 2. Battery charge with its range and the moment it empties */}
          <text x={L} y={top(1) - 8} fill="var(--color-ink-2)" {...TITLE_TEXT}>
            BATTERY CHARGE, Wh
          </text>
          <path d={bandPath(xs, s.soc_wh.lo.map((v) => (v === null ? null : yS(v))), hiOr(s.soc_wh.hi, s.soc_wh.value).map((v) => (v === null ? null : yS(v))))} fill="url(#pw-uncertain)" />
          <path d={bandPath(xs, s.soc_wh.lo.map((v) => (v === null ? null : yS(v))), hiOr(s.soc_wh.hi, s.soc_wh.value).map((v) => (v === null ? null : yS(v))))} fill="var(--color-uncertain)" opacity={0.14} />
          <path d={linePath(xs, s.soc_wh.value.map((v) => (v === null ? null : yS(v))))} fill="none" stroke="var(--color-ink)" strokeWidth={2} strokeLinejoin="round" />
          {capacityWh !== null && <Threshold y={yS(capacityWh)} W={W} label={`capacity ${num(capacityWh, 0)} Wh`} />}
          <YAxis ticks={niceTicks(sDomain[0], sDomain[1], 3)} y={yS} W={W} />
          <Moment q={empty} x={(h) => x(h * 3600)} y0={top(1)} y1={top(1) + PH} W={W} words="empties" startMs={startMs} />

          {/* 3. Bus temperature, its range, both thresholds and the crossing */}
          <text x={L} y={top(2) - 8} fill="var(--color-ink-2)" {...TITLE_TEXT}>
            BUS TEMPERATURE, °C
          </text>
          <path d={bandPath(xs, s.t_bus_c.lo.map((v) => (v === null ? null : yT(v))), hiOr(s.t_bus_c.hi, s.t_bus_c.value).map((v) => (v === null ? null : yT(v))))} fill="url(#pw-uncertain)" />
          <path d={bandPath(xs, s.t_bus_c.lo.map((v) => (v === null ? null : yT(v))), hiOr(s.t_bus_c.hi, s.t_bus_c.value).map((v) => (v === null ? null : yT(v))))} fill="var(--color-uncertain)" opacity={0.14} />
          {operationalC !== null && <Threshold y={yT(operationalC)} W={W} label={`operational minimum ${num(operationalC, 0)} °C`} />}
          {survivalC !== null && <Threshold y={yT(survivalC)} W={W} label={`survival minimum ${num(survivalC, 0)} °C`} below />}
          <path d={linePath(xs, s.t_bus_c.value.map((v) => (v === null ? null : yT(v))))} fill="none" stroke="var(--color-ink)" strokeWidth={2} strokeLinejoin="round" />
          <YAxis ticks={niceTicks(tDomain[0], tDomain[1], 3)} y={yT} W={W} />
          <Moment q={crossed} x={(h) => x(h * 3600)} y0={top(2)} y1={top(2) + PH} W={W} words="below survival" startMs={startMs} />

          {/* the one time axis */}
          <line x1={L} x2={W - R} y1={H - AXIS + 4} y2={H - AXIS + 4} stroke="var(--color-line-strong)" strokeWidth={1.5} />
          {timeTicks.map((t, i) => (
            <text
              key={t}
              x={x(t)}
              y={H - 8}
              textAnchor={i === 0 ? 'start' : i === timeTicks.length - 1 ? 'end' : 'middle'}
              {...TICK}
              className={i % 2 === 1 ? 'max-sm:hidden' : undefined}
            >
              {utcWords(startMs + t * 1000, withTime)}
            </text>
          ))}

          {cursor !== null && (
            <g pointerEvents="none">
              <line x1={xs[cursor]} x2={xs[cursor]} y1={top(0) - 4} y2={H - AXIS + 4} stroke="var(--color-ink)" strokeWidth={1.5} />
              <circle cx={xs[cursor]} cy={yP(s.p_gen_w[cursor])} r={4} fill="var(--color-sun)" stroke="var(--color-panel)" strokeWidth={2} />
              {s.soc_wh.value[cursor] !== null && <circle cx={xs[cursor]} cy={yS(s.soc_wh.value[cursor] as number)} r={4} fill="var(--color-ink)" stroke="var(--color-panel)" strokeWidth={2} />}
              {s.t_bus_c.value[cursor] !== null && <circle cx={xs[cursor]} cy={yT(s.t_bus_c.value[cursor] as number)} r={4} fill="var(--color-ink)" stroke="var(--color-panel)" strokeWidth={2} />}
            </g>
          )}
          <rect
            x={L}
            y={top(0) - 4}
            width={Math.max(0, W - L - R)}
            height={H - AXIS - top(0) + 8}
            fill="transparent"
            onPointerMove={onPointer}
            onPointerDown={onPointer}
            onPointerLeave={() => setCursor(null)}
          />
        </svg>
      </div>
      <Legend warmUnknown={warmUnknown} />
    </div>
  )
}

function YAxis({ ticks, y, W }: { ticks: number[]; y: (v: number) => number; W: number }) {
  return (
    <g>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="var(--color-line)" />
          <text x={L - 8} y={y(t) + 4} textAnchor="end" {...TICK}>
            {num(t, Math.abs(t) >= 10 || t === 0 ? 0 : 1)}
          </text>
        </g>
      ))}
    </g>
  )
}

/** A threshold: a dashed line and its name in words at the right end. */
function Threshold({ y, W, label, below = false }: { y: number; W: number; label: string; below?: boolean }) {
  return (
    <g>
      <line x1={L} x2={W - R} y1={y} y2={y} stroke="var(--color-ink-2)" strokeWidth={1.5} strokeDasharray="6 4" />
      <text x={W - R - 2} y={below ? y + 14 : y - 5} textAnchor="end" {...TICK} fill="var(--color-ink-2)" paintOrder="stroke" stroke="var(--color-panel)" strokeWidth={3}>
        {label}
      </text>
    </g>
  )
}

/** A moment with its time range: the range hatched, a dashed line at the value, and words beside it. */
function Moment({
  q,
  x,
  y0,
  y1,
  W,
  words,
  startMs,
}: {
  q: TimeQuantityDTO
  x: (h: number) => number
  y0: number
  y1: number
  W: number
  words: string
  startMs: number
}) {
  if (q.value === null || q.value === undefined) return null
  const xv = x(q.value)
  const lo = typeof q.lo === 'number' ? x(q.lo) : xv
  const hi = typeof q.hi === 'number' ? x(q.hi) : xv
  const flip = xv > (L + W) / 2
  const when = q.value_utc ? utcWords(Date.parse(q.value_utc), true) : utcWords(startMs + q.value * 3_600_000, true)
  return (
    <g>
      {hi - lo > 1 && <rect x={lo} y={y0} width={hi - lo} height={y1 - y0} fill="url(#pw-uncertain)" />}
      <line x1={xv} x2={xv} y1={y0} y2={y1} stroke="var(--color-alert)" strokeWidth={2} strokeDasharray="4 3" />
      <path d={`M${xv - 5} ${y0} L${xv + 5} ${y0} L${xv} ${y0 + 7} Z`} fill="var(--color-alert)" />
      <text
        x={flip ? xv - 8 : xv + 8}
        y={y0 + 14}
        textAnchor={flip ? 'end' : 'start'}
        {...TICK}
        fill="var(--color-ink)"
        fontWeight={600}
        paintOrder="stroke"
        stroke="var(--color-panel)"
        strokeWidth={3}
      >
        {q.open ? 'at least ' : ''}
        {words} {when}
      </text>
    </g>
  )
}

function Readout({ data, i, startMs }: { data: EnergyResponseDTO; i: number | null; startMs: number }) {
  const s = data.series
  const range = (b: EnergyResponseDTO['series']['soc_wh'], unit: string, digits: number) => {
    const v = b.value[i as number]
    if (v === null) return 'not known'
    const lo = b.lo[i as number]
    const hi = b.hi[i as number]
    const span = lo !== null && hi !== null ? ` (${num(lo, digits)} to ${num(hi, digits)})` : lo !== null ? ` (from ${num(lo, digits)}; warm end unknown)` : ''
    return `${num(v, digits)} ${unit}${span}`
  }
  return (
    <p aria-live="polite" className="min-h-10 font-mono text-caption leading-caption text-ink-2 tabular-nums">
      {i === null ? (
        <span className="font-sans text-ink-3">Point at the charts, or focus them and use the arrow keys, to read one moment.</span>
      ) : (
        <>
          <span className="text-ink">{utcWords(s.t_utc[i] ? Date.parse(s.t_utc[i] as string) : startMs + s.t_s[i] * 1000, true)} UTC</span>
          {' · '}Sun {s.lit[i] >= 0.5 ? 'up' : 'below the skyline'}
          {' · '}power {num(s.p_gen_w[i], 0)} W{' · '}charge {range(s.soc_wh, 'Wh', 0)}
          {' · '}bus {range(s.t_bus_c, '°C', 0)}
        </>
      )}
    </p>
  )
}

function Legend({ warmUnknown }: { warmUnknown: boolean }) {
  const sw = 'inline-block h-3 w-5 shrink-0 align-middle'
  return (
    <ul className="flex flex-wrap gap-x-5 gap-y-1.5 text-caption leading-caption text-ink-2">
      <li className="flex items-center gap-2">
        <svg className={sw} aria-hidden="true">
          <rect width="20" height="12" fill="url(#pw-blocked)" />
        </svg>
        Sun below the skyline
      </li>
      <li className="flex items-center gap-2">
        <svg className={sw} aria-hidden="true">
          <rect width="20" height="12" fill="url(#pw-uncertain)" />
          <line x1="0" x2="20" y1="6" y2="6" stroke="var(--color-ink)" strokeWidth="2" />
        </svg>
        Steady-state range between the cold and warm ground bounds (solid line is their midpoint, not a forecast or best estimate)
        {warmUnknown ? '; warm end unknown where the band stops' : ''}
      </li>
      <li className="flex items-center gap-2">
        <svg className={sw} aria-hidden="true">
          <line x1="0" x2="20" y1="6" y2="6" stroke="var(--color-ink-2)" strokeWidth="1.5" strokeDasharray="6 4" />
        </svg>
        A figure of the lander&apos;s
      </li>
      <li className="flex items-center gap-2">
        <svg className={sw} aria-hidden="true">
          <line x1="10" x2="10" y1="0" y2="12" stroke="var(--color-alert)" strokeWidth="2" strokeDasharray="4 3" />
        </svg>
        A moment and its range
      </li>
    </ul>
  )
}

function chartSummary(d: EnergyResponseDTO, op: number | null, surv: number | null): string {
  const k = d.key
  const parts = [`Three charts over ${Math.round((d.series.t_s[d.series.t_s.length - 1] ?? 0) / 3600)} hours.`]
  parts.push(
    k.battery_empty_at.value !== null
      ? `The battery empties about ${Math.round(k.battery_empty_at.value)} hours in.`
      : 'The battery does not empty in these dates.',
  )
  if (k.lowest_bus_temperature.value !== null) parts.push(`The bus is coldest at about ${Math.round(k.lowest_bus_temperature.value)} °C.`)
  if (op !== null) parts.push(`Operational minimum ${op} °C.`)
  if (surv !== null)
    parts.push(
      k.survival_threshold_crossed_at.value !== null
        ? `It falls below the survival minimum of ${surv} °C about ${Math.round(k.survival_threshold_crossed_at.value)} hours in.`
        : `It stays above the survival minimum of ${surv} °C.`,
    )
  return parts.join(' ')
}
