import { num } from './helpers'
import { scaleBarMetres } from './DispersionMap'
import type { MeshLinkDTO } from '../../lib/api/surface.types'

export interface MeshMapNode {
  id: string
  name: string
  east_m: number
  north_m: number
  /** Has a direct Earth link of its own. */
  earthLink: boolean
}

const W = 360
const PAD = 44
const BOTTOM = 30

/**
 * The nodes in plan view, north up, with the links between them: solid where
 * the terrain model says the line of sight is clear, dashed where it is
 * uncertain, and not drawn where it is blocked. A node with its own Earth link
 * is drawn filled in the Earth colour; the rest are open rings, so the two
 * differ in shape as well as colour. Drawn in a viewBox, so it scales to the
 * width it is given.
 */
/**
 * One entry per pair of nodes. The service reports a link once per stretch of
 * time; where a pair's line of sight changed, the state held longest is kept
 * and the pair is marked as changed.
 */
export function pairStates(links: MeshLinkDTO[]): (MeshLinkDTO & { changed: boolean })[] {
  const byPair = new Map<string, MeshLinkDTO[]>()
  for (const l of links) {
    const k = `${l.a}|${l.b}`
    byPair.set(k, [...(byPair.get(k) ?? []), l])
  }
  return [...byPair.values()].map((segs) => {
    const held = new Map<string, number>()
    for (const l of segs) held.set(l.terrain_sight, (held.get(l.terrain_sight) ?? 0) + (l.end_s - l.start_s))
    const sight = [...held.entries()].sort((x, y) => y[1] - x[1])[0][0]
    const pick = segs.find((l) => l.terrain_sight === sight)!
    return { ...pick, changed: held.size > 1 }
  })
}

export function MeshMap({ nodes, links }: { nodes: MeshMapNode[]; links: MeshLinkDTO[] }) {
  const easts = nodes.map((n) => n.east_m)
  const norths = nodes.map((n) => n.north_m)
  const e0 = Math.min(...easts, 0)
  const e1 = Math.max(...easts, 0)
  const n0 = Math.min(...norths, 0)
  const n1 = Math.max(...norths, 0)
  const spanM = Math.max(e1 - e0, n1 - n0, 50)
  const s = (W - 2 * PAD) / spanM
  const cx = (e0 + e1) / 2
  const cy = (n0 + n1) / 2
  const H = Math.max(W * 0.72, (n1 - n0) * s + 2 * PAD) + BOTTOM
  const plotH = H - BOTTOM
  const X = (e: number) => W / 2 + (e - cx) * s
  const Y = (n: number) => plotH / 2 - (n - cy) * s
  const at = new Map(nodes.map((n) => [n.id, n]))
  const bar = scaleBarMetres(spanM * 1.2)
  const pairs = pairStates(links)
  const changed = pairs.some((p) => p.changed)
  const drawn = pairs.filter((l) => l.terrain_sight !== 'blocked' && at.has(l.a) && at.has(l.b))
  const nClear = drawn.filter((l) => l.terrain_sight === 'clear').length
  const nUncertain = drawn.length - nClear
  const nBlocked = pairs.length - drawn.length
  const label =
    `Plan view, north up, of ${nodes.length} node${nodes.length === 1 ? '' : 's'}: ` +
    nodes.map((n) => `${n.name} ${num(n.east_m, 0)} m east and ${num(n.north_m, 0)} m north${n.earthLink ? ' with its own Earth link' : ''}`).join('; ') +
    `. ${nClear} link${nClear === 1 ? '' : 's'} drawn solid (clear), ${nUncertain} dashed (uncertain), ${nBlocked} not drawn (blocked).`

  return (
    <figure className="m-0 flex min-w-0 flex-col gap-2">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} className="block h-auto w-full max-w-[520px]">
        <rect x="0.5" y="0.5" width={W - 1} height={plotH - 1} rx="6" fill="var(--color-panel)" stroke="var(--color-line-strong)" />
        {drawn.map((l) => {
          const a = at.get(l.a)!
          const b = at.get(l.b)!
          return (
            <line
              key={`${l.a}-${l.b}`}
              data-link={`${l.a}-${l.b}`}
              data-sight={l.terrain_sight}
              x1={X(a.east_m)}
              y1={Y(a.north_m)}
              x2={X(b.east_m)}
              y2={Y(b.north_m)}
              stroke="var(--color-ink)"
              strokeWidth={l.terrain_sight === 'clear' ? 2 : 1.5}
              strokeDasharray={l.terrain_sight === 'uncertain' ? '6 4' : undefined}
              strokeLinecap="round"
            />
          )
        })}
        {nodes.map((n) => {
          const x = X(n.east_m)
          const y = Y(n.north_m)
          const right = x < W / 2
          return (
            <g key={n.id} data-node={n.id} data-earth={n.earthLink ? 'true' : 'false'}>
              <circle
                cx={x}
                cy={y}
                r={7}
                fill={n.earthLink ? 'var(--color-earth-fill)' : 'var(--color-panel)'}
                stroke={n.earthLink ? 'var(--color-earth)' : 'var(--color-ink)'}
                strokeWidth={2}
              />
              <text
                x={right ? x + 12 : x - 12}
                y={y + 4}
                textAnchor={right ? 'start' : 'end'}
                fontSize="12"
                fill="var(--color-ink)"
                stroke="var(--color-panel)"
                strokeWidth="3"
                paintOrder="stroke"
              >
                {n.name}
              </text>
            </g>
          )
        })}
        {/* North arrow */}
        <g aria-hidden="true" transform={`translate(${W - 22} 14)`}>
          <path d="M0 0 L5 13 L0 10 L-5 13 Z" fill="var(--color-ink-2)" />
          <text x="0" y="26" textAnchor="middle" fontSize="11" fill="var(--color-ink-2)">
            N
          </text>
        </g>
        {/* Scale bar */}
        <g aria-hidden="true" transform={`translate(14 ${plotH - 16})`}>
          <path d={`M0 -4 V0 H${bar * s} V-4`} fill="none" stroke="var(--color-ink-2)" strokeWidth="1.5" />
          <text x={bar * s + 6} y="1" fontSize="11" fill="var(--color-ink-2)" className="font-mono">
            {num(bar, 0)} m
          </text>
        </g>
        {/* Legend */}
        <g aria-hidden="true" fontSize="11" fill="var(--color-ink-2)" transform={`translate(10 ${plotH + 14})`}>
          <line x1="0" y1="0" x2="22" y2="0" stroke="var(--color-ink)" strokeWidth="2" />
          <text x="27" y="4">clear</text>
          <line x1="72" y1="0" x2="94" y2="0" stroke="var(--color-ink)" strokeWidth="1.5" strokeDasharray="6 4" />
          <text x="99" y="4">uncertain</text>
          <circle cx="170" cy="0" r="5" fill="var(--color-earth-fill)" stroke="var(--color-earth)" strokeWidth="1.5" />
          <text x="180" y="4">Earth link</text>
        </g>
      </svg>
      <figcaption className="text-caption leading-caption text-ink-3">
        Solid: line of sight clear. Dashed: uncertain at the terrain model&apos;s height error. Blocked links are not drawn.
        {changed && ' A link whose state changed during the dates is drawn in the state it held longest; the table lists each stretch.'}
      </figcaption>
    </figure>
  )
}
