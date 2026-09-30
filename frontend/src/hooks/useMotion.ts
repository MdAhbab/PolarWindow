import { useEffect, useState } from 'react'
import { useMission } from '../lib/store'

/** True when either the OS asks for reduced motion or the in-app toggle does. */
export function useReducedMotion(): boolean {
  const manual = useMission((s) => s.motion) === 'reduced'
  const [os, setOs] = useState(
    () => typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches,
  )

  useEffect(() => {
    if (typeof matchMedia === 'undefined') return
    const mq = matchMedia('(prefers-reduced-motion: reduce)')
    const on = () => setOs(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])

  return manual || os
}

/**
 * cubic-bezier(.16, 1, .3, 1) — the one easing curve in the system, used by
 * M2, M4 and M5. Solved by Newton with a bisection fallback so the code says
 * exactly what the spec sheet says.
 */
export function easeOut(t: number): number {
  return bezier(0.16, 1, 0.3, 1, t)
}

function bezier(x1: number, y1: number, x2: number, y2: number, x: number): number {
  if (x <= 0) return 0
  if (x >= 1) return 1
  const cx = 3 * x1
  const bx = 3 * (x2 - x1) - cx
  const ax = 1 - cx - bx
  const cy = 3 * y1
  const by = 3 * (y2 - y1) - cy
  const ay = 1 - cy - by
  const sampleX = (t: number) => ((ax * t + bx) * t + cx) * t
  const slopeX = (t: number) => (3 * ax * t + 2 * bx) * t + cx

  let t = x
  for (let i = 0; i < 8; i++) {
    const d = sampleX(t) - x
    if (Math.abs(d) < 1e-6) break
    const s = slopeX(t)
    if (Math.abs(s) < 1e-6) break
    t -= d / s
  }
  t = Math.max(0, Math.min(1, t))
  return ((ay * t + by) * t + cy) * t
}

/**
 * A motion class, or nothing under reduced motion. The branch is made here in
 * code (invariant 8); the CSS floor in globals.css only catches what slips by.
 */
export function useMotionClass(cls: string): string {
  return useReducedMotion() ? '' : cls
}
