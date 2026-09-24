import { useMemo } from 'react'
import { subSolarPoint, type SubPoint } from '../lib/geometry/ephemeris'
import { getCandidates } from '../lib/sites'
import { bearing } from '../lib/format'
import type { Site } from '../lib/types'

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

const CX = 350
const CY = 350
const R_EDGE = 330
/** Map edge, degrees of colatitude from the south pole. */
const EDGE_COLAT = 10

const DEG = Math.PI / 180

/** South polar stereographic. Longitude 0 at the top, east clockwise. */
function project(latDeg: number, lonDeg: number): { x: number; y: number } {
  const colat = 90 + latDeg
  const k = R_EDGE / Math.tan((EDGE_COLAT * DEG) / 2)
  const r = k * Math.tan((colat * DEG) / 2)
  const th = lonDeg * DEG
  return { x: CX + r * Math.sin(th), y: CY - r * Math.cos(th) }
}

function radiusForColat(colat: number): number {
  const k = R_EDGE / Math.tan((EDGE_COLAT * DEG) / 2)
  return k * Math.tan((colat * DEG) / 2)
}

/**
 * The terminator, solved rather than drawn.
 *
 * Elevation is zero where tan(colatitude) = tan(declination) / cos(delta
 * longitude). Below about a degree and a half of sub-solar latitude that
 * puts the whole lit region inside a lens around the pole, and the dark side
 * is everything outside the curve on the anti-solar side. Sweeping the
 * sub-solar longitude once a month rotates the whole pattern — which is M1.
 */
function darkRegionPath(sub: SubPoint): string | null {
  const tanDec = Math.tan(sub.latDeg * DEG)
  const pts: { x: number; y: number }[] = []
  const edge: { x: number; y: number }[] = []

  for (let i = 0; i <= 180; i++) {
    const lon = (i / 180) * 360
    const dLon = (lon - sub.lonDeg) * DEG
    const cosD = Math.cos(dLon)
    if (cosD === 0) continue
    const tanC = tanDec / cosD
    if (tanC <= 0) continue
    const colat = Math.atan(tanC) / DEG
    if (colat >= EDGE_COLAT) continue
    const r = radiusForColat(colat)
    const th = lon * DEG
    pts.push({ x: CX + r * Math.sin(th), y: CY - r * Math.cos(th) })
    edge.push({ x: CX + R_EDGE * Math.sin(th), y: CY - R_EDGE * Math.cos(th) })
  }

  if (pts.length < 3) return null
  const fwd = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ')
  const back = edge
    .slice()
    .reverse()
    .map((p) => `L${p.x.toFixed(1)} ${p.y.toFixed(1)}`)
    .join(' ')
  return `${fwd} ${back} Z`
}

function terminatorPath(sub: SubPoint): string | null {
  const tanDec = Math.tan(sub.latDeg * DEG)
  const pts: string[] = []
  for (let i = 0; i <= 180; i++) {
    const lon = (i / 180) * 360
    const cosD = Math.cos((lon - sub.lonDeg) * DEG)
    if (cosD === 0) continue
    const tanC = tanDec / cosD
    if (tanC <= 0) continue
    const colat = Math.atan(tanC) / DEG
    if (colat >= EDGE_COLAT) continue
    const r = radiusForColat(colat)
    const th = lon * DEG
    pts.push(`${pts.length === 0 ? 'M' : 'L'}${(CX + r * Math.sin(th)).toFixed(1)} ${(CY - r * Math.cos(th)).toFixed(1)}`)
  }
  return pts.length > 2 ? pts.join(' ') : null
}

/**
 * Schematic terrain. This is a stand-in for LOLA hillshade tiles at map scale
 * — the per-site DEM covers 20 km, this view covers about 300 km. Labelled as
 * schematic on the map so nobody reads a crater edge as a measurement.
 */
const CRATERS: { lat: number; lon: number; rDeg: number; psr: boolean; name: string }[] = [
  { lat: -89.9, lon: 0, rDeg: 0.7, psr: true, name: 'Shackleton' },
  { lat: -88.5, lon: 300, rDeg: 0.9, psr: true, name: 'de Gerlache' },
  { lat: -87.4, lon: 0, rDeg: 1.3, psr: true, name: 'Haworth' },
  { lat: -88.1, lon: 45, rDeg: 1.6, psr: true, name: 'Shoemaker' },
  { lat: -87.3, lon: 84, rDeg: 1.1, psr: true, name: 'Faustini' },
  { lat: -85.6, lon: 65, rDeg: 1.8, psr: false, name: 'Nobile' },
  { lat: -86.0, lon: 200, rDeg: 1.4, psr: false, name: 'unnamed' },
]

