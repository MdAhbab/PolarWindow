import { useEffect, useRef, useState } from 'react'
import { useReducedMotion } from '../hooks/useMotion'
import { frameGaps, framesTooSlow } from '../lib/frameBudget'

/** Frames timed once after load (the gaps between them are judged), and the wait after load before timing. */
const SAMPLE_FRAMES = 14
const SETTLE_MS = 1500

/**
 * The ambient glow behind every page inside the app (owner's request, L-12):
 * three very faint, very wide fields of the Sun's amber, Earth's cyan and the
 * brand blue, each drifting on its own slow loop (globals.css, `.pw-glow`).
 * Rendered once by the shell, outside the content that changes between pages,
 * so a page change neither restarts nor blinks it. Never on the front page.
 *
 * Where each field is on its loop comes from the clock, so a reload finds it
 * where it was. It is still under reduced motion and paused while the tab is
 * hidden; print, forced colours and high contrast drop it (CSS). On a machine
 * that cannot keep up (frames timed once after load) it stops drifting too.
 */
export function AmbientGlow() {
  const reduced = useReducedMotion()
  const root = useRef<HTMLDivElement>(null)
  // Seconds into every field's loop; the CSS turns it into a negative delay per field.
  const [at] = useState(() => Math.round((Date.now() / 1000) % 1e6))

  useEffect(() => {
    const el = root.current
    if (!el || typeof document === 'undefined') return
    const sync = () => el.toggleAttribute('data-paused', document.visibilityState === 'hidden')
    sync()
    document.addEventListener('visibilitychange', sync)
    return () => document.removeEventListener('visibilitychange', sync)
  }, [])

  // One measurement after load, no loop and no React state: a few animation
  // frames' timestamps; if the median gap is over about 30 ms the page cannot
  // keep up (no graphics acceleration) and the drift stops (`data-slow`, CSS).
  useEffect(() => {
    const el = root.current
    if (!el || reduced || typeof window === 'undefined' || typeof requestAnimationFrame === 'undefined') return
    const stamps: number[] = []
    let raf = 0
    let timer = 0
    const frame = (t: number) => {
      stamps.push(t)
      if (stamps.length <= SAMPLE_FRAMES) {
        raf = requestAnimationFrame(frame)
        return
      }
      el.toggleAttribute('data-slow', framesTooSlow(frameGaps(stamps)))
    }
    // After load, once the first draw has settled, so start-up work does not count against the machine.
    const begin = () => {
      timer = window.setTimeout(() => {
        raf = requestAnimationFrame(frame)
      }, SETTLE_MS)
    }
    if (document.readyState === 'complete') begin()
    else window.addEventListener('load', begin, { once: true })
    return () => {
      window.removeEventListener('load', begin)
      window.clearTimeout(timer)
      cancelAnimationFrame(raf)
    }
  }, [reduced])

  return (
    <div
      ref={root}
      aria-hidden="true"
      className="pw-glow"
      data-still={reduced || undefined}
      style={{ ['--pw-glow-at' as string]: at }}
    >
      <span className="pw-glow-field pw-glow-brand" />
      <span className="pw-glow-field pw-glow-earth" />
      <span className="pw-glow-field pw-glow-sun" />
    </div>
  )
}
