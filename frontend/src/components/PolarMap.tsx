import { subSolarPoint } from '../lib/geometry/ephemeris'
import { SITES } from '../lib/sites'
import { bearing } from '../lib/format'

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
function darkRegionPath(tH: number): string | null {
  const sub = subSolarPoint(tH)
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

function terminatorPath(tH: number): string | null {
  const sub = subSolarPoint(tH)
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
}: {
  tH: number
  selectedSiteId: string
  onSelect?: (id: string) => void
  size?: number
  className?: string
}) {
  const dark = darkRegionPath(tH)
  const term = terminatorPath(tH)
  const sub = subSolarPoint(tH)

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 700 700"
      className={className}
      role="img"
      aria-label={`South polar map from 80 degrees south to the pole. ${SITES.length} candidate sites. The sub-solar point is at longitude ${Math.round(
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

      {SITES.map((s) => {
        const p = project(s.latDeg, s.lonDeg)
        const selected = s.id === selectedSiteId
        return (
          <g key={s.id} transform={`translate(${p.x} ${p.y})`}>
            {selected && (
              <circle r="20" fill="none" stroke="var(--color-sun)" strokeWidth="2" strokeOpacity="0.55" />
            )}
            <g
              role={onSelect ? 'button' : undefined}
              tabIndex={onSelect ? 0 : undefined}
              aria-label={onSelect ? `Select ${s.name}` : undefined}
              onClick={() => onSelect?.(s.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  onSelect?.(s.id)
                }
              }}
              style={{ cursor: onSelect ? 'pointer' : undefined }}
            >
              {/* 48 px target whatever the visible mark is */}
              <circle r="24" fill="transparent" />
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
          </g>
        )
      })}

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
      <text
        x="32"
        y="676"
        fontFamily="var(--font-mono)"
        fontSize="11"
        fill="var(--color-ink-3)"
      >
        sub-solar {bearing(sub.lonDeg)}E
      </text>
    </svg>
  )
}