export function PolarMap({
  tH,
  selectedSiteId,
  onSelect,
  size = 700,
  className = '',
  sites: siteList,
  missionPins = [],
  onMissionPin,
  onMissionHover,
  ellipses = [],
}: {
  tH: number
  selectedSiteId: string
  onSelect?: (id: string) => void
  size?: number
  className?: string
  /** Candidate sites drawn as lettered pins. Defaults to every candidate. */
  sites?: Site[]
  /** The mission layer: diamonds, drawn over the candidates. */
  missionPins?: MissionPin[]
  onMissionPin?: (key: string) => void
  onMissionHover?: (key: string | null) => void
  /** Published landing ellipses as [lat, lon] rings. Drawn only when published. */
  ellipses?: [number, number][][]
}) {
  // One schematic sub-solar point per instant, shared by both paths. They
  // used to be solved three times per render, including renders where the
  // instant had not moved.
  const { sub, dark, term } = useMemo(() => {
    const sp = subSolarPoint(tH)
    return { sub: sp, dark: darkRegionPath(sp), term: terminatorPath(sp) }
  }, [tH])
  const shown = siteList ?? getCandidates()
  const sites = shown.map((s) => ({ site: s, at: project(s.latDeg, s.lonDeg) }))
  const pins = missionPins
    .filter((p) => p.latDeg <= POLAR_MAP_EDGE_LAT)
    .map((p) => ({ pin: p, at: project(p.latDeg, p.lonDeg) }))
  const rings = ellipses
    .filter((r) => r.length > 2 && r.every(([lat]) => lat <= POLAR_MAP_EDGE_LAT))
    .map((r) =>
      r
        .map(([lat, lon], i) => {
          const q = project(lat, lon)
          return `${i === 0 ? 'M' : 'L'}${q.x.toFixed(1)} ${q.y.toFixed(1)}`
        })
        .join(' ') + ' Z',
    )

  return (
    // Square by construction, so the site buttons below -- positioned in
    // per cent of the 700 x 700 view box -- sit exactly on their pins.
    <div
      className={`relative aspect-square w-full ${className}`}
      style={{ maxWidth: `min(${size}px, 70vh)` }}
    >
      <svg
        viewBox="0 0 700 700"
        className="absolute inset-0 h-full w-full"
        role="img"
        aria-label={`South polar map from 80 degrees south to the pole. ${sites.length} candidate sites${
          pins.length ? ` and ${pins.length} mission target${pins.length === 1 ? '' : 's'}` : ''
        }. The sub-solar point is at longitude ${Math.round(
          ((sub.lonDeg % 360) + 360) % 360,
        )} degrees east, so the unlit region lies opposite it.`}
      >
        <defs>
          <clipPath id="pw-map-clip">
            <circle cx={CX} cy={CY} r={R_EDGE} />
          </clipPath>
        </defs>

        <circle cx={CX} cy={CY} r={R_EDGE} fill="var(--color-raised)" />

        <g clipPath="url(#pw-map-clip)">
          <rect x="0" y="0" width="700" height="700" fill="var(--color-terrain-low)" />

          {/* broad relief */}
          <path d="M0 250 Q160 190 300 250 T700 220 L700 0 L0 0 Z" fill="var(--color-terrain-mid)" opacity="0.35" />
          <path d="M0 470 Q180 420 340 480 T700 450 L700 700 L0 700 Z" fill="var(--color-psr)" opacity="0.4" />

          {CRATERS.map((c) => {
            const p = project(c.lat, c.lon)
            const rr = radiusForColat(c.rDeg)
            return (
              <g key={c.name + c.lon}>
                <ellipse
                  cx={p.x}
                  cy={p.y}
                  rx={rr}
                  ry={rr * 0.94}
                  fill={c.psr ? 'url(#pw-psr)' : 'var(--color-psr)'}
                  stroke="var(--color-terrain-mid)"
                  strokeWidth="2"
                />
                <path
                  d={`M${p.x - rr} ${p.y} a${rr} ${rr * 0.94} 0 0 1 ${rr * 2} 0`}
                  fill="none"
                  stroke="var(--color-terrain-high)"
                  strokeWidth="2.5"
                  opacity="0.8"
                />
              </g>
            )
          })}

          {/* M1 — sunlight over the whole disc, then the unlit region laid on
              top of it. The sweep is the single most important animation here. */}
          <circle cx={CX} cy={CY} r={R_EDGE} fill="var(--color-sun-fill)" fillOpacity="0.14" />
          {dark && <path d={dark} fill="var(--color-psr)" fillOpacity="0.9" />}
          {term && (
            <>
              <path d={term} fill="none" stroke="url(#pw-uncertain)" strokeWidth="14" strokeOpacity="0.5" />
              <path d={term} fill="none" stroke="var(--color-sun)" strokeWidth="2.5" />
            </>
          )}

          <g fill="none" stroke="var(--color-line-strong)" strokeWidth="1" strokeDasharray="4 5">
            <circle cx={CX} cy={CY} r={radiusForColat(2)} />
            <circle cx={CX} cy={CY} r={radiusForColat(5)} />
            <path d={`M${CX} 20 V680 M20 ${CY} H680`} />
          </g>
        </g>

        <circle cx={CX} cy={CY} r={R_EDGE} fill="none" stroke="var(--color-line-strong)" strokeWidth="2" />

        <g fill="var(--color-ink-3)" fontFamily="var(--font-mono)" fontSize="11">
          <text x={CX + 8} y={CY - radiusForColat(2) + 4}>88°S</text>
          <text x={CX + 8} y={CY - radiusForColat(5) + 4}>85°S</text>
          <text x={CX} y="14" textAnchor="middle">0°</text>
          <text x="692" y={CY + 4} textAnchor="end">90°E</text>
        </g>

        {sites.map(({ site: s, at: p }) => {
          const selected = s.id === selectedSiteId
          return (
            <g key={s.id} transform={`translate(${p.x} ${p.y})`} aria-hidden="true">
              {selected && (
                <circle r="20" fill="none" stroke="var(--color-sun)" strokeWidth="2" strokeOpacity="0.55" />
              )}
              <path
                d="M0 12 s10-9.5 10-16a10 10 0 1 0-20 0c0 6.5 10 16 10 16Z"
                fill={selected ? 'var(--color-sun-fill)' : 'var(--color-ink)'}
                stroke="var(--color-canvas)"
                strokeWidth="1.5"
              />
              <circle cy="-4" r="3.4" fill="var(--color-canvas)" />
              <text
                y="32"
                textAnchor="middle"
                fontFamily="var(--font-sans)"
                fontSize="13"
                fontWeight="600"
                fill={selected ? 'var(--color-sun)' : 'var(--color-ink)'}
              >
                {s.code}
              </text>
            </g>
          )
        })}

        {rings.map((d, i) => (
          <path key={`ring-${i}`} d={d} fill="none" stroke="var(--color-line-strong)" strokeWidth="1" aria-hidden="true" />
        ))}

        {/* Mission targets: a 10 px diamond (at the map's usual on-screen
            scale), stroke ink, fill panel; dashed where the coordinate is a
            plan or a feature centre, solid where a lander came to rest. Never
            amber or cyan: those mean sunlight and Earth contact. */}
        {pins.map(({ pin, at }) => (
          <g key={pin.key} transform={`translate(${at.x} ${at.y})`} aria-hidden="true">
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

        <g>
          <rect x="452" y="42" width="216" height="26" fill="var(--color-canvas)" fillOpacity="0.85" />
          <text
            x="560"
            y="60"
            textAnchor="middle"
            fontFamily="var(--font-sans)"
            fontSize="12"
            fontWeight="600"
            letterSpacing="1.2"
            fill="var(--color-ink-2)"
          >
            SCHEMATIC TERRAIN
          </text>
        </g>
        <text x="32" y="676" fontFamily="var(--font-mono)" fontSize="11" fill="var(--color-ink-3)">
          sub-solar {bearing(sub.lonDeg)}E
        </text>
      </svg>

      {/* Real buttons, one per pin. An SVG cannot hold a <button>, so the pins
          above are drawn presentationally and these sit on top of them: a
          48 x 48 target each, reachable by Tab, announced with the site's
          name and whether it is the one selected. They replace <g role=button>,
          which the rule about real elements forbids. */}
      {onSelect &&
        sites.map(({ site: s, at: p }) => (
          <button
            key={s.id}
            type="button"
            onClick={() => onSelect(s.id)}
            aria-pressed={s.id === selectedSiteId}
            aria-label={`${s.code}, ${s.name}`}
            className="absolute size-12 -translate-x-1/2 -translate-y-1/2 rounded-control bg-transparent"
            style={{ left: `${(p.x / 700) * 100}%`, top: `${(p.y / 700) * 100}%` }}
          />
        ))}
      {onMissionPin &&
        pins.map(({ pin, at }) => (
          <button
            key={pin.key}
            type="button"
            onClick={() => onMissionPin(pin.key)}
            onMouseEnter={() => onMissionHover?.(pin.key)}
            onMouseLeave={() => onMissionHover?.(null)}
            onFocus={() => onMissionHover?.(pin.key)}
            onBlur={() => onMissionHover?.(null)}
            aria-pressed={pin.pressed}
            aria-label={pin.label}
            className="absolute size-12 -translate-x-1/2 -translate-y-1/2 rounded-control bg-transparent"
            style={{ left: `${(at.x / 700) * 100}%`, top: `${(at.y / 700) * 100}%` }}
          />
        ))}
    </div>
  )
}
