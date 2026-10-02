import { useMemo, useState } from 'react'
import { useMission } from '../lib/store'
import type { SiteMetrics } from '../lib/types'
import { Panel } from '../components/ui'
import { SceneFrame, hasWebGL } from './SceneFrame'
import { DOME_EXAGGERATION_WORDS } from './words'

/**
 * The skyline dome as a card, for Site and Skyline. Without WebGL there is no
 * card: the skyline chart on the Skyline page is the same picture flat, and
 * it is always there.
 */
export function DomeCard({ metrics, cursorH, heading = 'h3' }: { metrics: SiteMetrics; cursorH: number; heading?: 'h2' | 'h3' }) {
  const theme = useMission((s) => s.theme)
  const props = useMemo(
    () => ({ elDeg: metrics.mask.elDeg, sun: metrics.sun.samples, earth: metrics.earth.samples, nowH: metrics.windowStartH + cursorH }),
    [metrics, cursorH],
  )
  const [failed, setFailed] = useState(false)
  if (!hasWebGL() || failed) return null
  const H = heading
  return (
    <Panel as="section" className="flex min-w-0 flex-col gap-3 p-4 sm:p-5">
      <H className="text-title leading-6 font-semibold tracking-title text-ink">Standing at the site, looking out</H>
      <SceneFrame
        sceneKey={`${metrics.siteId}|${theme}`}
        make={(canvas, p, opts) => import('./skylineDome').then((s) => s.createSkylineDome(canvas, p, opts))}
        props={props}
        onFail={() => setFailed(true)}
        fallback={<div className="aspect-[16/10] w-full rounded-control bg-inset" />}
        caption={`The site’s own skyline all around, with the Sun’s path and Earth’s small loop over these dates; where the terrain hides them they show faintly. ${DOME_EXAGGERATION_WORDS} Drag to look around.`}
      />
    </Panel>
  )
}
