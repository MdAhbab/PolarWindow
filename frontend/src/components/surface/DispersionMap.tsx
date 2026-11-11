import { useId, useState, type PointerEvent } from 'react'
import type { HeatmapDTO } from '../../lib/api/surface.types'
import { num } from './helpers'
import { useWidth } from './parts'

/** Slope bins in degrees: the ramp is one neutral hue, light to dark (dark to light in the dark theme). */
export const SLOPE_BINS = [0, 5, 10, 15, 20, 30] as const
const MIX = [8, 22, 36, 50, 64, 80]

/** Which bin a slope falls in (the last is open-ended). */
export function slopeBin(deg: number): number {
  let b = 0
  SLOPE_BINS.forEach((edge, i) => {
    if (deg >= edge) b = i
  })
  return b
}

export function binLabel(i: number): string {
  const lo = SLOPE_BINS[i]
  const hi = SLOPE_BINS[i + 1]
  return hi === undefined ? `${lo}° and over` : `${lo}–${hi}°`
}

const fillFor = (i: number) => `color-mix(in oklab, var(--color-ink) ${MIX[i]}%, var(--color-panel))`

/** A round length for the scale bar: about a quarter of the map's width. */
export function scaleBarMetres(widthM: number): number {
  const target = widthM / 4
  const mag = 10 ** Math.floor(Math.log10(Math.max(target, 1)))
  return [1, 2, 5, 10].map((m) => m * mag).filter((v) => v <= target).pop() ?? mag
}

/**
 * The slope under the landing ellipse, north up: each cell is the slope over
 * the baseline, binned on one neutral ramp; unknown cells wear their own
 * cross-hatch; the ellipse is outlined and the drawn landing points sit on
 * top, a cross where the slope is over the lander's limit and a dot where it
 * is not, so the two are told apart by shape.
 */
