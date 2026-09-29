import { useId, useMemo, useState } from 'react'
import { api } from '../../lib/api/client'
import type { ViewshedDTO } from '../../lib/api/lifecycle'
import { formatValue } from '../../lib/lifecycle/quantity'
import { cellEdges, siteFrame, tilesFor, zoomFor, type SightLayer } from '../../lib/lifecycle/tileMap'

export const LAYER_WORDS: Record<SightLayer, string> = {
  sight: 'Line of sight',
  radio: 'Radio path',
}

/** The words that say what a map shows, for its accessible name. */
export function mapLabel(v: ViewshedDTO, layer: SightLayer, roverName: string): string {
  return `${LAYER_WORDS[layer]} between ${roverName} and the lander, out to ${formatValue(v.ranges_m[v.ranges_m.length - 1])} m in ${v.bearings_deg.length} directions, north up. The table lists each direction.`
}

/**
 * What every map of the ground around the lander carries on top of its layers, in metres
 * from the lander with north up: rings every hundred (or more) metres with their labels on
 * a plate, the north mark, and the lander as an ink square that reads on every state.
 * `R` is where the cells end.
 */
export function MapMarks({ R, pad }: { R: number; pad: number }) {
  const ringStep = R > 1500 ? 500 : R > 600 ? 200 : 100
  const rings: number[] = []
  for (let r = ringStep; r <= R; r += ringStep) rings.push(r)
  return (
    <>
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
      <rect x={-R / 40} y={-R / 40} width={R / 20} height={R / 20} fill="var(--color-ink)" stroke="var(--color-canvas)" strokeWidth={R / 200} />
    </>
  )
}

/**
 * The line of sight laid over the terrain, from the service's map tiles: the hillshade of the
 * elevation model the answer read, then the answer's own layer (each cell in sight, blocked
 * or uncertain, by pattern and tone) with rings, the north mark and the lander on top.
 *
 * The tiles are in the polar grid, whose north is not true north (it is the site's longitude
 * off), so the whole picture is turned to put north up and shrunk by the projection's scale.
 * The zoom is the one whose tile pixel is about one screen pixel at `size`. A tile that does
 * not load leaves the ground colour; if the layer's tiles fail, the map says so, since a map
 * without its layer would read as "no blockers".
 */
export function SiteTileMap({
  v,
  layer,
  roverName,
  tile,
  at,
  size = 420,
}: {
  v: ViewshedDTO
  layer: SightLayer
  roverName: string
  /** The answer's tile address, `viewshed_tile`. */
  tile: string
  at: { lat_deg: number; lon_deg: number }
  /** About how wide it is drawn, CSS pixels: sets the zoom. */
  size?: number
}) {
  const clip = useId()
  const edges = cellEdges(v.ranges_m)
  const R = edges[edges.length - 1]
  const pad = R * 0.22
  const half = R + pad
  const frame = useMemo(() => siteFrame(at.lat_deg, at.lon_deg), [at.lat_deg, at.lon_deg])
  const z = zoomFor((2 * half) / size)
  const terrain = useMemo(() => tilesFor(frame, z, half), [frame, z, half])
  const overlay = useMemo(() => tilesFor(frame, z, half, R), [frame, z, half, R])
  const [failed, setFailed] = useState<ReadonlySet<string>>(() => new Set())
  const fail = (href: string) => setFailed((f) => new Set(f).add(href))
  const placed = (l: 'terrain' | SightLayer) =>
    (l === 'terrain' ? terrain : overlay).flatMap((t) => {
      const href = api.viewshedTileUrl(tile, l, t.z, t.x, t.y)
      return href && !failed.has(href) ? [{ t, href }] : []
    })
  const overlayLost = overlay.some((t) => failed.has(api.viewshedTileUrl(tile, layer, t.z, t.x, t.y) ?? ''))
  return (
    <div className="flex flex-col gap-2">
      <svg
        viewBox={`${-half} ${-half} ${2 * half} ${2 * half}`}
        className="mx-auto block aspect-square w-full max-w-[420px]"
        role="img"
        aria-label={`${mapLabel(v, layer, roverName)} Drawn over the terrain map.`}
        data-testid="site-tile-map"
        data-zoom={z}
      >
        <defs>
          <clipPath id={clip}>
            <rect x={-half} y={-half} width={2 * half} height={2 * half} />
          </clipPath>
        </defs>
        <rect x={-half} y={-half} width={2 * half} height={2 * half} fill="var(--color-terrain-low)" />
        <g clipPath={`url(#${clip})`}>
          {/* Grid metres from the lander, y down: scaled to ground metres and turned to put north up. */}
          <g transform={`rotate(${-frame.convergenceDeg}) scale(${1 / frame.k})`}>
            {(['terrain', layer] as const).flatMap((l) =>
              placed(l).map(({ t, href }) => (
                <image
                  key={`${l}/${t.key}`}
                  href={href}
                  x={t.left}
                  y={t.top}
                  // One tile pixel of overlap hides the hairline seam between tiles.
                  width={t.size * (1 + 1 / 256)}
                  height={t.size * (1 + 1 / 256)}
                  preserveAspectRatio="none"
                  onError={() => fail(href)}
                />
              )),
            )}
          </g>
        </g>
        {/* Where the cells end. */}
        <circle r={R} fill="none" stroke="var(--color-ink)" strokeOpacity={0.55} strokeWidth={R / 300} />
        <MapMarks R={R} pad={pad} />
      </svg>
      {overlayLost && (
        <p role="status" className="text-small text-ink-2">
          The map layer did not load, so nothing is drawn over the terrain. The table has the same answer.
        </p>
      )}
    </div>
  )
}
