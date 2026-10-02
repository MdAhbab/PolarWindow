import { useMemo, useState } from 'react'
import type { ReturnDTO } from '../lib/api/lifecycle'
import { useMission } from '../lib/store'
import { Panel } from '../components/ui'
import { SceneFrame, hasWebGL } from './SceneFrame'
import type { Zone } from './landingZones'

/**
 * Where it comes down, as a card on Return: Earth turned to the booster's
 * landing zone and the capsule's splashdown zone. There only when a zone has
 * a position and the browser has WebGL; the rows below say the same in words.
 */
export function ZoneCard({ ret, missionId }: { ret: ReturnDTO; missionId: string }) {
  const theme = useMission((s) => s.theme)
  const b = ret.booster
  const c = ret.capsule
  const zones = useMemo(() => {
    const out: Zone[] = []
    if (b?.zone) {
      out.push({
        key: 'booster',
        // Not published yet: the position is where the sea is read, not a landing zone.
        label: b.landing === 'unknown' ? 'Sea read here' : 'Booster',
        latDeg: b.zone.lat_deg,
        lonDeg: b.zone.lon_deg,
        radiusKm: b.zone.pm_km,
      })
    }
    if (c?.applicable && c.zone) {
      out.push({ key: 'capsule', label: 'Splashdown', latDeg: c.zone.lat_deg, lonDeg: c.zone.lon_deg, radiusKm: c.zone.pm_km })
    }
    return out
  }, [b, c])
  const props = useMemo(() => ({ zones }), [zones])
  const [failed, setFailed] = useState(false)
  if (!zones.length || !hasWebGL() || failed) return null
  const both = zones.length > 1
  return (
    <Panel as="section" className="flex min-w-0 flex-col gap-3 p-4 sm:p-5">
      <h3 className="text-title leading-6 font-semibold tracking-title text-ink">Where it comes down</h3>
      <SceneFrame
        sceneKey={`${missionId}|${theme}`}
        make={(canvas, p, opts) => import('./landingZones').then((s) => s.createLandingZones(canvas, p, opts))}
        props={props}
        onFail={() => setFailed(true)}
        fallback={<div className="aspect-[4/3] w-full rounded-control bg-inset sm:aspect-[21/9]" />}
        caption={`Earth turned to ${both ? 'the two places' : 'the place'}, on NASA’s Blue Marble. A ring is a zone’s published size; where there is none, the size is not published or is smaller than the mark. The light is for the picture, not for the hour of the landing.`}
      />
    </Panel>
  )
}
