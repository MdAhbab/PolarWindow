import type React from 'react'
import { useReducedMotion } from '../../hooks/useMotion'
import { ringLabel, type RingState } from './model'

const R = 8
const C = 2 * Math.PI * R

/**
 * The ring in the shell: an empty track when nothing is being worked out,
 * filling with the running items' own progress, and a short arc turning when
 * none has a figure yet (standing still under reduced motion). The count
 * beside it is the number of things in the tray; a dashed track says the
 * saved copy has no activity at all. Shape and number, never colour alone.
 */
export function ActivityRing({
  ring,
  live,
  expanded,
  onClick,
  controls,
}: {
  ring: RingState
  live: boolean
  expanded: boolean
  onClick: (e: React.MouseEvent<HTMLButtonElement>) => void
  controls?: string
}) {
  const reduced = useReducedMotion()
  const label = ringLabel(ring, live)
  const busy = live && ring.count > 0
  const spinning = busy && ring.fraction === null
  const fill = busy && ring.fraction !== null ? Math.max(0.04, ring.fraction) : 0
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-haspopup="dialog"
      aria-expanded={expanded}
      aria-controls={controls}
      onClick={onClick}
      className="pw-press inline-flex h-12 min-w-12 items-center justify-center gap-1.5 rounded-pill px-3 text-ink-2 hover:bg-inset hover:text-ink aria-expanded:bg-inset aria-expanded:text-ink"
    >
      <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true" className="shrink-0">
        <circle
          cx="11"
          cy="11"
          r={R}
          fill="none"
          stroke="var(--color-line-strong)"
          strokeWidth="2.25"
          strokeDasharray={live ? undefined : '2.2 2.6'}
        />
        {busy && (
          <g
            className={spinning && !reduced ? 'pw-ring-spin' : undefined}
            style={{ transformOrigin: '11px 11px' }}
          >
            <circle
              cx="11"
              cy="11"
              r={R}
              fill="none"
              stroke="var(--color-ink)"
              strokeWidth="2.25"
              strokeLinecap="round"
              strokeDasharray={C}
              strokeDashoffset={spinning ? C * 0.75 : C * (1 - fill)}
              transform="rotate(-90 11 11)"
              className={reduced ? undefined : 'pw-ring-fill'}
            />
          </g>
        )}
        {!busy && live && <circle cx="11" cy="11" r="1.6" fill="var(--color-ink-3)" />}
      </svg>
      {busy && <span className="tnum text-body font-semibold text-ink">{ring.count}</span>}
    </button>
  )
}
