import { useEffect, useRef } from 'react'
import { useMission } from '../lib/store'
import { useReducedMotion } from '../hooks/useMotion'
import { clockUTC, shortDateUTC } from '../lib/format'
import { Icon } from './Icon'

/**
 * M1's driver.
 *
 * Play runs the whole window in 14 seconds, linear — the Sun really does move
 * at a constant rate, and easing would put an acceleration into a motion that
 * has none. Scrubbing is 1:1 with the pointer with no tween at all, because a
 * direct manipulation that lags is worse than no animation.
 */
const PLAY_SECONDS = 14

export function DateSlider({ compact = false }: { compact?: boolean }) {
  const { cursorH, windowHours, windowStartH, setCursor, playing, setPlaying } = useMission()
  const reduced = useReducedMotion()
  const raf = useRef(0)
  const last = useRef(0)

  useEffect(() => {
    if (!playing || reduced) return
    last.current = performance.now()
    const tick = (now: number) => {
      const dt = now - last.current
      last.current = now
      const step = (windowHours / (PLAY_SECONDS * 1000)) * dt
      const next = useMission.getState().cursorH + step
      setCursor(next > windowHours ? next - windowHours : next)
      raf.current = requestAnimationFrame(tick)
    }
    raf.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf.current)
  }, [playing, windowHours, setCursor, reduced])

  const pct = (cursorH / windowHours) * 100

  return (
    <div className="flex grow flex-col gap-2">
      <div className="flex items-baseline justify-between gap-4">
        <label htmlFor="pw-date" className="text-[12px] font-semibold tracking-[0.12em] text-ink-3 uppercase">
          Mission window — one lunar day, {Math.round(windowHours)} h
        </label>
        <span className="font-mono text-[12px] text-ink-2">
          {shortDateUTC(windowStartH)} → {shortDateUTC(windowStartH + windowHours)}
          <span className="text-ink"> · {clockUTC(windowStartH + cursorH)}</span>
        </span>
      </div>

      <div className="flex items-center gap-3">
        {!compact && (
          <button
            type="button"
            aria-label={playing ? 'Pause the window' : 'Play the window'}
            onClick={() => setPlaying(!playing)}
            disabled={reduced}
            title={reduced ? 'Play is off under reduced motion — use [ and ] to step' : undefined}
            className="inline-flex size-12 shrink-0 items-center justify-center rounded-control border border-line-strong text-ink hover:bg-inset disabled:text-ink-3"
          >
            <Icon name={playing ? 'pause' : 'play'} size={18} strokeWidth={1.8} />
          </button>
        )}

        <div className="relative flex h-12 grow items-center">
          <div className="absolute inset-x-0 h-1 bg-inset" />
          <div className="absolute left-0 h-1 bg-line-strong" style={{ width: `${pct}%` }} />
          <div
            className="pointer-events-none absolute h-6 w-1 -translate-x-1/2 bg-ink"
            style={{ left: `${pct}%` }}
          />
          <input
            id="pw-date"
            type="range"
            min={0}
            max={windowHours}
            step={0.25}
            value={cursorH}
            onChange={(e) => {
              setCursor(Number(e.target.value))
              setPlaying(false)
            }}
            className="absolute inset-x-0 h-12 w-full cursor-pointer opacity-0"
            aria-valuetext={clockUTC(windowStartH + cursorH)}
          />
        </div>

        {reduced && (
          <div className="flex shrink-0 gap-2">
            <button
              type="button"
              aria-label="Step back six hours"
              onClick={() => setCursor(Math.max(0, cursorH - 6))}
              className="inline-flex size-12 items-center justify-center rounded-control border border-line-strong text-ink hover:bg-inset"
            >
              −6h
            </button>
            <button
              type="button"
              aria-label="Step forward six hours"
              onClick={() => setCursor(Math.min(windowHours, cursorH + 6))}
              className="inline-flex size-12 items-center justify-center rounded-control border border-line-strong text-ink hover:bg-inset"
            >
              +6h
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
