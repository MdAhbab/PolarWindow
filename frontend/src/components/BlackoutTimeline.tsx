import { useId } from 'react'
import type { Arc, SiteMetrics } from '../lib/types'
import { hoursWithUnit, msFromModelH, shortDate } from '../lib/format'
import { crossingBands } from '../lib/bands'
import { nightAgainstLimit, nightMargin } from '../lib/geometry/metrics'
import { useReducedMotion } from '../hooks/useMotion'

const X0 = 40
const X1 = 980
const TRACK_H = 46

/** A word drawn on the chart. The "now" line is cut where it would cross one (V135). */
interface Label {
  key: string
  x: number
  y: number
  text: string
  fill: string
  size: number
  weight?: number
  spacing?: number
  anchor?: 'start' | 'middle' | 'end'
}

/**
 * S5: the dates hour by hour, three tracks deep.
 *
 * The third track is the one nobody else draws: the intersection of "no Sun"
 * and "no link". It is the number the autonomy packet is sized from, and it is
 * always smaller than either gap alone, which is exactly why quoting them
 * separately understates the problem.
 *
 * Dates on the axis come from the dates' own opening instant
 * (`metrics.windowStartIso`), as the table beside it does (R1): hours on the
 * tracks count from that instant, never from the model epoch.
 */
