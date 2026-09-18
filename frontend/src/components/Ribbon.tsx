import type { Arc } from '../lib/types'
import { hoursWithUnit } from '../lib/format'

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
  const longest =
    alertOverH === undefined
      ? undefined
      : arcs
          .filter((a) => !a.up && a.hours > alertOverH)
          .reduce<Arc | undefined>((b, a) => (!b || a.hours > b.hours ? a : b), undefined)

  return (
    <div
      className="relative flex border border-line"
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
            title={`${a.up ? 'above' : 'below'} the skyline · ${hoursWithUnit(a.hours)}`}
          >
            {showLabels && !a.up && w > 4 && (
              <span className="flex h-full items-center justify-center text-[11px] font-semibold text-ink">
                {Math.round(a.hours)}
              </span>
            )}
          </div>
        )
      })}
      {cursorH !== undefined && (
        <div
          className="pointer-events-none absolute top-0 bottom-0 w-0.5 bg-ink"
          style={{ left: `${(cursorH / windowHours) * 100}%` }}
          aria-hidden="true"
        />
      )}
      <span className="sr-only">
        Window opens at hour {Math.round(windowStartH)} and runs {Math.round(windowHours)} hours.
      </span>
    </div>
  )
}

function describeRibbon(arcs: Arc[], tone: 'sun' | 'earth'): string {
  const body = tone === 'sun' ? 'Sun' : 'Earth'
  const up = arcs.filter((a) => a.up)
  const down = arcs.filter((a) => !a.up)
  const worst = down.reduce((m, a) => Math.max(m, a.hours), 0)
  return `${body} above the local skyline in ${up.length} stretches, below it in ${down.length}; the longest gap is about ${Math.round(worst)} hours.`
}
