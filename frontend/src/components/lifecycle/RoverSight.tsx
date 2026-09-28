import { useState } from 'react'
import type { QuantityDTO, RoverSightDTO, SightState, ViewshedDTO } from '../../lib/api/lifecycle'
import { formatValue, quantityText, quantityView } from '../../lib/lifecycle/quantity'
import { ScrollRegion, Segmented } from '../ui'
import { ChartPanel, Legend } from './Section'

/** The three states, each with a glyph and words (colour never alone: a fill, a 45° and a −45° hatch). */
export const SIGHT_WORDS: Record<SightState, { words: string; glyph: string; fill: string }> = {
  clear: { words: 'In sight', glyph: '●', fill: 'var(--color-earth-fill)' },
  blocked: { words: 'Blocked', glyph: '✕', fill: 'url(#pw-blocked)' },
  uncertain: { words: 'Uncertain', glyph: '?', fill: 'url(#pw-uncertain)' },
}

export type SightLayer = 'sight' | 'radio'

const LAYER_WORDS: Record<SightLayer, string> = {
  sight: 'Line of sight',
  radio: 'Radio path',
}

/** One ray's states as runs of the same state, from the first sample to the last of each run. */
export function rayRuns(states: SightState[], ranges: number[]): { state: SightState; from: number; to: number; first: number; last: number }[] {
  const out: { state: SightState; from: number; to: number; first: number; last: number }[] = []
  states.forEach((s, j) => {
    const prev = out[out.length - 1]
    if (prev && prev.state === s) {
      prev.to = ranges[j]
      prev.last = j
    } else out.push({ state: s, from: ranges[j], to: ranges[j], first: j, last: j })
  })
  return out
}

/** A ray's runs in words: "In sight 25–150 m; uncertain 175–200 m; blocked 225–500 m". */
export function rayWords(states: SightState[], ranges: number[]): string {
  return rayRuns(states, ranges)
    .map((r, i) => {
      const w = SIGHT_WORDS[r.state].words
      const span = r.from === r.to ? `${formatValue(r.from)} m` : `${formatValue(r.from)}–${formatValue(r.to)} m`
      return `${i ? w.toLowerCase() : w} ${span}`
    })
    .join('; ')
}

const COMPASS: Record<number, string> = { 0: 'north', 90: 'east', 180: 'south', 270: 'west' }
export const bearingWords = (b: number) => `${formatValue(b)}°${COMPASS[b] ? ` (${COMPASS[b]})` : ''}`

/**
 * The answer in words: what share is out of the lander's sight (over the
 * drive, or the ground around it when no drive is published), and the
 * longest stretch; or why it cannot be said.
 */
export function roverSentence(d: RoverSightDTO, roverName: string): string {
  if (!d.resolvable) return d.reason ?? 'The ground between the rover and the lander is not known well enough to say.'
  const share = d.out_of_sight_share
  const shareMissing = quantityView(share).kind === 'missing'
  const out: string[] = []
  // The radio path needs a wider corridor, so it is blocked over more of the ground than the line of sight.
  const radio = d.radio_not_clear_share && quantityView(d.radio_not_clear_share).kind !== 'missing' ? d.radio_not_clear_share : null
  const radioPart = radio ? `; the radio path is not clear over ${quantityText(radio)}` : ''
  if (shareMissing) out.push(share.missing_reason ?? 'The share out of sight is not worked out.')
  else if (d.share_basis === 'ground' && d.radius_m)
    out.push(`Within ${formatValue(d.radius_m)} m of the lander, ${quantityText(share)} of the ground is out of its sight${radioPart}.`)
  else out.push(`${roverName} would be out of the lander’s sight for ${quantityText(share)} of its drive${radioPart}.`)
  const longest: QuantityDTO = d.longest_out_of_sight_m
  if (quantityView(longest).kind !== 'missing') out.push(`The longest stretch out of sight is ${quantityText(longest)}.`)
  else if (longest.missing_reason && longest.missing_reason !== share.missing_reason) out.push(longest.missing_reason)
  return out.join(' ')
}