export function DispersionMap({ h, limitDeg }: { h: HeatmapDTO; limitDeg: number }) {
  const [ref, W] = useWidth<HTMLDivElement>(420)
  const [hover, setHover] = useState<{ r: number; c: number } | null>(null)
  const pid = useId().replace(/:/g, '')
  const widthM = h.nx * h.cell_m
  const heightM = h.ny * h.cell_m
  const maxW = Math.min(W, 560)
  const s = Math.min(maxW / widthM, 520 / heightM)
  const mw = widthM * s
  const mh = heightM * s
  const PAD_B = 34
  const X = (east: number) => (east - h.east_min_m) * s
  const Y = (north: number) => mh - (north - h.north_min_m) * s
  const cw = h.cell_m * s
  const bar = scaleBarMetres(widthM)
  const outline = h.outline.east_m.map((e, i) => `${i ? 'L' : 'M'}${X(e).toFixed(1)} ${Y(h.outline.north_m[i]).toFixed(1)}`).join('') + 'Z'
  const unknown = h.slope_deg.flat().filter((v) => v === null).length

  const onMove = (e: PointerEvent<SVGRectElement>) => {
    const box = e.currentTarget.getBoundingClientRect()
    const c = Math.floor((e.clientX - box.left) / cw)
    const r = h.ny - 1 - Math.floor((e.clientY - box.top) / cw)
    if (r >= 0 && r < h.ny && c >= 0 && c < h.nx) setHover({ r, c })
  }
  const hv = hover ? h.slope_deg[hover.r]?.[hover.c] : undefined

  return (
    <figure className="m-0 flex min-w-0 flex-col gap-2">
      <div ref={ref} className="min-w-0">
        <svg
          width={mw}
          height={mh + PAD_B}
          viewBox={`0 0 ${mw} ${mh + PAD_B}`}
          role="img"
          aria-label={`Slope map, north up, ${num(widthM, 0)} by ${num(heightM, 0)} metres, with the landing ellipse outlined and ${h.points.east_m.length} drawn landing points. Cells are the slope over ${h.baseline_m} m.${unknown ? ` ${unknown} cells have no slope.` : ''}`}
          className="block max-w-full"
        >
          <defs>
            <pattern id={`${pid}-unk`} width="6" height="6" patternUnits="userSpaceOnUse">
              <rect width="6" height="6" fill="var(--color-panel)" />
              <path d="M0 0 L6 6 M6 0 L0 6" stroke="var(--color-ink-3)" strokeWidth="1" />
            </pattern>
          </defs>
          {h.slope_deg.map((row, r) =>
            row.map((v, c) => (
              <rect
                key={`${r}-${c}`}
                x={c * cw}
                y={mh - (r + 1) * cw}
                width={cw + 0.5}
                height={cw + 0.5}
                fill={v === null ? `url(#${pid}-unk)` : fillFor(slopeBin(v))}
              />
            )),
          )}
          <path d={outline} fill="none" stroke="var(--color-panel)" strokeWidth={5} />
          <path d={outline} fill="none" stroke="var(--color-ink)" strokeWidth={2} />
          {h.points.east_m.map((e, i) => {
            const x = X(e)
            const y = Y(h.points.north_m[i])
            const sl = h.points.slope_deg[i]
            if (sl !== null && sl > limitDeg)
              return (
                <path
                  key={i}
                  d={`M${x - 2.5} ${y - 2.5}L${x + 2.5} ${y + 2.5}M${x + 2.5} ${y - 2.5}L${x - 2.5} ${y + 2.5}`}
                  stroke="var(--color-alert)"
                  strokeWidth={1.75}
                  paintOrder="stroke"
                />
              )
            return <circle key={i} cx={x} cy={y} r={1.8} fill={sl === null ? 'var(--color-ink-3)' : 'var(--color-ink)'} stroke="var(--color-panel)" strokeWidth={0.9} />
          })}
          {hover && (
            <rect x={hover.c * cw} y={mh - (hover.r + 1) * cw} width={cw} height={cw} fill="none" stroke="var(--color-focus)" strokeWidth={2} pointerEvents="none" />
          )}
          <rect x={0} y={0} width={mw} height={mh} fill="transparent" onPointerMove={onMove} onPointerDown={onMove} onPointerLeave={() => setHover(null)} />
          <rect x={0} y={0} width={mw} height={mh} fill="none" stroke="var(--color-line-strong)" pointerEvents="none" />

          {/* north arrow */}
          <g transform={`translate(${mw - 18} 10)`} pointerEvents="none">
            <circle cx={0} cy={10} r={13} fill="var(--color-panel)" opacity={0.85} />
            <path d="M0 0 L5 12 L0 9 L-5 12 Z" fill="var(--color-ink)" />
            <text x={0} y={21} textAnchor="middle" fontFamily="var(--font-sans)" fontSize={9} fontWeight={700} fill="var(--color-ink)">
              N
            </text>
          </g>
          {/* scale bar */}
          <g transform={`translate(0 ${mh + 12})`} fontFamily="var(--font-sans)" fontSize={12} fill="var(--color-ink-2)">
            <path d={`M0 0 V6 H${bar * s} V0`} fill="none" stroke="var(--color-ink-2)" strokeWidth={1.5} />
            <text x={bar * s + 8} y={10}>
              {num(bar, 0)} m
            </text>
          </g>
        </svg>
      </div>
      <p aria-live="polite" className="min-h-5 font-mono text-caption leading-caption text-ink-2 tabular-nums">
        {hover
          ? hv === null || hv === undefined
            ? 'This cell: no slope (unknown)'
            : `This cell: ${num(hv, 1)}° over ${h.baseline_m} m`
          : <span className="font-sans text-ink-3">Point at the map to read one cell&apos;s slope.</span>}
      </p>
      <figcaption className="flex flex-col gap-2">
        <span className="text-caption leading-caption text-ink-2">Slope over {h.baseline_m} m, degrees</span>
        <ul className="flex flex-wrap gap-x-3 gap-y-1.5 text-caption leading-caption text-ink-2">
          {SLOPE_BINS.map((_, i) => (
            <li key={i} className="flex items-center gap-1.5">
              <span aria-hidden="true" className="inline-block size-3.5 rounded-xs border border-line" style={{ background: fillFor(i) }} />
              {binLabel(i)}
            </li>
          ))}
          <li className="flex items-center gap-1.5">
            <svg aria-hidden="true" className="size-3.5">
              <rect width="14" height="14" fill={`url(#${pid}-unk)`} />
            </svg>
            unknown
          </li>
        </ul>
        <ul className="flex flex-wrap gap-x-4 gap-y-1.5 text-caption leading-caption text-ink-2">
          <li className="flex items-center gap-1.5">
            <svg aria-hidden="true" className="h-3 w-5">
              <ellipse cx="10" cy="6" rx="8" ry="4.5" fill="none" stroke="var(--color-ink)" strokeWidth="2" />
            </svg>
            Landing ellipse (3 sigma)
          </li>
          <li className="flex items-center gap-1.5">
            <svg aria-hidden="true" className="size-3">
              <circle cx="6" cy="6" r="2.2" fill="var(--color-ink)" stroke="var(--color-panel)" strokeWidth="0.9" />
            </svg>
            Landing point at or under the slope limit
          </li>
          <li className="flex items-center gap-1.5">
            <svg aria-hidden="true" className="size-3">
              <path d="M3 3L9 9M9 3L3 9" stroke="var(--color-alert)" strokeWidth="1.5" />
            </svg>
            Over the slope limit ({num(limitDeg, 1)}°)
          </li>
        </ul>
      </figcaption>
    </figure>
  )
}
