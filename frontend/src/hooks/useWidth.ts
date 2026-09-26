import { useLayoutEffect, useState, type RefObject } from 'react'

/**
 * The width of an element, kept current as it resizes, for charts drawn in
 * SVG at their real size (so their text stays readable on a phone instead of
 * shrinking with a viewBox). `fallback` is used before the first measurement
 * and where there is no layout (tests).
 */
export function useWidth(ref: RefObject<HTMLElement | null>, fallback = 720): number {
  const [w, setW] = useState(fallback)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const set = () => {
      const next = Math.round(el.getBoundingClientRect().width)
      if (next > 0) setW(next)
    }
    set()
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(set)
    ro.observe(el)
    return () => ro.disconnect()
  }, [ref])
  return w
}