/** Cell edges half-way between samples; the first cell starts at the lander. */
function edges(xs: number[]): number[] {
  const e = [0]
  for (let j = 1; j < xs.length; j++) e.push((xs[j - 1] + xs[j]) / 2)
  const last = xs[xs.length - 1]
  e.push(last + (xs.length > 1 ? (last - xs[xs.length - 2]) / 2 : last))
  return e
}

const pt = (r: number, deg: number) => {
  const a = (deg * Math.PI) / 180
  return `${(r * Math.sin(a)).toFixed(2)} ${(-r * Math.cos(a)).toFixed(2)}`
}

/** An annular sector between two radii and two bearings (clockwise from north). */
function sector(r0: number, r1: number, a0: number, a1: number): string {
  const large = a1 - a0 > 180 ? 1 : 0
  const outer = `M ${pt(r1, a0)} A ${r1} ${r1} 0 ${large} 1 ${pt(r1, a1)}`
  if (r0 <= 0) return `${outer} L 0 0 Z`
  return `${outer} L ${pt(r0, a1)} A ${r0} ${r0} 0 ${large} 0 ${pt(r0, a0)} Z`
}

/**
 * The viewshed as a map layer around the lander, north up: each ray's runs
 * drawn as sectors, in sight filled, blocked hatched at 45°, uncertain at
 * −45°, with rings every hundred metres. Nothing moves, so this is also its
 * own reduced-motion version.
 */
export function ViewshedMap({ v, layer, roverName }: { v: ViewshedDTO; layer: SightLayer; roverName: string }) {
  const grid = v[layer]
  const re = edges(v.ranges_m)
  const R = re[re.length - 1]
  const n = v.bearings_deg.length
  const step = n > 1 ? (v.bearings_deg[1] - v.bearings_deg[0] + 360) % 360 || 360 / n : 360
  const pad = R * 0.22
  const ringStep = R > 1500 ? 500 : R > 600 ? 200 : 100
  const rings: number[] = []
  for (let r = ringStep; r <= R; r += ringStep) rings.push(r)
  const counts = { clear: 0, blocked: 0, uncertain: 0 }
  grid.forEach((ray) => ray.forEach((s) => (counts[s] += 1)))
  const label = `${LAYER_WORDS[layer]} between ${roverName} and the lander, out to ${formatValue(v.ranges_m[v.ranges_m.length - 1])} m in ${n} directions, north up. The table lists each direction.`
  return (
    <svg
      viewBox={`${-R - pad} ${-R - pad} ${2 * (R + pad)} ${2 * (R + pad)}`}
      className="mx-auto block aspect-square w-full max-w-[420px]"
      role="img"
      aria-label={label}
    >
      <circle r={R} fill="var(--color-dark-fill)" />
      {grid.map((ray, i) => {
        const b = v.bearings_deg[i]
        return rayRuns(ray, v.ranges_m).map((run) => {
          const d = sector(re[run.first], re[run.last + 1], b - step / 2, b + step / 2)
          return (
            <g key={`${b}-${run.first}`}>
              {/* Uncertain gets a light wash under its hatch, so it stands apart from blocked. */}
              {run.state === 'uncertain' && <path d={d} fill="var(--color-uncertain)" fillOpacity={0.3} />}
              <path
                d={d}
                fill={SIGHT_WORDS[run.state].fill}
                // The same paint as a thin stroke closes the hairline seams between rays.
                stroke={SIGHT_WORDS[run.state].fill}
                strokeWidth={R / 300}
              />
            </g>
          )
        })
      })}
      {rings.map((r) => (
        <g key={r}>
          <circle r={r} fill="none" stroke="var(--color-panel)" strokeOpacity={0.8} strokeWidth={R / 250} strokeDasharray={`${R / 60} ${R / 60}`} />
          {/* The label on a panel-coloured plate, so it reads on every state. */}
          <rect x={R / 90} y={-r - R / 60 - R / 16} width={(`${formatValue(r)} m`.length * 0.62 + 0.5) * (R / 16)} height={R / 13} fill="var(--color-panel)" />
          <text x={R / 60 + R / 90} y={-r - R / 60 - R / 160} fontSize={R / 16} fill="var(--color-ink)" className="font-mono">
            {formatValue(r)} m
          </text>
        </g>
      ))}
      <text x={0} y={-R - pad * 0.55} textAnchor="middle" fontSize={R / 12} fontWeight={600} fill="var(--color-ink)">
        N
      </text>
      {/* The lander: an ink square with a ring, so it reads on every state. */}
      <rect x={-R / 40} y={-R / 40} width={R / 20} height={R / 20} fill="var(--color-ink)" stroke="var(--color-canvas)" strokeWidth={R / 200} />
    </svg>
  )
}

