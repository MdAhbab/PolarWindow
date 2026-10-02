import type { Mission } from '../lib/api/adapters'

/**
 * The Moon view (§10.2): two orthographic discs centred on 0°E and 180°E.
 *
 * The discs are schematic and the positions are exact: a 30° graticule in
 * `line`, the limb in `line-strong`, the disc in `panel`, and each target a
 * diamond at its published coordinate. The discs are `role="img"` with a
 * sentence naming what is on each; the mission list is the interaction, so
 * nothing here duplicates it as a hidden control.
 */

const R = 100
const C = 110
const VIEW = 220
const DEG = Math.PI / 180

interface Placed {
  mission: Mission
  x: number
  y: number
}

/** Orthographic projection about (0°, lon0). Null on the hidden hemisphere. */
export function orthographic(latDeg: number, lonDeg: number, lon0Deg: number): { x: number; y: number } | null {
  const lat = latDeg * DEG
  const dLon = (lonDeg - lon0Deg) * DEG
  if (Math.cos(lat) * Math.cos(dLon) < 0) return null
  return { x: C + R * Math.cos(lat) * Math.sin(dLon), y: C - R * Math.sin(lat) }
}

function Graticule() {
  const parallels = [-60, -30, 0, 30, 60]
  const meridians = [30, 60]
  return (
    <g fill="none" stroke="var(--color-line)" strokeWidth="1">
      {parallels.map((lat) => {
        const y = C - R * Math.sin(lat * DEG)
        const half = R * Math.cos(lat * DEG)
        return <path key={`p${lat}`} d={`M${C - half} ${y} H${C + half}`} />
      })}
      <path d={`M${C} ${C - R} V${C + R}`} />
      {meridians.map((d) => (
        <ellipse key={`m${d}`} cx={C} cy={C} rx={R * Math.sin(d * DEG)} ry={R} />
      ))}
    </g>
  )
}

function Disc({
  title,
  lon0,
  missions,
  highlight,
  caption,
  onPole,
}: {
  title: string
  lon0: number
  missions: Mission[]
  highlight: Set<string>
  caption?: string | null
  onPole?: () => void
}) {
  const placed: Placed[] = missions.flatMap((m) => {
    if (!m.target) return []
    const p = orthographic(m.target.latDeg, m.target.lonDeg, lon0)
    return p ? [{ mission: m, ...p }] : []
  })
  const names = [...new Set(placed.map((p) => p.mission.name))]
  const summary = `${title}. ${
    names.length
      ? `${names.length} mission target${names.length === 1 ? '' : 's'} shown: ${names.join(', ')}.`
      : 'No mission target in this view.'
  } Schematic globe; positions from published coordinates.`

  return (
    <figure className="flex min-w-0 flex-col items-center gap-2">
      <div className="relative w-full max-w-[260px]">
        <svg viewBox={`0 0 ${VIEW} ${VIEW}`} className="block w-full" role="img" aria-label={summary}>
          <circle cx={C} cy={C} r={R} fill="var(--color-panel)" />
          <Graticule />
          <circle cx={C} cy={C} r={R} fill="none" stroke="var(--color-line-strong)" strokeWidth="1.5" />
          {placed.map(({ mission: m, x, y }) => {
            const on = highlight.has(m.id)
            const dashed = m.target?.coordinateKind !== 'actual_landing'
            return (
              <g key={m.id} transform={`translate(${x} ${y})`}>
                <rect
                  x="-3.5"
                  y="-3.5"
                  width="7"
                  height="7"
                  transform="rotate(45)"
                  fill={on ? 'var(--color-ink)' : 'var(--color-panel)'}
                  stroke="var(--color-ink)"
                  strokeWidth="1.4"
                  strokeDasharray={dashed ? '2 1.6' : undefined}
                />
                {on && (
                  <text
                    x={x > C ? -8 : 8}
                    y="3.5"
                    textAnchor={x > C ? 'end' : 'start'}
                    fontFamily="var(--font-sans)"
                    fontSize="10"
                    fontWeight="600"
                    fill="var(--color-ink)"
                    paintOrder="stroke"
                    stroke="var(--color-panel)"
                    strokeWidth="3"
                  >
                    {m.name}
                  </text>
                )}
              </g>
            )
          })}
        </svg>
        {onPole && (
          <button
            type="button"
            onClick={onPole}
            aria-label={`Show the south-polar inset (${title.toLowerCase()})`}
            title="Show the south-polar inset"
            className="absolute size-12 -translate-x-1/2 -translate-y-1/2 rounded-pill bg-transparent"
            style={{ left: '50%', top: `${((C + R - 8) / VIEW) * 100}%` }}
          />
        )}
      </div>
      <figcaption className="flex flex-col items-center gap-0.5 text-center">
        <span className="text-small font-semibold text-ink">{title}</span>
        {caption && <span className="text-caption text-ink-2">{caption}</span>}
      </figcaption>
    </figure>
  )
}

export function MoonDiscs({
  missions,
  highlight,
  earthNeverRisesOnFarSide,
  onPole,
}: {
  missions: Mission[]
  highlight: Set<string>
  /**
   * A far-side mission is focused and its site's Earth contact, from the API,
   * is zero. The caption is a fact from the data, never from the drawing.
   */
  earthNeverRisesOnFarSide: boolean
  onPole?: () => void
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-2 gap-3">
        <Disc title="Near side (faces Earth)" lon0={0} missions={missions} highlight={highlight} onPole={onPole} />
        <Disc
          title="Far side"
          lon0={180}
          missions={missions}
          highlight={highlight}
          caption={earthNeverRisesOnFarSide ? 'Earth never rises here' : null}
          onPole={onPole}
        />
      </div>
      <p className="text-center text-caption text-ink-3">Schematic globe; positions from published coordinates.</p>
    </div>
  )
}
