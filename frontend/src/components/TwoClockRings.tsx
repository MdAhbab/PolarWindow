import type { Arc, SiteMetrics, TrackSample } from '../lib/types'
import { useReducedMotion } from '../hooks/useMotion'
import { bearing, degrees, hoursSpoken } from '../lib/format'
import { crossingBands, type Band } from '../lib/bands'

const CX = 260
const CY = 260
const R_SUN = 200
const R_EARTH = 150
const W = 34
const C_SUN = 2 * Math.PI * R_SUN
const C_EARTH = 2 * Math.PI * R_EARTH


/**
 * Turn an alternating arc list into an SVG stroke-dasharray.
 *
 * The arcs already alternate above/below, so the dasharray is just their
 * lengths — except when the window opens with the body already below the
 * skyline, where a zero-length "on" has to go first.
 */
function dashFromArcs(arcs: Arc[], windowHours: number, circumference: number): string {
  if (!arcs.length) return `0 ${circumference}`
  const lens = arcs.map((a) => (a.hours / windowHours) * circumference)
  const parts = arcs[0].up ? lens : [0, ...lens]
  return parts.map((n) => n.toFixed(2)).join(' ')
}

/** Crossing bands as a dasharray: gap to the first band, band, gap, band... */
function dashFromBands(bands: Band[], windowHours: number, circumference: number): string | null {
  if (!bands.length) return null
  const parts: number[] = []
  let at = 0
  for (const b of bands) {
    parts.push(((b.fromH - at) / windowHours) * circumference)
    parts.push(((b.toH - b.fromH) / windowHours) * circumference)
    at = b.toH
  }
  parts.push(((windowHours - at) / windowHours) * circumference)
  // A dasharray starts with a dash; the leading 0 makes it start with the gap.
  return [0, ...parts].map((n) => Math.max(0, n).toFixed(2)).join(' ')
}

/** Terrain above the horizon blocks; a body below its geometric horizon does not need to be. */
export const TERRAIN_BLOCKER_MIN_EL_DEG = 0.05

function sampleAt(samples: TrackSample[], windowStartH: number, cursorH: number): TrackSample | undefined {
  if (!samples.length) return undefined
  const t = windowStartH + cursorH
  const step = samples.length > 1 ? samples[1].tH - samples[0].tH : 1
  const i = Math.max(0, Math.min(samples.length - 1, Math.round((t - samples[0].tH) / step)))
  return samples[i]
}

/**
 * The signature screen's one drawing.
 *
 * Filled arc means above this site's own horizon; hatched means blocked by its
 * own terrain. Sun and Earth are drawn identically at different radii, so the
 * eye compares them without being taught anything first.
 */
