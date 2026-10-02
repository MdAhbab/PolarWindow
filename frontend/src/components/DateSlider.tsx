import { useEffect, useRef } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { useMission } from '../lib/store'
import { useReducedMotion } from '../hooks/useMotion'
import { humanStampH, msFromModelH, shortDate, spanWords } from '../lib/format'
import { SYNODIC_HOURS } from '../lib/store'
import { Icon } from './Icon'

/**
 * M1's driver.
 *
 * Play runs the whole window in 14 seconds, linear — the Sun really does move
 * at a constant rate, and easing would put an acceleration into a motion that
 * has none. Scrubbing is 1:1 with the pointer with no tween at all, because a
 * direct manipulation that lags is worse than no animation.
 *
 * On a landing-site page it is the page's control card: a round play button
 * that says what it does, the track, and where the dates are now as a day
 * counter. `compact` is the bare track, for inside a chart card.
 */
const PLAY_SECONDS = 14

export function DateSlider({ compact = false }: { compact?: boolean }) {
  const { cursorH, windowHours, windowStartH, setCursor, playing, setPlaying } = useMission(
    useShallow((s) => ({
      cursorH: s.cursorH,
      windowHours: s.windowHours,
      windowStartH: s.windowStartH,
      setCursor: s.setCursor,
      playing: s.playing,
      setPlaying: s.setPlaying,
    })),
  )
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
  // U10: a person's timestamp on screen and in aria-valuetext; ISO is for exports.
  const now = humanStampH(windowStartH + cursorH, windowStartH)
  const lunarDay = Math.abs(windowHours - SYNODIC_HOURS) < 1
  const span = lunarDay ? `one lunar day, ${Math.round(windowHours)} hours` : spanWords(windowHours)
  const range = `${shortDate(msFromModelH(windowStartH))} → ${shortDate(msFromModelH(windowStartH + windowHours))}`

  const track = (
    <div className="relative flex h-12 grow items-center">
      <div className="absolute inset-x-0 h-1 rounded-pill bg-inset" />
      <div className="absolute left-0 h-1 rounded-pill bg-ink-3" style={{ width: `${pct}%` }} />
      {/* The thumb: a 3 px bar with a halo of the card behind it, so it reads on the fill and off it. */}
      <div
        className="pointer-events-none absolute h-6 w-[3px] -translate-x-1/2 rounded-pill bg-ink shadow-[0_0_0_4px_var(--pw-core,var(--color-panel))]"
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
        aria-valuetext={now}
        aria-keyshortcuts="[ ] Shift+[ Shift+]"
      />
    </div>
  )

  const steps = reduced && (
    <div className="flex shrink-0 gap-2">
      <button
        type="button"
        aria-label="Step back six hours"
        onClick={() => setCursor(Math.max(0, cursorH - 6))}
        className="pw-press inline-flex h-12 min-w-12 items-center justify-center rounded-pill border border-line-strong px-3 text-body text-ink hover:bg-inset"
      >
        −6h
      </button>
      <button
        type="button"
        aria-label="Step forward six hours"
        onClick={() => setCursor(Math.min(windowHours, cursorH + 6))}
        className="pw-press inline-flex h-12 min-w-12 items-center justify-center rounded-pill border border-line-strong px-3 text-body text-ink hover:bg-inset"
      >
        +6h
      </button>
    </div>
  )

  if (compact) {
    return (
      <div className="flex grow flex-col gap-2">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <label htmlFor="pw-date" className="text-small font-semibold text-ink-2">
            Dates: {span}
          </label>
          <span className="font-mono text-caption text-ink-2 sm:text-right">
            {range}
            <span className="text-ink"> · {now}</span>
          </span>
        </div>
        <div className="flex items-center gap-3">
          {track}
          {steps}
        </div>
      </div>
    )
  }

  // "Day 12, 26 March, 09:40 UTC": the day for the counter, the rest under it.
  const comma = now.indexOf(', ')
  const stamp = comma > 0 ? now.slice(comma + 2) : now
  const counter =
    windowHours >= 48
      ? // The same count as the clock on the Site page: "Day 12 of 30".
        { figure: `Day ${Math.floor(cursorH / 24)}`, of: `of ${Math.round(windowHours / 24)}` }
      : { figure: `Hour ${Math.floor(cursorH)}`, of: `of ${spanWords(windowHours)}` }

  return (
    <div
      data-guide="date-bar"
      className="pw-card pw-card-quiet grid items-center gap-x-5 gap-y-3 p-3 pr-4 sm:grid-cols-[auto_minmax(0,1fr)_auto] sm:p-4 sm:pr-6"
    >
      <div className="flex items-center gap-3 sm:contents">
        <button
          type="button"
          aria-label={playing ? 'Pause' : 'Play through the dates'}
          onClick={() => setPlaying(!playing)}
          disabled={reduced}
          title={reduced ? 'Play is off under reduced motion. Use [ and ] to step.' : 'Play through the dates (Space)'}
          className="pw-press inline-flex h-12 shrink-0 items-center justify-center gap-2 rounded-pill border border-line-strong bg-tray pr-4 pl-3.5 text-body font-semibold text-ink hover:border-ink-3 hover:bg-inset disabled:text-ink-3"
        >
          <Icon name={playing ? 'pause' : 'play'} size={18} strokeWidth={1.8} />
          <span aria-hidden="true">{playing ? 'Pause' : 'Play'}</span>
        </button>
        <span className="flex flex-col items-end text-right sm:hidden" aria-hidden="true">
          <span className="pw-figure text-[22px] leading-6 text-ink">
            {counter.figure}{' '}
            <span className="text-body font-normal tracking-normal text-ink-3 [font-stretch:100%]">{counter.of}</span>
          </span>
        </span>
      </div>

      <div className="flex min-w-0 flex-col gap-0.5">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4">
          <label htmlFor="pw-date" className="text-small font-semibold text-ink-2">
            Dates: {span}
          </label>
          <span className="font-mono text-caption text-ink-3">{range}</span>
        </div>
        <div className="flex items-center gap-3">
          {track}
          {steps}
        </div>
      </div>

      {/* Where the dates are now: said by the slider itself (aria-valuetext), drawn here as a counter. */}
      <div className="hidden flex-col items-end gap-0.5 text-right sm:flex" aria-hidden="true">
        <span className="pw-figure text-[26px] leading-7 whitespace-nowrap text-ink">
          {counter.figure}{' '}
          <span className="text-body font-normal tracking-normal text-ink-3 [font-stretch:100%]">{counter.of}</span>
        </span>
        <span className="font-mono text-caption whitespace-nowrap text-ink-2">{stamp}</span>
      </div>
    </div>
  )
}
