import { useEffect, useRef, useState } from 'react'
import { easeOut, useReducedMotion } from './useMotion'

/**
 * M4 — number roll. 600 ms, in step with the ring fill, on tabular figures.
 *
 * Under reduced motion the value is set directly: no roll, no fade. The unit
 * and the plus-or-minus never animate in either mode.
 *
 * A roll runs between two real values only. A non-finite target means "no
 * value yet", and the first real value after it is set directly: rolling up
 * from zero would show numbers the server never sent. A hidden page gets the
 * value directly too, since it would not see the frames.
 */
export function useCountUp(target: number, durationMs = 600): number {
  const reduced = useReducedMotion()
  const [value, setValue] = useState(target)
  const fromRef = useRef(target)
  const rafRef = useRef(0)

  useEffect(() => {
    const from = fromRef.current
    if (reduced || !Number.isFinite(target) || !Number.isFinite(from) || document.hidden) {
      fromRef.current = target
      setValue(target)
      return
    }
    if (from === target) return
    const start = performance.now()

    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / durationMs)
      const v = from + (target - from) * easeOut(p)
      setValue(v)
      if (p < 1) rafRef.current = requestAnimationFrame(tick)
      else fromRef.current = target
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [target, durationMs, reduced])

  // The render before the effect runs: a first real value shows at once.
  return Number.isFinite(value) ? value : target
}
