import { useId, useMemo, useState } from 'react'
import { getCandidates } from '../lib/sites'
import { api } from '../lib/api/client'
import { useSnapshotActive } from '../lib/api/snapshot'
import type { Site } from '../lib/types'
import type { SubPoint } from '../lib/subSolar'
import { Segmented } from './ui'
import polePhoto from '../assets/space/moon-south-pole-wac-2048.jpg'

/**
 * One mission-target pin (§10.2). Missions that share a coordinate (three aim
 * at the centre of Mons Mouton) share one pin, and its name lists them all.
 */
export interface MissionPin {
  key: string
  latDeg: number
  lonDeg: number
  /** Dashed for a planned target or a feature centre; solid for an actual landing. */
  dashed: boolean
  /** The pin button's accessible name. */
  label: string
  /** Filled in ink: selected, or linked to the row being hovered or focused. */
  highlighted: boolean
  /** The pin is the selected one (a pressed toggle), where selection applies. */
  pressed?: boolean
}

/** The inner edge of the map: pins north of 80°S are outside it. */
export const POLAR_MAP_EDGE_LAT = -80

/** Lunar radius, metres: the sphere the LOLA polar products are projected from. */
const R_MOON_M = 1_737_400

/**
 * Half the side of the tile pyramid's square, metres. The tile service builds
 * its quadtree over the regional DEM's own extent (LDEM 80S at 80 m, origin at
 * ±303,960 m), so this is what places a tile; the map's circle is 80°S at
 * 304,006 m, a few pixels outside it.
 */
const TILE_HALF_EXTENT_M = 303_960

const CX = 350
const CY = 350
const R_EDGE = 330
const DEG = Math.PI / 180

type View = 'region' | 'pole'

/**
 * The two extents. The whole map runs from 80°S to the pole; the close-up
 * from 87.5°S, where seven candidate sites sit within a few kilometres of
 * each other and their pins would otherwise land on top of one another.
 */
const VIEWS: Record<View, { edgeColat: number; rings: { colat: number; label: string }[]; name: string }> = {
  region: {
    edgeColat: 10,
    rings: [
      { colat: 2, label: '88°S' },
      { colat: 5, label: '85°S' },
    ],
    name: '80 degrees south to the pole',
  },
  pole: {
    edgeColat: 2.5,
    rings: [
      { colat: 1, label: '89°S' },
      { colat: 2, label: '88°S' },
    ],
    name: 'a close-up from 87.5 degrees south to the pole',
  },
}

/** Distance from the pole in south polar stereographic, metres (scale true at the pole). */
const stereoM = (colatDeg: number) => 2 * R_MOON_M * Math.tan((colatDeg * DEG) / 2)

interface Projection {
  edgeColat: number
  /** SVG units per metre. */
  s: number
  project: (latDeg: number, lonDeg: number) => { x: number; y: number }
  radius: (colatDeg: number) => number
}

/**
 * South polar stereographic, exactly as the LOLA products and the tile
 * service use it: longitude 0 at the top (grid +y), east clockwise, and the
 * map's edge at `edgeColat` degrees from the pole.
 */
function projection(view: View): Projection {
  const edgeColat = VIEWS[view].edgeColat
  const s = R_EDGE / stereoM(edgeColat)
  const radius = (colat: number) => stereoM(colat) * s
  return {
    edgeColat,
    s,
    radius,
    project: (latDeg, lonDeg) => {
      const r = radius(90 + latDeg)
      const th = lonDeg * DEG
      return { x: CX + r * Math.sin(th), y: CY - r * Math.cos(th) }
    },
  }
}

interface TileRef {
  key: string
  href: string
  x: number
  y: number
  size: number
}

/**
 * The hillshade tiles that cover the visible circle, at the zoom that puts
 * about four tiles across it: 1,024 source pixels for a map drawn at up to
 * ~640 CSS pixels. The pyramid is pre-rendered to z5, so this never asks the
 * service to render one on demand.
 */
