import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { API_BASE } from '../lib/api/client'
import { DATA_MODE } from '../lib/api/snapshot'
import type { TripDTO } from '../lib/api/lifecycle'
import { useMission } from '../lib/store'
import { Panel } from '../components/ui'
import { SceneFrame, hasWebGL } from './SceneFrame'

/**
 * The flown path to the Moon as a card on Trip. It is drawn from the same
 * orbit file the step offers as a download, so it is there only for a flown
 * trip, with the live service, in a browser with WebGL; otherwise the page
 * keeps the day-by-day strip above it, which says the same in a flat drawing.
 * The lander moves along the path as the card scrolls through the screen.
 */
export function PathCard({ trip, missionId }: { trip: TripDTO; missionId: string }) {
  const theme = useMission((s) => s.theme)
  const able = trip.source === 'flown' && DATA_MODE !== 'snapshot' && hasWebGL()
  const file = useQuery({
    queryKey: ['trip-path', missionId],
    queryFn: async ({ signal }) => {
      const r = await fetch(`${API_BASE}/missions/${encodeURIComponent(missionId)}/trip/export?format=csv`, { signal })
      if (!r.ok) throw new Error(`trip export ${r.status}`)
      return r.text()
    },
    enabled: able,
    staleTime: Infinity,
    retry: false,
  })
  const [failed, setFailed] = useState(false)

  // How far the card has come through the screen: 0 as its top enters, 1 as its foot leaves.
  const card = useRef<HTMLDivElement>(null)
  const [progress, setProgress] = useState(0)
  const shown = able && Boolean(file.data) && !failed
  useEffect(() => {
    if (!shown) return
    let raf = 0
    const measure = () => {
      raf = 0
      const el = card.current
      if (!el) return
      const r = el.getBoundingClientRect()
      const vh = window.innerHeight
      setProgress(Math.max(0, Math.min(1, (vh - r.top) / (vh + r.height))))
    }
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(measure)
    }
    measure()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
    }
  }, [shown])

  const light = useMemo(() => trip.samples.map((s) => ({ t: Date.parse(s.t), lit: s.light !== 'dark' })), [trip.samples])
  const burns = useMemo(() => trip.burns.map((b) => Date.parse(b.t)), [trip.burns])
  const props = useMemo(() => ({ csv: file.data ?? '', light, burns, progress }), [file.data, light, burns, progress])

  if (!shown) return null
  return (
    <Panel as="section" className="flex min-w-0 flex-col gap-3 p-4 sm:p-5">
      <h3 className="text-title leading-6 font-semibold tracking-title text-ink">The path to the Moon</h3>
      <div ref={card}>
        <SceneFrame
          sceneKey={`${missionId}|${theme}`}
          make={(canvas, p, opts) => import('./tripPath').then((s) => s.createTripPath(canvas, p, opts))}
          props={props}
          onFail={() => setFailed(true)}
          fallback={<div className="aspect-[4/3] w-full rounded-control bg-inset sm:aspect-[21/9]" />}
          caption="The flown path as NASA reconstructed it, seen from Earth at true distance; Earth and the Moon are drawn three times their size, the Moon where the trip ends. Amber is sunlight, grey is shadow, the dots are burns, and a gap in the reconstruction is left empty. The laps round the Moon show as a wavy line because the Moon was moving. Scroll to move the lander along the path."
        />
      </div>
    </Panel>
  )
}