export function TwoClockRings({
  metrics,
  cursorH,
  maxSize = 540,
  showCentre = true,
  className = '',
}: {
  metrics: SiteMetrics
  cursorH: number
  maxSize?: number
  showCentre?: boolean
  className?: string
}) {
  const reduced = useReducedMotion()
  // M2 — the rings arrive with a short clockwise turn into place, from day 0,
  // on every new site or dates: transform and opacity only, restarted by the
  // key below. Under reduced motion they are simply there.
  const arrive = reduced ? '' : 'pw-ring-in'
  const arrivalKey = `${metrics.siteId}|${metrics.windowStartH}|${metrics.windowHours}`

  const win = metrics.windowHours
  const sunDash = dashFromArcs(metrics.sun.arcs, win, C_SUN)
  const earthDash = dashFromArcs(metrics.earth.arcs, win, C_EARTH)
  const sunBands = dashFromBands(crossingBands(metrics.sun.arcs, win), win, C_SUN)
  const earthBands = dashFromBands(crossingBands(metrics.earth.arcs, win), win, C_EARTH)
  // M6 in code: breathe under full motion, static at 0.34 opacity otherwise.
  const bandProps = reduced ? { strokeOpacity: 0.34 } : { className: 'breathe' }
  const nowAngle = (cursorH / win) * 360

  const worstDark = metrics.sun.longestDownArc
  const worstAngle = worstDark ? (((worstDark.startH + worstDark.endH) / 2 - metrics.windowStartH) / win) * 360 : null

  const sunNow = sampleAt(metrics.sun.samples, metrics.windowStartH, cursorH)
  const earthNow = sampleAt(metrics.earth.samples, metrics.windowStartH, cursorH)

  return (
    <svg
      viewBox="0 0 520 520"
      style={{ maxWidth: maxSize }}
      className={`h-auto w-full ${className}`}
      role="img"
      aria-label={describe(metrics)}
    >
      <desc>
        Filled arc means above the local horizon. Hatched arc means below it or blocked by terrain.
        Finer hatching at each crossing shows that crossing's timing margin. The same arcs are available
        as a table.
      </desc>

      {/* day marks at 0, 1/4, 1/2, 3/4 of the window */}
      <g stroke="var(--color-line-strong)" strokeWidth="1.5">
        <line x1={CX} y1="26" x2={CX} y2="38" />
        <line x1={CX} y1="26" x2={CX} y2="38" transform={`rotate(90 ${CX} ${CY})`} />
        <line x1={CX} y1="26" x2={CX} y2="38" transform={`rotate(180 ${CX} ${CY})`} />
        <line x1={CX} y1="26" x2={CX} y2="38" transform={`rotate(270 ${CX} ${CY})`} />
      </g>
      <g fill="var(--color-ink-3)" fontFamily="var(--font-mono)" fontSize="12">
        <text x={CX} y="18" textAnchor="middle">
          day 0
        </text>
        <text x="518" y={CY - 12} textAnchor="end">
          day {Math.round(win / 96)}
        </text>
      </g>

      <g key={arrivalKey} className={arrive} style={{ transformOrigin: `${CX}px ${CY}px`, transformBox: 'view-box' }}>
        <circle cx={CX} cy={CY} r={R_SUN} fill="none" stroke="url(#pw-blocked)" strokeWidth={W} />
        <circle
          cx={CX}
          cy={CY}
          r={R_SUN}
          fill="none"
          stroke="var(--color-sun-fill)"
          strokeWidth={W}
          strokeDasharray={sunDash}
          transform={`rotate(-90 ${CX} ${CY})`}
          className="pw-sun-glow"
        />
        <circle cx={CX} cy={CY} r={R_EARTH} fill="none" stroke="url(#pw-blocked)" strokeWidth={W} />
        <circle
          cx={CX}
          cy={CY}
          r={R_EARTH}
          fill="none"
          stroke="var(--color-earth-fill)"
          strokeWidth={W}
          strokeDasharray={earthDash}
          transform={`rotate(-90 ${CX} ${CY})`}
        />
        {sunBands && (
          <circle
            cx={CX}
            cy={CY}
            r={R_SUN}
            fill="none"
            stroke="url(#pw-uncertain)"
            strokeWidth={W}
            strokeDasharray={sunBands}
            transform={`rotate(-90 ${CX} ${CY})`}
            {...bandProps}
          />
        )}
        {earthBands && (
          <circle
            cx={CX}
            cy={CY}
            r={R_EARTH}
            fill="none"
            stroke="url(#pw-uncertain)"
            strokeWidth={W}
            strokeDasharray={earthBands}
            transform={`rotate(-90 ${CX} ${CY})`}
            {...bandProps}
          />
        )}
      </g>

      <g fill="none" stroke="var(--color-line)" strokeWidth="1">
        <circle cx={CX} cy={CY} r={R_SUN + W / 2} />
        <circle cx={CX} cy={CY} r={R_SUN - W / 2} />
        <circle cx={CX} cy={CY} r={R_EARTH + W / 2} />
        <circle cx={CX} cy={CY} r={R_EARTH - W / 2} />
      </g>

      {worstAngle !== null && (
        <g transform={`rotate(${worstAngle} ${CX} ${CY})`}>
          <line x1={CX} y1="30" x2={CX} y2="60" stroke="var(--color-alert)" strokeWidth="2.5" />
        </g>
      )}

      <g transform={`rotate(${nowAngle} ${CX} ${CY})`}>
        <line x1={CX} y1="22" x2={CX} y2="128" stroke="var(--color-ink)" strokeWidth="2" />
        <path d={`M${CX - 5} 22 L${CX + 5} 22 L${CX} 32 Z`} fill="var(--color-ink)" />
      </g>

      {showCentre && (
        <CentreDial cursorH={cursorH} sun={sunNow} earth={earthNow} windowHours={win} />
      )}
    </svg>
  )
}

