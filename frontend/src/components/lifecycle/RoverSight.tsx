import { useState } from 'react'
import { useSnapshotActive } from '../../lib/api/snapshot'
import type { QuantityDTO, RoverSightDTO, SightState, ViewshedDTO } from '../../lib/api/lifecycle'
import { formatValue, quantityText, quantityView } from '../../lib/lifecycle/quantity'
import { cellEdges, tileSwatch, type SightLayer } from '../../lib/lifecycle/tileMap'
import { ScrollRegion, Segmented } from '../ui'
import { ChartPanel, Legend } from './Section'
import { LAYER_WORDS, MapMarks, SiteTileMap, mapLabel } from './SiteTileMap'

/** The three states, each with a glyph and words (colour never alone: a fill, a 45° and a −45° hatch). */
export const SIGHT_WORDS: Record<SightState, { words: string; glyph: string; fill: string }> = {
  clear: { words: 'In sight', glyph: '●', fill: 'var(--color-earth-fill)' },
  blocked: { words: 'Blocked', glyph: '✕', fill: 'url(#pw-blocked)' },
  uncertain: { words: 'Uncertain', glyph: '?', fill: 'url(#pw-uncertain)' },
}

export type { SightLayer }

/** What the radio path needs beyond the line of sight, in the words the served note uses. */
export const RADIO_ROOM = 'the space around the line of sight that the radio signal needs'

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
  const re = cellEdges(v.ranges_m)
  const R = re[re.length - 1]
  const n = v.bearings_deg.length
  const step = n > 1 ? (v.bearings_deg[1] - v.bearings_deg[0] + 360) % 360 || 360 / n : 360
  const pad = R * 0.22
  return (
    <svg
      viewBox={`${-R - pad} ${-R - pad} ${2 * (R + pad)} ${2 * (R + pad)}`}
      className="mx-auto block aspect-square w-full max-w-[420px]"
      role="img"
      aria-label={mapLabel(v, layer, roverName)}
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
      <MapMarks R={R} pad={pad} />
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
            <th scope="col" className={head}>
              Direction
            </th>
            <th scope="col" className={head}>
              Line of sight
            </th>
            <th scope="col" className={head}>
              Radio path{' '}
              <span className="mt-0.5 block text-small font-normal tracking-normal text-ink-3 normal-case">({RADIO_ROOM})</span>
            </th>
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

/**
 * The map with its switch (line of sight, radio path), its legend and its table twin. Laid over
 * the terrain, from the service's tiles, when the answer gives its tile address and where the
 * lander is; drawn as sectors around the lander when it does not, and always in the offline
 * copy, which has no tiles.
 */
export function ViewshedPanel({
  v,
  roverName,
  tile,
  at,
}: {
  v: ViewshedDTO
  roverName: string
  tile?: string | null
  at?: { lat_deg: number; lon_deg: number } | null
}) {
  const [layer, setLayer] = useState<SightLayer>('sight')
  const offline = useSnapshotActive()
  const onTerrain = Boolean(tile && at && !offline)
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
              : `Where the radio path is clear too: the ground must also stay out of ${RADIO_ROOM}, so less of the ground is clear.`}
          </p>
          {onTerrain ? (
            <SiteTileMap v={v} layer={layer} roverName={roverName} tile={tile as string} at={at as { lat_deg: number; lon_deg: number }} />
          ) : (
            <ViewshedMap v={v} layer={layer} roverName={roverName} />
          )}
        </div>
      }
      legend={<ViewshedLegend onTerrain={onTerrain} />}
      table={<ViewshedTable v={v} />}
    />
  )
}

/** The key under a map of the line of sight: the lander, each state with its glyph, and (over the terrain) the ground. */
export function ViewshedLegend({ onTerrain }: { onTerrain: boolean }) {
  return (
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
              {onTerrain ? (
                // The tiles are translucent, so the swatch sits on ground colour as they do on the relief.
                <span className="flex h-3 w-5 border border-line" style={{ background: 'var(--color-terrain-mid)' }}>
                  <span className="h-full w-full" style={{ background: tileSwatch(s) }} />
                </span>
              ) : (
                <svg width="20" height="12" aria-hidden="true">
                  {s === 'uncertain' && <rect width="20" height="12" fill="var(--color-uncertain)" fillOpacity={0.3} />}
                  <rect width="20" height="12" fill={SIGHT_WORDS[s].fill} />
                </svg>
              )}
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
        ...(onTerrain
          ? [
              {
                swatch: <span className="h-3 w-5 border border-line" style={{ background: 'var(--color-terrain-mid)' }} />,
                label: 'The ground, shaded from the terrain map',
              },
            ]
          : []),
      ]}
    />
  )
}
