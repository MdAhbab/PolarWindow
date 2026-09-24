import { useEffect, useRef, useState } from 'react'
import type { SiteMetrics, TrackSample } from '../lib/types'
import { useReducedMotion, easeOut } from '../hooks/useMotion'
import { bearing, compass, degrees } from '../lib/format'

const X0 = 60
const X1 = 980
const Y_TOP = 24
const Y_BOT = 400
const EL_MAX = 8
const EL_MIN = -8

const xOf = (az: number) => X0 + (((az % 360) + 360) % 360) * ((X1 - X0) / 360)
const yOf = (el: number) => Y_BOT - ((Math.max(EL_MIN, Math.min(EL_MAX, el)) - EL_MIN) / (EL_MAX - EL_MIN)) * (Y_BOT - Y_TOP)

function pathFromSamples(samples: TrackSample[], loop: boolean): string {
  if (!samples.length) return ''
  const pts = loop
    ? samples
    : [...samples].sort((a, b) => a.azDeg - b.azDeg)
  let d = ''
  let prevX = NaN
  for (const s of pts) {
    const x = xOf(s.azDeg)
    const y = yOf(s.elDeg)
    // Don't draw the seam where azimuth wraps 360 -> 0.
    const jump = Number.isFinite(prevX) && Math.abs(x - prevX) > (X1 - X0) / 3
    d += `${d === '' || jump ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)} `
    prevX = x
  }
  return d.trim()
}

/**
 * S4 — standing at the site, looking out.
 *
 * The dashed line is where the horizon would be on a smooth Moon. Everything
 * between it and the grey silhouette is rock a globe-only calculation ignores,
 * and at this latitude the Sun spends its whole day inside that band.
 */
