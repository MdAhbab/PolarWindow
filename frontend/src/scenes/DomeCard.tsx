import { useCallback, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { useMission } from '../lib/store'
import type { SiteMetrics } from '../lib/types'
import { Button, Panel } from '../components/ui'
import { Icon } from '../components/Icon'
import { SceneFrame, hasWebGL, type SceneHandle } from './SceneFrame'
import type { DomeHandle, DomeProps } from './skylineDome'
import { DOME_EXAGGERATION_WORDS } from './words'

/** Pixels per degree on the compass strip under the view. */
const PX = 2
const MARKS = [
  ['N', 0],
  ['NE', 45],
  ['E', 90],
  ['SE', 135],
  ['S', 180],
  ['SW', 225],
  ['W', 270],
  ['NW', 315],
] as const

const EDGE =
  'pw-press absolute top-1/2 z-10 grid size-11 -translate-y-1/2 place-items-center rounded-pill border border-line-strong bg-panel/80 text-ink backdrop-blur-sm hover:bg-inset'

/**
 * The skyline dome as a card, for Site and Skyline. Without WebGL there is no
 * card: the skyline chart on the Skyline page is the same picture flat, and
 * it is always there.
 *
 * That it turns is shown, not told: it turns a quarter of the way round once
 * it comes into view, a pill on it says to drag (until someone does), arrow
 * buttons at its edges and the arrow keys turn it, a compass strip under it
 * slides as it turns, and two buttons face the Sun and Earth.
 */
export function DomeCard({ metrics, cursorH, heading = 'h3' }: { metrics: SiteMetrics; cursorH: number; heading?: 'h2' | 'h3' }) {
  const theme = useMission((s) => s.theme)
  const props = useMemo<DomeProps>(
    () => ({ elDeg: metrics.mask.elDeg, sun: metrics.sun.samples, earth: metrics.earth.samples, nowH: metrics.windowStartH + cursorH }),
    [metrics, cursorH],
  )
  const [failed, setFailed] = useState(false)
  const [dragged, setDragged] = useState(false)
  const [facing, setFacing] = useState('')
  const dome = useRef<DomeHandle | null>(null)
  const strip = useRef<HTMLDivElement>(null)

  const onReady = useCallback((h: SceneHandle<DomeProps>) => {
    const d = h as DomeHandle
    dome.current = d
    d.onFirstDrag(() => setDragged(true))
    d.onYaw((y) => {
      // Straight to the element: a frame of the turn is not a React render.
      if (strip.current) strip.current.style.transform = `translateX(${-(((y % 360) + 360) % 360) * PX}px)`
    })
  }, [])

  const turn = (deg: number) => {
    dome.current?.turnBy(deg)
    setDragged(true)
  }
  const face = (body: 'sun' | 'earth') => {
    dome.current?.face(body)
    setDragged(true)
    setFacing(body === 'sun' ? 'Facing the Sun' : 'Facing Earth')
  }
  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      e.preventDefault()
      turn(e.key === 'ArrowLeft' ? -30 : 30)
    }
  }

  if (!hasWebGL() || failed) return null
  const H = heading
  return (
    <Panel as="section" className="flex min-w-0 flex-col gap-3 p-4 sm:p-5">
      <H className="text-title leading-6 font-semibold tracking-title text-ink">Standing at the site, looking out</H>
      <div role="group" aria-label="Sky view. The left and right arrow keys turn it." onKeyDown={onKey} className="flex min-w-0 flex-col gap-3">
        <SceneFrame
          sceneKey={`${metrics.siteId}|${theme}`}
          make={(canvas, p, opts) => import('./skylineDome').then((s) => s.createSkylineDome(canvas, p, opts))}
          props={props}
          onFail={() => setFailed(true)}
          onReady={onReady}
          fallback={<div className="aspect-[16/10] w-full rounded-control bg-inset" />}
          overlay={
            <>
              <button type="button" aria-label="Turn left" onClick={() => turn(-45)} className={`${EDGE} left-2`}>
                <Icon name="chevron" size={18} strokeWidth={2} className="rotate-90" />
              </button>
              <button type="button" aria-label="Turn right" onClick={() => turn(45)} className={`${EDGE} right-2`}>
                <Icon name="chevron" size={18} strokeWidth={2} className="-rotate-90" />
              </button>
              <span
                aria-hidden="true"
                className={`pointer-events-none absolute bottom-3 left-1/2 inline-flex -translate-x-1/2 items-center gap-2 rounded-pill border border-line-strong bg-panel/85 px-3 py-1 text-caption font-semibold whitespace-nowrap sm:px-3.5 sm:py-1.5 sm:text-small text-ink backdrop-blur-sm transition-opacity duration-[var(--pw-dur-slow)] ${
                  dragged ? 'opacity-0' : 'opacity-100'
                }`}
              >
                <svg width="18" height="12" viewBox="0 0 18 12" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M1 6h16M5 2 1 6l4 4M13 2l4 4-4 4" />
                </svg>
                Drag to look around
              </span>
            </>
          }
          caption={`The skyline all around, with the Sun’s path and Earth’s loop over these dates. ${DOME_EXAGGERATION_WORDS}`}
        />
        <div aria-hidden="true" className="relative h-7 overflow-hidden rounded-control border border-line bg-inset">
          {/* Three turns side by side, so the strip never runs out while it slides. */}
          <div ref={strip} className="absolute top-0 left-1/2 h-full will-change-transform">
            {[-1, 0, 1].flatMap((turnN) =>
              MARKS.map(([t, az]) => (
                <span
                  key={`${turnN}-${t}`}
                  className={`absolute top-1/2 -translate-x-1/2 -translate-y-1/2 font-mono text-tag ${t.length === 1 ? 'font-semibold text-ink' : 'text-ink-3'}`}
                  style={{ left: (az + turnN * 360) * PX }}
                >
                  {t}
                </span>
              )),
            )}
          </div>
          <span className="absolute top-0 left-1/2 h-1.5 w-px -translate-x-1/2 bg-ink" />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => face('sun')}>
            <Icon name="sun" size={16} strokeWidth={1.8} className="text-sun" />
            Face the Sun
          </Button>
          <Button onClick={() => face('earth')}>
            <Icon name="earth" size={16} strokeWidth={1.8} className="text-earth" />
            Face Earth
          </Button>
          <span className="sr-only" aria-live="polite">
            {facing}
          </span>
        </div>
      </div>
    </Panel>
  )
}