export function BlackoutTimeline({
  metrics,
  cursorH,
  limitH,
  width = 1000,
  className = '',
}: {
  metrics: SiteMetrics
  cursorH: number
  /**
   * The battery limit, hours. The longest night is drawn in the alert hatch
   * only when it runs past it by more than its margin; magenta means over
   * the limit and nothing else. Omit and no night is drawn as over.
   */
  limitH?: number
  width?: number
  className?: string
}) {
  const win = metrics.windowHours
  const x = (h: number) => X0 + ((h - metrics.windowStartH) / win) * (X1 - X0)
  const w = (h: number) => (h / win) * (X1 - X0)
  const reduced = useReducedMotion()
  const maskId = `pw-now-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`
  // M6 in code: breathe under full motion, static at 0.34 opacity otherwise.
  const bandProps = reduced ? { opacity: 0.34 } : { className: 'breathe' }
  const sunBands = crossingBands(metrics.sun.arcs, win)
  const earthBands = crossingBands(metrics.earth.arcs, win)
  const cut = (a: { openStart?: boolean; openEnd?: boolean }) => Boolean(a.openStart || a.openEnd)

  // The dates' opening instant: the API's, else (a saved answer without it)
  // the model hours it was asked for.
  const originMs = metrics.windowStartIso ? Date.parse(metrics.windowStartIso) : msFromModelH(metrics.windowStartH)
  const at = (h: number) => originMs + h * 3_600_000

  const worstSun = metrics.sun.longestDownArc
  const sunPast =
    limitH !== undefined &&
    worstSun !== undefined &&
    nightAgainstLimit({ h: worstSun.hours, open: cut(worstSun), marginH: nightMargin(metrics) }, limitH).kind === 'past'
  const worstEarth = metrics.earth.longestDownArc
  const worstCompound = metrics.compound.reduce(
    (b, c) => (!b || c.hours > b.hours ? c : b),
    undefined as (typeof metrics.compound)[number] | undefined,
  )

  const hourLabels = (arcs: Arc[], y: number, prefix: string): Label[] =>
    arcs
      .filter((a) => !a.up && w(a.hours) > 34)
      .map((a, i) => ({
        key: `${prefix}${i}`,
        x: x(a.startH) + w(a.hours) / 2,
        y,
        text: `${cut(a) ? '≥' : ''}${Math.round(a.hours)}`,
        fill: 'var(--color-ink)',
        size: 12,
        weight: 600,
        anchor: 'middle' as const,
      }))

  const labels: Label[] = [
    { key: 't-sun', x: X0, y: 26, text: 'SUNLIGHT', fill: 'var(--color-sun)', size: 12, weight: 600, spacing: 1.4 },
    { key: 't-earth', x: X0, y: 116, text: 'CONTACT WITH EARTH', fill: 'var(--color-earth)', size: 12, weight: 600, spacing: 1.4 },
    // Short enough to stay whole in the first screen width at 390 (V135).
    { key: 't-neither', x: X0, y: 206, text: 'DARK AND OUT OF CONTACT', fill: 'var(--color-alert)', size: 12, weight: 600, spacing: 1.4 },
    ...hourLabels(metrics.sun.arcs, 64, 's'),
    ...hourLabels(metrics.earth.arcs, 154, 'e'),
    ...(worstCompound ? [worstLabel(worstCompound)] : []),
  ]
  /**
   * The longest dark-and-silent stretch, named beside it: to its right where
   * the words fit inside the chart, else to its left pointing back, else the
   * short form on the side with more room. Never cut at the chart's edge.
   */
  function worstLabel(c: { startH: number; hours: number; openStart?: boolean; openEnd?: boolean }): Label {
    const h = hoursWithUnit(c.hours, 0, cut(c))
    const long = `${h}, the longest time dark and out of contact`
    const short = `${h}, longest dark and out of contact`
    // About 7.4 user units a character at 13 px semibold, the arrow included.
    const fits = (s: string) => (s.length + 2) * 7.4
    const right = x(c.startH) + w(c.hours) + 10
    const left = x(c.startH) - 10
    const base = { key: 'worst', y: 238, fill: 'var(--color-alert)', size: 13, weight: 600 }
    if (right + fits(long) <= X1) return { ...base, x: right, text: `← ${long}` }
    if (left - fits(long) >= X0) return { ...base, x: left, text: `${long} →`, anchor: 'end' }
    return X1 - right >= left - X0
      ? { ...base, x: Math.min(right, X1 - fits(short)), text: `← ${short}` }
      : { ...base, x: Math.max(left, X0 + fits(short)), text: `${short} →`, anchor: 'end' }
  }
  const drawLabel = (l: Label, mask = false) => (
    <text
      key={l.key}
      x={l.x}
      y={l.y}
      textAnchor={l.anchor}
      fill={mask ? 'black' : l.fill}
      stroke={mask ? 'black' : undefined}
      strokeWidth={mask ? 8 : undefined}
      strokeLinejoin={mask ? 'round' : undefined}
      fontFamily="var(--font-sans)"
      fontSize={l.size}
      fontWeight={l.weight}
      letterSpacing={l.spacing}
    >
      {l.text}
    </text>
  )
  const nowX = x(metrics.windowStartH + cursorH)

  return (
    <svg
      width={width}
      height="300"
      viewBox="0 0 1020 300"
      className={className}
      role="img"
      aria-label={
        `Timeline of ${Math.round(win)} hours, ${shortDate(at(0))} to ${shortDate(at(win))}. There are ${metrics.sun.arcs.filter((a) => !a.up).length} ` +
        `nights, the longest ${metrics.sun.longestDownOpen ? 'at least' : 'about'} ` +
        `${Math.round(metrics.sun.longestDownH)} hours. There are ` +
        `${metrics.earth.arcs.filter((a) => !a.up).length} times without contact with Earth, the longest ` +
        `${metrics.earth.longestDownOpen ? 'at least' : 'about'} ${Math.round(metrics.earth.longestDownH)} hours. ` +
        `There are ${metrics.compound.length} times with neither, the longest about ` +
        `${Math.round(metrics.worstCompoundH)} hours. Hatched bands at each crossing show its timing margin.`
      }
    >
      <defs>
        {/* The "now" line stops short of every word it would run through:
            white shows the line, the words (drawn thick in black) hide it. */}
        <mask id={maskId} maskUnits="userSpaceOnUse" x="0" y="0" width="1020" height="300">
          <rect x="0" y="0" width="1020" height="300" fill="white" />
          {labels.map((l) => drawLabel(l, true))}
        </mask>
      </defs>

      <rect x={X0} y="36" width={X1 - X0} height={TRACK_H} fill="var(--color-sun-fill)" />
      {metrics.sun.arcs
        .filter((a) => !a.up)
        .map((a, i) => (
          <rect
            key={i}
            x={x(a.startH)}
            y="36"
            width={w(a.hours)}
            height={TRACK_H}
            fill={a === worstSun && sunPast ? 'url(#pw-alert)' : 'url(#pw-blocked)'}
          />
        ))}
      {sunBands.map((b, i) => (
        <rect key={`sb${i}`} x={x(b.fromH)} y="36" width={w(b.toH - b.fromH)} height={TRACK_H} fill="url(#pw-uncertain)" {...bandProps} />
      ))}
      <rect x={X0} y="36" width={X1 - X0} height={TRACK_H} fill="none" stroke="var(--color-line)" />

      <rect x={X0} y="126" width={X1 - X0} height={TRACK_H} fill="var(--color-earth-fill)" />
      {metrics.earth.arcs
        .filter((a) => !a.up)
        .map((a, i) => (
          <rect key={i} x={x(a.startH)} y="126" width={w(a.hours)} height={TRACK_H} fill={a === worstEarth ? 'url(#pw-alert)' : 'url(#pw-blocked)'} />
        ))}
      {earthBands.map((b, i) => (
        <rect key={`eb${i}`} x={x(b.fromH)} y="126" width={w(b.toH - b.fromH)} height={TRACK_H} fill="url(#pw-uncertain)" {...bandProps} />
      ))}
      <rect x={X0} y="126" width={X1 - X0} height={TRACK_H} fill="none" stroke="var(--color-line)" />

      <rect x={X0} y="216" width={X1 - X0} height="32" fill="var(--color-dark-fill)" />
      {metrics.compound.map((c, i) => (
        <rect key={i} x={x(c.startH)} y="216" width={w(c.hours)} height="32" fill="url(#pw-alert)" />
      ))}
      <rect x={X0} y="216" width={X1 - X0} height="32" fill="none" stroke="var(--color-line)" />

      <line x1={nowX} y1="30" x2={nowX} y2="254" stroke="var(--color-ink)" strokeWidth="2" mask={`url(#${maskId})`} />

      {labels.map((l) => drawLabel(l))}

      <line x1={X0} y1="262" x2={X1} y2="262" stroke="var(--color-line-strong)" strokeWidth="1.5" />
      <g fill="var(--color-ink-3)" fontFamily="var(--font-sans)" fontSize="12" textAnchor="middle">
        {[0, 0.25, 0.5, 0.75, 1].map((f) => (
          <g key={f}>
            <line
              x1={X0 + f * (X1 - X0)}
              y1="262"
              x2={X0 + f * (X1 - X0)}
              y2="270"
              stroke="var(--color-line-strong)"
              strokeWidth="1.5"
            />
            <text x={X0 + f * (X1 - X0)} y="286">
              {axisDate(at(f * win), win)}
            </text>
          </g>
        ))}
      </g>
    </svg>
  )
}

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** A tick as a date ("21 Mar"), with the time of day when the dates span only a few days. */
export function axisDate(ms: number, windowHours: number): string {
  const d = new Date(ms)
  const day = `${d.getUTCDate()} ${MON[d.getUTCMonth()]}`
  if (windowHours > 72) return day
  return `${day} ${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`
}
