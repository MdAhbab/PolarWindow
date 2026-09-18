import type { SiteMetrics } from '../lib/types'
import { hoursWithUnit } from '../lib/format'

const X0 = 40
const X1 = 980
const TRACK_H = 46

/**
 * S5 — the window hour by hour, three tracks deep.
 *
 * The third track is the one nobody else draws: the intersection of "no Sun"
 * and "no link". It is the number the autonomy packet is sized from, and it is
 * always smaller than either gap alone, which is exactly why quoting them
 * separately understates the problem.
 */
export function BlackoutTimeline({
  metrics,
  cursorH,
  width = 1000,
  className = '',
}: {
  metrics: SiteMetrics
  cursorH: number
  width?: number
  className?: string
}) {
  const win = metrics.windowHours
  const x = (h: number) => X0 + ((h - metrics.windowStartH) / win) * (X1 - X0)
  const w = (h: number) => (h / win) * (X1 - X0)

  const worstSun = metrics.sun.longestDownArc
  const worstEarth = metrics.earth.longestDownArc
  const worstCompound = metrics.compound.reduce(
    (b, c) => (!b || c.hours > b.hours ? c : b),
    undefined as (typeof metrics.compound)[number] | undefined,
  )

  return (
    <svg
      width={width}
      height="300"
      viewBox="0 0 1020 300"
      className={className}
      role="img"
      aria-label={
        `Timeline of ${Math.round(win)} hours. Sunlight has ${metrics.sun.arcs.filter((a) => !a.up).length} ` +
        `dark periods, the longest about ${Math.round(metrics.sun.longestDownH)} hours. The Earth link has ` +
        `${metrics.earth.arcs.filter((a) => !a.up).length} blackouts, the longest about ` +
        `${Math.round(metrics.earth.longestDownH)} hours. There are ${metrics.compound.length} periods with ` +
        `neither, the worst about ${Math.round(metrics.worstCompoundH)} hours.`
      }
    >
      <text x={X0} y="26" fill="var(--color-sun)" fontFamily="var(--font-sans)" fontSize="12" fontWeight="600" letterSpacing="1.4">
        SUNLIGHT
      </text>
      <rect x={X0} y="36" width={X1 - X0} height={TRACK_H} fill="var(--color-sun-fill)" />
      {metrics.sun.arcs
        .filter((a) => !a.up)
        .map((a, i) => (
          <g key={i}>
            <rect x={x(a.startH)} y="36" width={w(a.hours)} height={TRACK_H} fill={a === worstSun ? 'url(#pw-alert)' : 'url(#pw-blocked)'} />
            {w(a.hours) > 34 && (
              <text
                x={x(a.startH) + w(a.hours) / 2}
                y="64"
                textAnchor="middle"
                fill="var(--color-ink)"
                fontFamily="var(--font-sans)"
                fontSize="12"
                fontWeight="600"
              >
                {Math.round(a.hours)}
              </text>
            )}
          </g>
        ))}
      <rect x={X0} y="36" width={X1 - X0} height={TRACK_H} fill="none" stroke="var(--color-line)" />

      <text x={X0} y="116" fill="var(--color-earth)" fontFamily="var(--font-sans)" fontSize="12" fontWeight="600" letterSpacing="1.4">
        EARTH LINK
      </text>
      <rect x={X0} y="126" width={X1 - X0} height={TRACK_H} fill="var(--color-earth-fill)" />
      {metrics.earth.arcs
        .filter((a) => !a.up)
        .map((a, i) => (
          <g key={i}>
            <rect x={x(a.startH)} y="126" width={w(a.hours)} height={TRACK_H} fill={a === worstEarth ? 'url(#pw-alert)' : 'url(#pw-blocked)'} />
            {w(a.hours) > 34 && (
              <text
                x={x(a.startH) + w(a.hours) / 2}
                y="154"
                textAnchor="middle"
                fill="var(--color-ink)"
                fontFamily="var(--font-sans)"
                fontSize="12"
                fontWeight="600"
              >
                {Math.round(a.hours)}
              </text>
            )}
          </g>
        ))}
      <rect x={X0} y="126" width={X1 - X0} height={TRACK_H} fill="none" stroke="var(--color-line)" />

      <text x={X0} y="206" fill="var(--color-alert)" fontFamily="var(--font-sans)" fontSize="12" fontWeight="600" letterSpacing="1.4">
        NEITHER — DARK AND SILENT AT ONCE
      </text>
      <rect x={X0} y="216" width={X1 - X0} height="32" fill="var(--color-dark-fill)" />
      {metrics.compound.map((c, i) => (
        <rect key={i} x={x(c.startH)} y="216" width={w(c.hours)} height="32" fill="url(#pw-alert)" />
      ))}
      <rect x={X0} y="216" width={X1 - X0} height="32" fill="none" stroke="var(--color-line)" />
      {worstCompound && (
        <text
          x={Math.min(X1 - 200, x(worstCompound.startH) + w(worstCompound.hours) + 10)}
          y="238"
          fill="var(--color-alert)"
          fontFamily="var(--font-sans)"
          fontSize="13"
          fontWeight="600"
        >
          ← {hoursWithUnit(worstCompound.hours)}, the worst compound event
        </text>
      )}

      <line
        x1={x(metrics.windowStartH + cursorH)}
        y1="30"
        x2={x(metrics.windowStartH + cursorH)}
        y2="254"
        stroke="var(--color-ink)"
        strokeWidth="2"
      />

      <line x1={X0} y1="262" x2={X1} y2="262" stroke="var(--color-line-strong)" strokeWidth="1.5" />
      <g fill="var(--color-ink-3)" fontFamily="var(--font-mono)" fontSize="11" textAnchor="middle">
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
              h{Math.round(f * win)}
            </text>
          </g>
        ))}
      </g>
    </svg>
  )
}
