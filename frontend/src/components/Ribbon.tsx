import type { Arc } from '../lib/types'
import { hoursWithUnit } from '../lib/format'
import { crossingBands } from '../lib/bands'
import { useReducedMotion } from '../hooks/useMotion'

/**
 * One body's window as a bar. Solid where it is above the local skyline,
 * hatched where terrain or the horizon has it. The hatch is never an empty
 * gap: "no data" and "dark" must not look the same.
 */
export function Ribbon({
  arcs,
  windowStartH,
  windowHours,
  tone,
  height = 26,
  cursorH,
  alertOverH,
  showLabels = false,
  ariaLabel,
}: {
  arcs: Arc[]
  windowStartH: number
  windowHours: number
  tone: 'sun' | 'earth'
  height?: number
  cursorH?: number
  /** Gaps longer than this are hatched in the alert hue. Omit for no limit. */
  alertOverH?: number
  showLabels?: boolean
  ariaLabel?: string
}) {
  const fill = tone === 'sun' ? 'bg-sun-fill' : 'bg-earth-fill'
  const reduced = useReducedMotion()
  const bands = crossingBands(arcs, windowHours)
  const longest =
    alertOverH === undefined
      ? undefined
      : arcs
          .filter((a) => !a.up && a.hours > alertOverH)
          .reduce<Arc | undefined>((b, a) => (!b || a.hours > b.hours ? a : b), undefined)

  return (
    <div
      className="pw-draw-bar relative flex origin-left border border-line"
      style={{ height }}
      role="img"
      aria-label={ariaLabel ?? describeRibbon(arcs, tone)}
    >
      {arcs.map((a, i) => {
        const w = (a.hours / windowHours) * 100
        const isWorst = longest === a
        return (
          <div
            key={i}
            style={{ width: `${w}%` }}
            className={
              a.up ? fill : isWorst ? 'hatch-alert' : 'hatch-blocked'
            }
            title={`${a.up ? 'above' : 'below'} the skyline · ${hoursWithUnit(
              a.hours,
              0,
              a.openStart || a.openEnd,
            )}${a.openStart ? ' · began before the window' : ''}${a.openEnd ? ' · continues after it' : ''}`}
          >
            {showLabels && !a.up && w > 4 && (
              <span className="flex h-full items-center justify-center text-tag font-semibold text-ink">
                {Math.round(a.hours)}
              </span>
            )}
          </div>
        )
      })}
      {/* M6: the timing margin at every crossing, hatched at −45°. Breathes
          under full motion; static at 0.34 opacity otherwise, decided here in
          code rather than left to the CSS media query alone. */}
      {bands.map((b, i) => (
        <div
          key={`band-${i}`}
          aria-hidden="true"
          className={`hatch-uncertain pointer-events-none absolute top-0 bottom-0 ${reduced ? '' : 'breathe'}`}
          style={{
            left: `${(b.fromH / windowHours) * 100}%`,
            width: `${((b.toH - b.fromH) / windowHours) * 100}%`,
            opacity: reduced ? 0.34 : undefined,
          }}
        />
      ))}
      {cursorH !== undefined && (
        <div
          className="pointer-events-none absolute top-0 bottom-0 w-0.5 bg-ink"
          style={{ left: `${(cursorH / windowHours) * 100}%` }}
          aria-hidden="true"
        />
      )}
      <span className="sr-only">
        These dates start at hour {Math.round(windowStartH)} and last {Math.round(windowHours)} hours.
      </span>
    </div>
  )
}

function describeRibbon(arcs: Arc[], tone: 'sun' | 'earth'): string {
  const body = tone === 'sun' ? 'Sun' : 'Earth'
  const up = arcs.filter((a) => a.up)
  const down = arcs.filter((a) => !a.up)
  const worst = down.reduce<Arc | undefined>((m, a) => (!m || a.hours > m.hours ? a : m), undefined)
  const cut = worst && (worst.openStart || worst.openEnd)
  return `${body} above the local skyline in ${up.length} stretches, below it in ${down.length}; the longest time below is ${
    cut ? 'at least' : 'about'
  } ${Math.round(worst?.hours ?? 0)} hours${cut ? ', cut short by the chosen dates' : ''}.`
}
