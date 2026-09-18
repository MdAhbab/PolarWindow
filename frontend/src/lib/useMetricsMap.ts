import { useCallback, useMemo } from 'react'
import { useQueries, type UseQueryResult } from '@tanstack/react-query'
import type { HorizonMask, SiteMetrics } from './types'
import { useWindowParams } from './mission'
import { getEngineVersion, useManySiteMetrics, type WindowParams } from './api/queries'
import { api, type MetricsDTO, type WindowsDTO } from './api/client'
import { adaptHorizon, adaptSite, type Autonomy } from './api/adapters'

/**
 * The `Record<siteId, SiteMetrics>` the map, compare and report screens draw from.
 *
 * This replaces the store field of the same shape. Assembling it from queries
 * rather than caching it in zustand means it cannot go stale behind the data
 * it is supposed to describe.
 *
 * Every piece is referentially stable while its data is unchanged (`combine`
 * below, and the memo over them). Without that the map screen rebuilt fifteen
 * sites' arcs on every frame of the date slider, because the objects it keyed
 * its memo on were recreated on every render.
 */
export function useSiteMetricsMap(siteIds: string[]): {
  map: Record<string, SiteMetrics>
  autonomy: Record<string, Autonomy>
  done: number
  total: number
  isPending: boolean
  error: unknown
} {
  const w = useWindowParams()
  const metrics = useManySiteMetrics(siteIds, w)
  const windows = useManyWindows(siteIds, w)
  const masks = useManyHorizons(siteIds)

  const { map, autonomy } = useMemo(() => {
    const out: Record<string, SiteMetrics> = {}
    const packets: Record<string, Autonomy> = {}
    for (const id of siteIds) {
      const m = metrics.byId[id]
      const win = windows[id]
      const mask = masks[id]
      if (!m || !win || !mask) continue
      // Adapt only sites whose three parts have all arrived.
      const adapted = adaptSite(id, win, m, mask)
      out[id] = adapted.metrics
      packets[id] = adapted.autonomy
    }
    return { map: out, autonomy: packets }
  }, [siteIds, metrics.byId, windows, masks])

  return {
    map,
    autonomy,
    done: Object.keys(map).length,
    total: siteIds.length,
    isPending: metrics.isPending,
    error: metrics.error,
  }
}

function byId<T>(siteIds: string[]) {
  return (results: UseQueryResult<T>[]): Record<string, T> =>
    Object.fromEntries(results.flatMap((r, i) => (r.data ? [[siteIds[i], r.data]] : []))) as Record<
      string,
      T
    >
}

function useManyWindows(siteIds: string[], w: WindowParams): Record<string, WindowsDTO> {
  const combine = useCallback(byId<WindowsDTO>(siteIds), [siteIds])
  return useQueries({
    queries: siteIds.map((id) => ({
      queryKey: ['windows', getEngineVersion(), id, w.start, w.end, w.stepS],
      staleTime: 5 * 60 * 1000,
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        api.windows(id, { start: w.start, end: w.end, step_s: w.stepS }, signal),
    })),
    combine,
  })
}

function useManyHorizons(siteIds: string[]): Record<string, HorizonMask> {
  const combine = useCallback(byId<HorizonMask>(siteIds), [siteIds])
  return useQueries({
    queries: siteIds.map((id) => ({
      queryKey: ['horizon', getEngineVersion(), id],
      staleTime: Infinity,
      gcTime: Infinity,
      queryFn: async ({ signal }: { signal: AbortSignal }) =>
        adaptHorizon(await api.horizon(id, 1, signal)),
    })),
    combine,
  })
}

export type { MetricsDTO }