export function HorizonProfile({
  metrics,
  cursorH,
  width = 1000,
  height = 430,
  className = '',
}: {
  metrics: SiteMetrics
  cursorH: number
  width?: number
  height?: number
  className?: string
}) {
  const reduced = useReducedMotion()
  const [reveal, setReveal] = useState(reduced ? 1 : 0)
  const raf = useRef(0)

  // M5 — the Sun path traces along the skyline on entry, so you watch it run
  // into the ridge rather than finding it already stuck there.
  useEffect(() => {
    if (reduced) {
      setReveal(1)
      return
    }
    setReveal(0)
    const start = performance.now()
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / 900)
      setReveal(easeOut(p))
      if (p < 1) raf.current = requestAnimationFrame(tick)
    }
    raf.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf.current)
  }, [metrics.siteId, reduced])

  const mask = metrics.mask
  const n = mask.elDeg.length
  const skyline: string[] = []
  const upper: string[] = []
  const lower: string[] = []
  for (let b = 0; b <= n; b++) {
    const i = b % n
    const az = b === n ? 359.999 : (b * 360) / n
    const x = xOf(az).toFixed(1)
    skyline.push(`${b === 0 ? 'M' : 'L'}${x} ${yOf(mask.elDeg[i]).toFixed(1)}`)
    upper.push(`${b === 0 ? 'M' : 'L'}${x} ${yOf(mask.elDeg[i] + mask.tolDeg[i]).toFixed(1)}`)
    lower.push(`L${x} ${yOf(mask.elDeg[i] - mask.tolDeg[i]).toFixed(1)}`)
  }
  const skyTop = skyline
  const fillPath = `${skyline.join(' ')} L${X1} ${Y_BOT} L${X0} ${Y_BOT} Z`
  // The skyline's own error, bearing by bearing: +- tol_deg, which the server
  // derives from the blocking sample's range and its elevation model's
  // vertical error. It used to be a constant 11 px stroke, which drew the same
  // margin for a 45 m blocker (+-2.5 deg) and a 30 km one (+-0.008 deg).
  const bandPath = `${upper.join(' ')} ${lower.reverse().join(' ')} Z`

  const sunPath = pathFromSamples(metrics.sun.samples, false)
  const earthPath = pathFromSamples(metrics.earth.samples, true)

  const worst = metrics.sun.longestDownArc
  const blockAz = worst?.blockedByBearingDeg
  const nowSun = nearest(metrics.sun.samples, metrics.windowStartH + cursorH)

  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 1040 430"
      className={className}
      role="img"
      aria-label={describe(metrics)}
    >
      <rect x={X0} y={Y_TOP} width={X1 - X0} height={Y_BOT - Y_TOP} fill="var(--color-psr)" />

      <g stroke="var(--color-inset)" strokeWidth="1">
        {[-8, -4, 4, 8].map((e) => (
          <line key={e} x1={X0} y1={yOf(e)} x2={X1} y2={yOf(e)} />
        ))}
      </g>
      <g fill="var(--color-ink-3)" fontFamily="var(--font-mono)" fontSize="11" textAnchor="end">
        {[8, 4, 0, -4, -8].map((e) => (
          <text key={e} x={X0 - 8} y={yOf(e) + 4}>
            {e > 0 ? `+${e}` : e}°
          </text>
        ))}
      </g>

      {/* the horizon a globe-only tool would draw */}
      <line x1={X0} y1={yOf(0)} x2={X1} y2={yOf(0)} stroke="var(--color-terrain-mid)" strokeWidth="1.5" strokeDasharray="7 6" />
      <rect x={X0 + 4} y={yOf(0) - 22} width="330" height="17" fill="var(--color-psr)" />
      <text x={X0 + 8} y={yOf(0) - 9} fontFamily="var(--font-sans)" fontSize="12" fontWeight="600" fill="var(--color-ink-3)">
        FLAT HORIZON 0°: what a tool that ignores terrain draws
      </text>

      {/* the bearings that cost the longest night */}
      {worst && blockAz !== undefined && (
        <rect
          x={xOf(blockAz) - 26}
          y={Y_TOP}
          width="52"
          height={Y_BOT - Y_TOP}
          fill="url(#pw-blocked)"
          opacity="0.75"
        />
      )}

      <path d={fillPath} fill="var(--color-terrain-low)" />
      <path d={skyTop.join(' ')} fill="none" stroke="var(--color-terrain-high)" strokeWidth="2.5" />
      <path
        d={bandPath}
        fill="url(#pw-uncertain)"
        stroke="none"
        {...(reduced ? { fillOpacity: 0.34 } : { className: 'breathe' })}
      />

      <path
        d={earthPath}
        fill="none"
        stroke="var(--color-earth)"
        strokeWidth="3"
        strokeDasharray="4000"
        strokeDashoffset={4000 * (1 - reveal)}
      />
      <path
        d={sunPath}
        fill="none"
        stroke="var(--color-sun)"
        strokeWidth="3.5"
        strokeDasharray="4000"
        strokeDashoffset={4000 * (1 - reveal)}
      />

      {metrics.earth.samples.length > 0 && (
        <text
          x={xOf(metrics.earth.samples[0].azDeg) + 14}
          y={yOf(7.4)}
          fontFamily="var(--font-sans)"
          fontSize="12"
          fontWeight="600"
          fill="var(--color-earth)"
        >
          EARTH: a small loop in the sky (libration), not a path
        </text>
      )}

      {nowSun && (
        <g>
          <line x1={xOf(nowSun.azDeg)} y1={Y_TOP} x2={xOf(nowSun.azDeg)} y2={Y_BOT} stroke="var(--color-ink)" strokeWidth="2" />
          <path
            d={`M${xOf(nowSun.azDeg) - 6} ${Y_TOP} L${xOf(nowSun.azDeg) + 6} ${Y_TOP} L${xOf(nowSun.azDeg)} ${Y_TOP + 12} Z`}
            fill="var(--color-ink)"
          />
          <circle
            cx={xOf(nowSun.azDeg)}
            cy={yOf(nowSun.elDeg)}
            r="10"
            fill={nowSun.marginDeg > 0 ? 'var(--color-sun-fill)' : 'none'}
            stroke="var(--color-sun)"
            strokeWidth="3"
            strokeDasharray={nowSun.marginDeg > 0 ? undefined : '4 3.5'}
          />
        </g>
      )}

      <line x1={X0} y1={Y_BOT} x2={X1} y2={Y_BOT} stroke="var(--color-line-strong)" strokeWidth="1.5" />
      <g fill="var(--color-ink-2)" fontFamily="var(--font-sans)" fontSize="13" fontWeight="600" letterSpacing="1.2" textAnchor="middle">
        {[0, 90, 180, 270, 359.999].map((az, i) => (
          <text key={i} x={xOf(az)} y={Y_BOT + 20}>
            {compass(az)}
          </text>
        ))}
      </g>
      {nowSun && (
        <text
          x={xOf(nowSun.azDeg)}
          y={Y_BOT + 38}
          textAnchor="middle"
          fontFamily="var(--font-mono)"
          fontSize="11"
          fill="var(--color-ink)"
        >
          {bearing(nowSun.azDeg)} now
        </text>
      )}
    </svg>
  )
}

function nearest(samples: TrackSample[], t: number): TrackSample | undefined {
  if (!samples.length) return undefined
  const step = samples.length > 1 ? samples[1].tH - samples[0].tH : 1
  const i = Math.max(0, Math.min(samples.length - 1, Math.round((t - samples[0].tH) / step)))
  return samples[i]
}

function describe(m: SiteMetrics): string {
  const w = m.sun.longestDownArc
  return (
    `Horizon profile. The terrain skyline peaks at ${degrees(m.mask.maxElDeg, 1)} at bearing ` +
    `${bearing(m.mask.maxElBearingDeg)}. The Sun's path over one lunar day is drawn against it. ` +
    (w
      ? `It passes behind terrain near bearing ${bearing(w.blockedByBearingDeg ?? 0)}, which is the ` +
        `${Math.round(w.hours)} hour night.`
      : 'It clears the skyline at every bearing on these dates.')
  )
}
