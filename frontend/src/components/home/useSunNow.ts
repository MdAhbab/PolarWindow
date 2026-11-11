import { useEffect, useMemo, useState } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { useMission } from '../../lib/store'
import { useSubSolar, useWindowParams, windowParamsFor } from '../../lib/mission'
import { useTimeline } from '../../lib/api/queries'
import { modelHFromMs } from '../../lib/format'
import { hasSite, siteById } from '../../lib/sites'
import { subSolarAt, type SubPoint } from '../../lib/subSolar'
import { minuteOf } from './model'

/** The clock, moved on every `ms` (a second for the clock, a minute for the map). */
export function useNow(ms: number): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const h = window.setInterval(() => setNow(Date.now()), ms)
    return () => window.clearInterval(h)
  }, [ms])
  return now
}

export interface SunNow {
  sun: SubPoint | null
  /** The instant the sun is for: the start of this UTC minute. */
  atMs: number
  state: 'loading' | 'shown' | 'unavailable'
}

/**
 * The sub-solar point for this minute, from the same SPICE Sun as every number
 * (the focused site's Sun track). When the window the person set covers now,
 * this is `useSubSolar` on it, a cache hit; otherwise a two-day track around
 * now is asked for, and the point read from it the same way.
 */
export function useSunNow(): SunNow {
  const atMs = minuteOf(useNow(60_000))
  const nowH = modelHFromMs(atMs)
  const { siteId, windowStartH, windowHours } = useMission(
    useShallow((s) => ({ siteId: s.siteId, windowStartH: s.windowStartH, windowHours: s.windowHours })),
  )
  const inWindow = nowH >= windowStartH && nowH < windowStartH + windowHours
  const fromWindow = useSubSolar(nowH)
  // The same query useSubSolar makes (a cache hit), read here only for its failure.
  const windowTl = useTimeline(siteId, useWindowParams(), inWindow)

  // Two days from the start of today (UTC), so the minute stays inside it all day.
  const dayStartH = Math.floor(nowH / 24) * 24
  const around = useMemo(() => windowParamsFor(dayStartH, 48), [dayStartH])
  const tl = useTimeline(siteId, around, !inWindow)
  const fromAround = useMemo(() => {
    if (inWindow || !tl.data || !hasSite(siteId)) return null
    const site = siteById(siteId)
    return subSolarAt(tl.data, site.latDeg, site.lonDeg, atMs)
  }, [inWindow, tl.data, siteId, atMs])

  const sun = inWindow ? fromWindow : fromAround
  const q = inWindow ? windowTl : tl
  const state: SunNow['state'] = sun ? 'shown' : q.isError || (q.data && !sun) ? 'unavailable' : 'loading'
  return { sun, atMs, state }
}