function tilesFor(p: Projection): TileRef[] {
  const visibleM = stereoM(p.edgeColat)
  const z = Math.max(0, Math.min(5, Math.round(Math.log2((4 * TILE_HALF_EXTENT_M) / visibleM))))
  const n = 2 ** z
  const sizeM = (2 * TILE_HALF_EXTENT_M) / n
  const out: TileRef[] = []
  for (let tx = 0; tx < n; tx++) {
    for (let ty = 0; ty < n; ty++) {
      const xMin = -TILE_HALF_EXTENT_M + tx * sizeM
      const yMax = TILE_HALF_EXTENT_M - ty * sizeM
      // Skip tiles that miss the visible circle entirely.
      const dx = Math.max(xMin, Math.min(0, xMin + sizeM))
      const dy = Math.max(yMax - sizeM, Math.min(0, yMax))
      if (Math.hypot(dx, dy) > visibleM) continue
      out.push({
        key: `${z}/${tx}/${ty}`,
        href: api.tileUrl('hillshade', z, tx, ty),
        x: CX + xMin * p.s,
        y: CY - yMax * p.s,
        size: sizeM * p.s,
      })
    }
  }
  return out
}

/**
 * The unlit region and the terminator on a smooth Moon, for the Sun at `sub`
 * (the sub-solar point, from SPICE through the API). Ridges and craters cast
 * no shadow here; that is what each site's own skyline is for, and the map
 * says so.
 *
 * The Sun's elevation at colatitude c from the south pole is zero where
 * tan(c) = tan(declination) / cos(delta longitude). The curve exists on the
 * side where cos(delta longitude) has the declination's sign. With the Sun
 * south of the equator the pole is lit and the dark side lies beyond the
 * curve; with it north, the pole is dark and only the ground beyond the curve
 * on the sunward side is lit.
 */
function shadowPaths(sub: SubPoint, p: Projection): { dark: string | null; term: string | null } {
  const tanDec = Math.tan(sub.latDeg * DEG)
  const disc = `M${CX - R_EDGE} ${CY} a${R_EDGE} ${R_EDGE} 0 1 0 ${2 * R_EDGE} 0 a${R_EDGE} ${R_EDGE} 0 1 0 ${-2 * R_EDGE} 0 Z`
  if (tanDec === 0) return { dark: null, term: null }
  const pts: { x: number; y: number }[] = []
  const edge: { x: number; y: number }[] = []
  // Sweep the half-turn where the curve exists from end to end, so it stays
  // one unbroken line; a sweep from 0 to 360 degrees joins its two ends
  // straight across the map whenever the half-turn wraps past 0.
  const from = sub.lonDeg + (tanDec > 0 ? -90 : 90)
  for (let i = 1; i < 180; i++) {
    const lon = from + i
    const cosD = Math.cos((lon - sub.lonDeg) * DEG)
    const tanC = tanDec / cosD
    if (!(tanC > 0)) continue
    const colat = Math.atan(tanC) / DEG
    if (colat >= p.edgeColat) continue
    const r = p.radius(colat)
    const th = lon * DEG
    pts.push({ x: CX + r * Math.sin(th), y: CY - r * Math.cos(th) })
    edge.push({ x: CX + R_EDGE * Math.sin(th), y: CY - R_EDGE * Math.cos(th) })
  }
  if (pts.length < 3) {
    // The curve lies outside the view: all of it is dark (Sun north) or lit.
    return { dark: tanDec > 0 ? disc : null, term: null }
  }
  const line = pts.map((q, i) => `${i === 0 ? 'M' : 'L'}${q.x.toFixed(1)} ${q.y.toFixed(1)}`).join(' ')
  const back = edge
    .slice()
    .reverse()
    .map((q) => `L${q.x.toFixed(1)} ${q.y.toFixed(1)}`)
    .join(' ')
  const beyond = `${line} ${back} Z`
  // Sun north: the region beyond the curve is the lit one, so the dark one is
  // the rest of the disc (drawn with the even-odd rule).
  return { dark: tanDec > 0 ? `${disc} ${beyond}` : beyond, term: line }
}

/**
 * Single-link clusters of points closer than `gap` (SVG units). Pins that
 * would collide are drawn as one marker with one name, instead of letters
 * printed over each other.
 */
function clusters<T extends { at: { x: number; y: number } }>(items: T[], gap: number): T[][] {
  const parent = items.map((_, i) => i)
  const find = (i: number): number => (parent[i] === i ? i : (parent[i] = find(parent[i])))
  for (let i = 0; i < items.length; i++) {
    for (let j = i + 1; j < items.length; j++) {
      const a = items[i].at
      const b = items[j].at
      if (Math.hypot(a.x - b.x, a.y - b.y) < gap) parent[find(i)] = find(j)
    }
  }
  const groups = new Map<number, T[]>()
  items.forEach((it, i) => groups.set(find(i), [...(groups.get(find(i)) ?? []), it]))
  return [...groups.values()]
}

