import { useEffect, useRef, useState } from 'react'
import { useReducedMotion } from '../hooks/useMotion'

/**
 * The ambient glow behind every page inside the app (owner's request, L-12):
 * three very faint, very wide fields of the Sun's amber, Earth's cyan and the
 * brand blue, each drifting on its own slow loop (globals.css, `.pw-glow`).
 * Rendered once by the shell, outside the content that changes between pages,
 * so a page change neither restarts nor blinks it. Never on the front page.
 *
 * Where each field is on its loop comes from the clock, so a reload finds it
 * where it was. It is still under reduced motion and paused while the tab is
 * hidden; print, forced colours and high contrast drop it (CSS).
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