/** The map's table twin, from the same rays: each direction's runs, for the line of sight and the radio path. */
export function ViewshedTable({ v }: { v: ViewshedDTO }) {
  const cell = 'px-3 py-2 text-small text-ink-2'
  const head = 'px-3 py-2.5 text-tag font-semibold tracking-caps-md text-ink-3 uppercase'
  return (
    <ScrollRegion label="Line of sight table, scrolls sideways" className="border border-line">
      <table className="w-full min-w-[640px] border-collapse text-left">
        <caption className="sr-only">For each direction from the lander, where a rover would be in its sight, blocked, or uncertain, by distance.</caption>
        <thead>
          <tr className="bg-inset">
            {['Direction', 'Line of sight', 'Radio path (first Fresnel zone)'].map((h) => (
              <th key={h} scope="col" className={head}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {v.bearings_deg.map((b, i) => (
            <tr key={b} className="border-t border-line">
              <th scope="row" className={`${cell} font-semibold whitespace-nowrap text-ink`}>
                {bearingWords(b)}
              </th>
              <td className={cell}>{rayWords(v.sight[i], v.ranges_m)}</td>
              <td className={cell}>{rayWords(v.radio[i], v.ranges_m)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </ScrollRegion>
  )
}

/** The map with its switch (line of sight, radio path), its legend and its table twin. */
export function ViewshedPanel({ v, roverName }: { v: ViewshedDTO; roverName: string }) {
  const [layer, setLayer] = useState<SightLayer>('sight')
  return (
    <ChartPanel
      title={`${LAYER_WORDS[layer]}, ${roverName} and the lander`}
      chart={
        <div className="flex flex-col gap-3">
          <Segmented
            pill
            label="Show"
            value={layer}
            onChange={setLayer}
            options={[
              { value: 'sight', label: LAYER_WORDS.sight },
              { value: 'radio', label: LAYER_WORDS.radio },
            ]}
          />
          <p className="text-small text-ink-2">
            {layer === 'sight'
              ? 'Where a rover could see the lander’s antenna, and the lander see it.'
              : 'Where the radio path is clear too: it needs a wider corridor over the ground (the first Fresnel zone), so less of the ground is clear.'}
          </p>
          <ViewshedMap v={v} layer={layer} roverName={roverName} />
        </div>
      }
      legend={
        <Legend
          items={[
            {
              swatch: (
                <svg width="12" height="12" aria-hidden="true">
                  <rect x="1" y="1" width="10" height="10" fill="var(--color-ink)" stroke="var(--color-canvas)" />
                </svg>
              ),
              label: 'The lander',
            },
            ...(['clear', 'uncertain', 'blocked'] as const).map((s) => ({
            swatch: (
              <span className="flex items-center gap-1.5">
                <svg width="20" height="12" aria-hidden="true">
                  {s === 'uncertain' && <rect width="20" height="12" fill="var(--color-uncertain)" fillOpacity={0.3} />}
                  <rect width="20" height="12" fill={SIGHT_WORDS[s].fill} />
                </svg>
                <span className="text-ink">{SIGHT_WORDS[s].glyph}</span>
              </span>
            ),
            label:
              s === 'clear'
                ? `${SIGHT_WORDS[s].words}`
                : s === 'blocked'
                  ? `${SIGHT_WORDS[s].words} by the ground`
                  : `${SIGHT_WORDS[s].words}: the terrain map’s error could tip it either way`,
            })),
          ]}
        />
      }
      table={<ViewshedTable v={v} />}
    />
  )
}
