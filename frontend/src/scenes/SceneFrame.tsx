import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useReducedMotion } from '../hooks/useMotion'

/**
 * A three.js scene on a dashboard page (design-visual-refresh.md, *Three
 * dimensions*), with the page's flat drawing always underneath it.
 *
 * The scene's code (and three.js with it) is fetched only when the browser
 * has WebGL, the page is idle and the frame is within a screen of the
 * viewport; until then, and without WebGL, the flat drawing is the picture.
 * A scene draws on demand, never in a loop of its own: it asks for frames
 * while something moves (its own arrival, a drag, the dates changing) and is
 * still otherwise, so it costs nothing off screen or in a hidden tab. Under
 * reduced motion it draws its resting frame at once. It is disposed when the
 * page goes. The canvas is hidden from assistive technology: the numbers are
 * in the page's words and the flat drawing's table.
 */
export interface SceneHandle<P> {
  /** New data or a new moment (the date slider): draws again. */
  update: (props: P) => void
  /** The frame's size changed. */
  resize: () => void
  dispose: () => void
}

export type SceneFactory<P> = (canvas: HTMLCanvasElement, props: P, opts: { reduced: boolean }) => Promise<SceneHandle<P>>

let webgl: boolean | null = null
/** Whether this browser can draw a scene at all; without it a page keeps its flat drawing. */
export function hasWebGL(): boolean {
  if (webgl !== null) return webgl
  try {
    const c = document.createElement('canvas')
    const ctx = c.getContext('webgl2') ?? c.getContext('webgl')
    webgl = Boolean(ctx)
    ctx?.getExtension('WEBGL_lose_context')?.loseContext()
  } catch {
    webgl = false
  }
  return webgl
}

/** When the browser has a moment: after the page's own work, so a scene never delays an answer. */
function idle(fn: () => void) {
  if (typeof window.requestIdleCallback === 'function') window.requestIdleCallback(fn, { timeout: 1200 })
  else setTimeout(fn, 200)
}

export function SceneFrame<P>({
  make,
  props,
  fallback,
  caption,
  className = '',
  sceneKey,
  onFail,
}: {
  make: SceneFactory<P>
  props: P
  /** The flat drawing: the picture without WebGL, and while the scene loads. */
  fallback: ReactNode
  /** One line under the scene saying what it is and how it is drawn. */
  caption?: ReactNode
  className?: string
  /** A new scene for a new key (another site, another theme); props alone only redraw it. */
  sceneKey: string
  /** The scene could not be made. A card with no flat drawing of its own takes itself away. */
  onFail?: () => void
}) {
  const frame = useRef<HTMLDivElement>(null)
  const handle = useRef<SceneHandle<P> | null>(null)
  const latest = useRef(props)
  latest.current = props
  const failed = useRef(onFail)
  failed.current = onFail
  const reduced = useReducedMotion()
  const [live, setLive] = useState(false)

  useEffect(() => {
    const el = frame.current
    if (!el || !hasWebGL()) return

    const cv = document.createElement('canvas')
    cv.setAttribute('aria-hidden', 'true')
    cv.className =
      'absolute inset-0 h-full w-full touch-pan-y pointer-events-none opacity-0 transition-opacity duration-[var(--pw-dur-slow)]'
    el.appendChild(cv)

    let gone = false
    let started = false
    const begin = () => {
      if (started) return
      started = true
      idle(() => {
        if (gone) return
        make(cv, latest.current, { reduced })
          .then((h) => {
            if (gone) return h.dispose()
            handle.current = h
            cv.classList.remove('pointer-events-none', 'opacity-0')
            cv.classList.add('opacity-100')
            setLive(true)
          })
          .catch(() => {
            // A scene that fails leaves the flat drawing in place, as without WebGL.
            if (!gone) failed.current?.()
          })
      })
    }
    const near = new IntersectionObserver((es) => es.some((e) => e.isIntersecting) && begin(), { rootMargin: '100% 0px' })
    near.observe(el)
    const ro = new ResizeObserver(() => handle.current?.resize())
    ro.observe(el)
    return () => {
      gone = true
      near.disconnect()
      ro.disconnect()
      handle.current?.dispose()
      handle.current = null
      cv.remove()
      setLive(false)
    }
    // A new scene only for a new key or a change of motion preference; new
    // props reach the live one through `update` below.
  }, [sceneKey, reduced])

  useEffect(() => {
    handle.current?.update(props)
  }, [props])

  return (
    <div className={`flex min-w-0 flex-col gap-2 ${className}`}>
      <div ref={frame} className="relative min-w-0">
        <div className={live ? 'invisible' : ''} aria-hidden={live ? true : undefined}>
          {fallback}
        </div>
      </div>
      {live && caption && <p className="text-caption leading-caption text-ink-3">{caption}</p>}
    </div>
  )
}