/**
 * Two small gauges: where each body is right now, against the skyline at its
 * own bearing. Separate gauges rather than one shared horizon, because the two
 * bodies are in different parts of the sky and a single silhouette would be a
 * lie about at least one of them.
 */
function CentreDial({
  cursorH,
  sun,
  earth,
  windowHours,
}: {
  cursorH: number
  sun?: TrackSample
  earth?: TrackSample
  windowHours: number
}) {
  const day = Math.floor(cursorH / 24)
  return (
    <g>
      <text
        x={CX}
        y={178}
        textAnchor="middle"
        fill="var(--color-ink-3)"
        fontFamily="var(--font-sans)"
        fontSize="12"
        fontWeight="600"
        letterSpacing="1.6"
      >
        NOW · DAY {day} OF {Math.round(windowHours / 24)}
      </text>
      <Gauge x={CX - 62} label="SUN" sample={sun} tone="var(--color-sun)" />
      <Gauge x={CX + 62} label="EARTH" sample={earth} tone="var(--color-earth)" />
    </g>
  )
}

const G_TOP = 210
const G_BOTTOM = 300
const G_HALF = 44
const EL_RANGE = 8

function elToY(el: number): number {
  const mid = (G_TOP + G_BOTTOM) / 2
  return mid - (Math.max(-EL_RANGE, Math.min(EL_RANGE, el)) / EL_RANGE) * ((G_BOTTOM - G_TOP) / 2)
}

function Gauge({ x, label, sample, tone }: { x: number; label: string; sample?: TrackSample; tone: string }) {
  const zero = elToY(0)
  const el = sample?.elDeg ?? 0
  const maskEl = sample?.maskElDeg ?? 0
  const up = (sample?.marginDeg ?? 0) > 0
  const yEl = elToY(el)
  const ySky = elToY(maskEl)

  return (
    <g>
      {/* terrain below the skyline at this body's bearing */}
      <rect x={x - G_HALF} y={ySky} width={G_HALF * 2} height={G_BOTTOM - ySky} fill="var(--color-terrain-low)" />
      <line x1={x - G_HALF} y1={ySky} x2={x + G_HALF} y2={ySky} stroke="var(--color-terrain-high)" strokeWidth="2" />
      {/* flat horizon reference */}
      <line
        x1={x - G_HALF}
        y1={zero}
        x2={x + G_HALF}
        y2={zero}
        stroke="var(--color-line-strong)"
        strokeWidth="1"
        strokeDasharray="4 4"
      />
      {up ? (
        <circle cx={x} cy={yEl} r="9" fill={tone} />
      ) : (
        <circle cx={x} cy={yEl} r="9" fill="none" stroke={tone} strokeWidth="2" strokeDasharray="3 2.5" />
      )}
      <text
        x={x}
        y={G_TOP - 6}
        textAnchor="middle"
        fill={tone}
        fontFamily="var(--font-sans)"
        fontSize="12"
        fontWeight="600"
      >
        {label} {sample ? degrees(el, 1) : '—'}
      </text>
      <text
        x={x}
        y={G_BOTTOM + 16}
        textAnchor="middle"
        fill="var(--color-ink-2)"
        fontFamily="var(--font-sans)"
        fontSize="11"
      >
        {sample ? (up ? 'visible' : 'behind the skyline') : 'computing'}
      </text>
    </g>
  )
}

function describe(m: SiteMetrics): string {
  const dark = m.sun.longestDownArc
  const terrain =
    dark?.blockedByElDeg !== undefined && dark.blockedByElDeg > TERRAIN_BLOCKER_MIN_EL_DEG
  return (
    `Sun and Earth rings over ${Math.round(m.windowHours)} hours. ` +
    `Outer amber ring: the Sun is above the local skyline for about ${Math.round(m.sun.upHours)} hours ` +
    `in ${m.sun.arcs.filter((a) => a.up).length} stretches. ` +
    `Inner cyan ring: Earth is above it for about ${Math.round(m.earth.upHours)} hours. ` +
    (dark
      ? `The longest night is ${hoursSpoken(dark.hours, m.sun.longestDownOpen)}` +
        (m.sun.longestDownOpen ? ', cut short by the chosen dates' : '') +
        (terrain
          ? `, caused by a ridge at bearing ${bearing(dark.blockedByBearingDeg ?? 0)}.`
          : ', with the Sun below the horizon rather than behind a ridge.')
      : 'The Sun does not set on these dates.')
  )
}