const centroid = (pts: { at: { x: number; y: number } }[]) => ({
  x: pts.reduce((a, q) => a + q.at.x, 0) / pts.length,
  y: pts.reduce((a, q) => a + q.at.y, 0) / pts.length,
})

const pct = (v: number) => `${(v / 700) * 100}%`

export function PolarMap({
  sun,
  selectedSiteId,
  onSelect,
  size = 700,
  className = '',
  sites: siteList,
  missionPins = [],
  onMissionPin,
  onMissionHover,
  ellipses = [],
  poleView = false,
  siteMarks = 'pins',
}: {
  /** The sub-solar point for the shadow line; null draws none (still loading, say). */
  sun: SubPoint | null
  selectedSiteId: string
  onSelect?: (id: string) => void
  size?: number
  className?: string
  /** Candidate sites drawn as lettered pins. Defaults to every candidate. */
  sites?: Site[]
  /** The mission layer: diamonds, drawn over the candidates. */
  missionPins?: MissionPin[]
  /** Called with every pin key a marker stands for (one, or a cluster). */
  onMissionPin?: (keys: string[]) => void
  onMissionHover?: (keys: string[] | null) => void
  /** Published landing ellipses as [lat, lon] rings. Drawn only when published. */
  ellipses?: [number, number][][]
  /** Offer the pole close-up, where the candidates near the pole separate. */
  poleView?: boolean
  /**
   * `dots` draws the candidates as unlabelled context marks, for a small map
   * whose subject is something else (the missions inset): lettered pins at
   * that size are too small to read and fall on top of each other.
   */
  siteMarks?: 'pins' | 'dots'
}) {
  const clipId = useId()
  const [view, setView] = useState<View>('region')
  const p = useMemo(() => projection(view), [view])
  // Tiles come from the offline copy while it is in use.
  const saved = useSnapshotActive()
  const tiles = useMemo(() => tilesFor(p), [p, saved])
  const [failed, setFailed] = useState<ReadonlySet<string>>(() => new Set())
  // The photograph under the relief; without it (it did not load) the relief is the picture.
  const [photo, setPhoto] = useState(true)
  const { dark, term } = useMemo(() => (sun ? shadowPaths(sun, p) : { dark: null, term: null }), [sun, p])

  const shown = siteList ?? getCandidates()
  const inView = (lat: number) => 90 + lat <= p.edgeColat
  const sites = shown.filter((s) => inView(s.latDeg)).map((s) => ({ site: s, at: p.project(s.latDeg, s.lonDeg) }))
  const pins = missionPins.filter((m) => inView(m.latDeg)).map((pin) => ({ pin, at: p.project(pin.latDeg, pin.lonDeg) }))
  const rings = ellipses
    .filter((r) => r.length > 2 && r.every(([lat]) => inView(lat)))
    .map(
      (r) =>
        r
          .map(([lat, lon], i) => {
            const q = p.project(lat, lon)
            return `${i === 0 ? 'M' : 'L'}${q.x.toFixed(1)} ${q.y.toFixed(1)}`
          })
          .join(' ') + ' Z',
    )

  // About 36 CSS pixels at the size the map is drawn: closer than that, two
  // lettered pins collide.
  const gap = 36 * (700 / Math.min(size, 700))
  const siteGroups = siteMarks === 'dots' ? [] : clusters(sites, gap)
  const pinGroups = clusters(pins, gap * 0.6)
  const poleColat = VIEWS.pole.edgeColat
  const canZoom = (g: typeof sites) => poleView && view === 'region' && g.every((m) => 90 + m.site.latDeg < poleColat)

  const hiddenSites = shown.length - sites.length
  const summary = `South pole map, ${VIEWS[view].name}, over NASA’s photograph of the pole and the LOLA terrain map. ${sites.length} candidate site${
    sites.length === 1 ? '' : 's'
  }${pins.length ? ` and ${pins.length} mission target${pins.length === 1 ? '' : 's'}` : ''} shown${
    hiddenSites > 0 ? `; ${hiddenSites} more lie outside this close-up` : ''
  }. ${
    sun
      ? 'The shaded region is where the Sun is below a flat horizon at this moment; the shadows of ridges and craters are not included, and the shadows in the photograph are from the days it was taken.'
      : 'The Sun position is still loading, so no shadow is drawn.'
  }`

  return (
    <div className={`flex w-full flex-col gap-2 ${className}`} style={{ maxWidth: `min(${size}px, 70vh)` }}>
      {poleView && (
        <Segmented<View>
          label="Map extent"
          value={view}
          onChange={setView}
          options={[
            { value: 'region', label: '80°S to the pole' },
            { value: 'pole', label: 'Pole close-up' },
          ]}
        />
      )}
      {/* Square by construction, so the buttons below -- positioned in per
          cent of the 700 x 700 view box -- sit exactly on their pins. */}
      <div className="relative aspect-square w-full">
        {/* The ground is a picture of its own under the drawing: the Sun's
            sweep redraws the drawing every frame, and the photograph and the
            tiles are then not painted again with it. */}
        <svg viewBox="0 0 700 700" className="pw-relief absolute inset-0 h-full w-full" aria-hidden="true">
          <defs>
            <clipPath id={`${clipId}-relief`}>
              <circle cx={CX} cy={CY} r={R_EDGE} />
            </clipPath>
          </defs>
          <circle cx={CX} cy={CY} r={R_EDGE} fill="var(--color-terrain-low)" />
          <g clipPath={`url(#${clipId}-relief)`}>
            {/* The real ground: NASA's LRO camera mosaic of the pole, cut to
                the square the tiles cover and in their projection
                (fetch_pole_mosaic.py), so a pin sits on the place it names. */}
            {photo && (
              <image
                href={polePhoto}
                x={CX - TILE_HALF_EXTENT_M * p.s}
                y={CY - TILE_HALF_EXTENT_M * p.s}
                width={2 * TILE_HALF_EXTENT_M * p.s}
                height={2 * TILE_HALF_EXTENT_M * p.s}
                preserveAspectRatio="none"
                onError={() => setPhoto(false)}
              />
            )}
            {/* The LOLA relief, in the same projection. Over the photograph
                it shows only where it is the lighter of the two: a
                photograph of the pole is black wherever the Sun was not, and
                the relief fills those shadows with the shape of the ground.
                Without the photograph it is the picture, a little crisper
                than the tiles' own soft grey. A tile that fails to load
                leaves what is under it, never a broken-image mark. */}
            <g
              style={
                photo
                  ? { mixBlendMode: 'lighten', filter: 'contrast(1.28) brightness(0.74)' }
                  : { filter: 'contrast(1.28) brightness(1.04)' }
              }
            >
              {tiles
                .filter((t) => !failed.has(t.href))
                .map((t) => (
                  <image
                    key={t.key}
                    href={t.href}
                    x={t.x}
                    y={t.y}
                    // Half a unit of overlap hides the hairline seam between tiles.
                    width={t.size + 0.5}
                    height={t.size + 0.5}
                    preserveAspectRatio="none"
                    onError={() => setFailed((f) => new Set(f).add(t.href))}
                  />
                ))}
            </g>
          </g>
        </svg>
        <svg viewBox="0 0 700 700" className="absolute inset-0 h-full w-full" role="img" aria-label={summary}>
          <defs>
            <clipPath id={clipId}>
              <circle cx={CX} cy={CY} r={R_EDGE} />
            </clipPath>
          </defs>

          <g clipPath={`url(#${clipId})`}>
            {/* M1 — sunlight over the whole disc, then the unlit region laid
                on top of it. Translucent, so the relief reads through. */}
            <circle cx={CX} cy={CY} r={R_EDGE} fill="var(--color-sun-fill)" fillOpacity="0.14" />
            {dark && <path d={dark} fill="var(--color-psr)" fillOpacity="0.7" fillRule="evenodd" />}
            {term && (
              <>
                <path d={term} fill="none" stroke="url(#pw-uncertain)" strokeWidth="14" strokeOpacity="0.5" />
                <path d={term} fill="none" stroke="var(--color-sun)" strokeWidth="2.5" />
              </>
            )}

            <g fill="none" stroke="var(--color-line-strong)" strokeWidth="1" strokeDasharray="4 5">
              {VIEWS[view].rings.map((r) => (
                <circle key={r.label} cx={CX} cy={CY} r={p.radius(r.colat)} />
              ))}
              <path d={`M${CX} 20 V680 M20 ${CY} H680`} />
            </g>
          </g>

          <circle cx={CX} cy={CY} r={R_EDGE} fill="none" stroke="var(--color-line-strong)" strokeWidth="2" />

          <g
            fill="var(--color-ink-2)"
            fontFamily="var(--font-mono)"
            fontSize="11"
            paintOrder="stroke"
            stroke="var(--color-canvas)"
            strokeWidth="3"
          >
            {VIEWS[view].rings.map((r) => (
              <text key={r.label} x={CX + 8} y={CY - p.radius(r.colat) + 4}>
                {r.label}
              </text>
            ))}
            <text x={CX} y="14" textAnchor="middle">
              0°
            </text>
            <text x="692" y={CY + 4} textAnchor="end">
              90°E
            </text>
          </g>

          {siteMarks === 'dots' &&
            sites.map(({ site: s, at }) => (
              <circle
                key={s.id}
                cx={at.x}
                cy={at.y}
                r="5"
                fill="var(--color-ink-2)"
                stroke="var(--color-canvas)"
                strokeWidth="1.5"
                aria-hidden="true"
              />
            ))}

          {siteGroups.map((g, gi) => {
            if (g.length === 1) {
              const { site: s, at } = g[0]
              const selected = s.id === selectedSiteId
              return (
                <g key={s.id} transform={`translate(${at.x} ${at.y})`} aria-hidden="true">
                  {selected && <circle r="20" fill="none" stroke="var(--color-sun)" strokeWidth="2" strokeOpacity="0.55" />}
                  {/* The pin drops onto the map as its card arrives (globals.css .pw-pin); its code stays still. */}
                  <g className="pw-pin" style={{ ['--pw-pin-i' as string]: gi }}>
                    <path
                      d="M0 12 s10-9.5 10-16a10 10 0 1 0-20 0c0 6.5 10 16 10 16Z"
                      fill={selected ? 'var(--color-sun-fill)' : 'var(--color-ink)'}
                      stroke="var(--color-canvas)"
                      strokeWidth="1.5"
                    />
                    <circle cy="-4" r="3.4" fill="var(--color-canvas)" />
                  </g>
                  <text
                    y="32"
                    textAnchor="middle"
                    fontFamily="var(--font-sans)"
                    fontSize="13"
                    fontWeight="600"
                    fill={selected ? 'var(--color-sun)' : 'var(--color-ink)'}
                    paintOrder="stroke"
                    stroke="var(--color-canvas)"
                    strokeWidth="3"
                  >
                    {s.code}
                  </text>
                </g>
              )
            }
            // A cluster: each site a small dot at its exact position, and one
            // label naming them, beside the group rather than on top of it.
            const c = centroid(g)
            const right = Math.max(...g.map((m) => m.at.x)) + 12
            const selected = g.some((m) => m.site.id === selectedSiteId)
            const codes = g.map((m) => m.site.code).join(' ')
            return (
              <g key={g.map((m) => m.site.id).join('|')} aria-hidden="true">
                {g.map((m) => (
                  <circle
                    key={m.site.id}
                    cx={m.at.x}
                    cy={m.at.y}
                    r="4.5"
                    fill={m.site.id === selectedSiteId ? 'var(--color-sun-fill)' : 'var(--color-ink)'}
                    stroke="var(--color-canvas)"
                    strokeWidth="1.5"
                  />
                ))}
                {selected && <circle cx={c.x} cy={c.y} r="24" fill="none" stroke="var(--color-sun)" strokeWidth="2" strokeOpacity="0.55" />}
                <text
                  x={right}
                  y={c.y + 4}
                  fontFamily="var(--font-sans)"
                  fontSize="13"
                  fontWeight="600"
                  fill="var(--color-ink)"
                  paintOrder="stroke"
                  stroke="var(--color-canvas)"
                  strokeWidth="3"
                >
                  {g.length > 4 ? `${g.length} sites` : codes}
                </text>
              </g>
            )
          })}

          {rings.map((d, i) => (
            <path key={`ring-${i}`} d={d} fill="none" stroke="var(--color-line-strong)" strokeWidth="1" aria-hidden="true" />
          ))}

          {/* Mission targets: a diamond, stroke ink, fill panel; dashed where
              the coordinate is a plan or a feature centre, solid where a
              lander came to rest. Never amber or cyan: those mean sunlight and
              Earth contact. Targets that sit together keep their exact
              positions and gain one count beside them. */}
          {pinGroups.map((g) => (
            <g key={g.map((m) => m.pin.key).join('|')} aria-hidden="true">
              {g.map(({ pin, at }) => (
                <g key={pin.key} transform={`translate(${at.x} ${at.y})`}>
                  {pin.highlighted && (
                    <circle r="17" fill="none" stroke="var(--color-ink)" strokeWidth="2" strokeOpacity="0.55" />
                  )}
                  <rect
                    x="-8"
                    y="-8"
                    width="16"
                    height="16"
                    transform="rotate(45)"
                    fill={pin.highlighted ? 'var(--color-ink)' : 'var(--color-panel)'}
                    stroke="var(--color-ink)"
                    strokeWidth="2"
                    strokeDasharray={pin.dashed ? '4 3' : undefined}
                  />
                </g>
              ))}
              {g.length > 1 && (
                <text
                  x={Math.max(...g.map((m) => m.at.x)) + 16}
                  y={centroid(g).y - 10}
                  fontFamily="var(--font-sans)"
                  fontSize="13"
                  fontWeight="700"
                  fill="var(--color-ink)"
                  paintOrder="stroke"
                  stroke="var(--color-canvas)"
                  strokeWidth="3"
                >
                  ×{g.length}
                </text>
              )}
            </g>
          ))}

        </svg>

        {/* Real buttons over the pins. An SVG cannot hold a <button>, so the
            marks above are presentational and these sit on top of them: a
            48 x 48 target each, reachable by Tab, named from the data. A
            cluster near the pole is one button that opens the close-up, where
            its sites separate; any other cluster keeps a button per site. */}
        {onSelect &&
          siteGroups.flatMap((g) => {
            if (g.length > 1 && canZoom(g)) {
              const c = centroid(g)
              const names = g.map((m) => `${m.site.code}, ${m.site.name}`).join('; ')
              const selected = g.find((m) => m.site.id === selectedSiteId)
              return [
                <button
                  key={`cluster-${g[0].site.id}`}
                  type="button"
                  onClick={() => setView('pole')}
                  aria-label={`${g.length} candidate sites near the pole: ${names}${
                    selected ? `. Includes the selected site, ${selected.site.code}` : ''
                  }. Show the pole close-up`}
                  className="absolute size-12 -translate-x-1/2 -translate-y-1/2 rounded-pill bg-transparent"
                  style={{ left: pct(c.x), top: pct(c.y) }}
                />,
              ]
            }
            return g.map(({ site: s, at }) => (
              <button
                key={s.id}
                type="button"
                onClick={() => onSelect(s.id)}
                aria-pressed={s.id === selectedSiteId}
                aria-label={`${s.code}, ${s.name}`}
                className="absolute size-12 -translate-x-1/2 -translate-y-1/2 rounded-pill bg-transparent"
                style={{ left: pct(at.x), top: pct(at.y) }}
              />
            ))
          })}
        {onMissionPin &&
          pinGroups.map((g) => {
            const keys = g.map((m) => m.pin.key)
            const c = centroid(g)
            const label =
              g.length === 1
                ? g[0].pin.label
                : `${g.length} targets close together. ${g.map((m) => m.pin.label).join('. ')}`
            return (
              <button
                key={keys.join('|')}
                type="button"
                onClick={() => onMissionPin(keys)}
                onMouseEnter={() => onMissionHover?.(keys)}
                onMouseLeave={() => onMissionHover?.(null)}
                onFocus={() => onMissionHover?.(keys)}
                onBlur={() => onMissionHover?.(null)}
                aria-pressed={g.length === 1 ? g[0].pin.pressed : undefined}
                aria-label={label}
                className="absolute size-12 -translate-x-1/2 -translate-y-1/2 rounded-pill bg-transparent"
                style={{ left: pct(c.x), top: pct(c.y) }}
              />
            )
          })}
      </div>
    </div>
  )
}
