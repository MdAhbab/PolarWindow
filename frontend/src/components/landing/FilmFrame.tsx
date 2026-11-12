import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { FILM_FEATHER, filmFrame, type FilmFrame as Frame } from './film'
import './landing.css'

/**
 * The picture of a film, inside its stage. The stage is the whole screen in the page's canvas colour; the
 * picture is never larger than 1.25 times its own width (film.ts, filmFrame), centred, no taller than the
 * window, and where it does not reach an edge of the stage that edge fades into the canvas (a CSS mask,
 * landing.css), so on a big screen the picture fades into space. A fine static grain lies over the
 * picture and nothing else.
 *
 * `native` is what the file is known to be before it loads; the child reports what it really is
 * (`videoWidth`, or the still's own width), so a larger file fills a larger screen with no change here.
 * The size is measured on resize (a ResizeObserver on the stage), never while scrolling.
 */
export function FilmFrame({
  native,
  grain,
  children,
}: {
  native: { w: number; h: number }
  /** The grain file is there (the film files are). */
  grain: boolean
  children: (report: (w: number, h: number) => void) => ReactNode
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [real, setReal] = useState<{ w: number; h: number } | null>(null)
  const [frame, setFrame] = useState<Frame | null>(null)
  const size = real ?? native

  const report = useCallback((w: number, h: number) => {
    if (w > 0 && h > 0) setReal((r) => (r && r.w === w && r.h === h ? r : { w, h }))
  }, [])

  const measure = useCallback(() => {
    const stage = ref.current?.parentElement
    if (!stage) return
    const r = stage.getBoundingClientRect()
    const next = filmFrame(r.width, r.height, window.innerHeight, size.w, size.h)
    setFrame((f) =>
      f && f.w === next.w && f.h === next.h && f.featherX === next.featherX && f.featherY === next.featherY ? f : next,
    )
  }, [size.w, size.h])

  useLayoutEffect(() => {
    measure()
  }, [measure])
  useEffect(() => {
    const stage = ref.current?.parentElement
    if (!stage) return
    const ro = new ResizeObserver(measure)
    ro.observe(stage)
    window.addEventListener('resize', measure)
    return () => {
      ro.disconnect()
      window.removeEventListener('resize', measure)
    }
  }, [measure])

  return (
    <div
      ref={ref}
      className="pw-film-frame"
      style={{
        width: frame ? frame.w : '100%',
        height: frame ? frame.h : '100%',
        ['--pw-fx' as string]: frame?.featherX ? `${FILM_FEATHER * 100}%` : '0%',
        ['--pw-fy' as string]: frame?.featherY ? `${FILM_FEATHER * 100}%` : '0%',
      }}
    >
      {children(report)}
      {grain && <span aria-hidden="true" className="pw-film-grain" />}
    </div>
  )
}
