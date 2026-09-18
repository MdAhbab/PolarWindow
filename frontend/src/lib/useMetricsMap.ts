import { useMemo } from 'react'
import type { SiteMetrics } from './types'
import { useWindowParams } from './mission'
import { useManySiteMetrics } from './api/queries'

import { useQueries } from '@tanstack/react-query'
import { api } from './api/client'
import { adaptHorizon, adaptSite } from './api/adapters'
import { getEngineVersion, type WindowParams } from './api/queries'
import type { HorizonMask } from './types'
import type { MetricsDTO, WindowsDTO } from './api/client'

/**
 * The `Record<siteId, SiteMetrics>` the compare and report screens draw from.
 *
 * This replaces the store field of the same shape. Assembling it from queries
 * rather than caching it in zustand means it cannot go stale behind the data
 * it is supposed to describe -- the failure the old Worker's `jobId` counter
 * existed to prevent, now prevented by construction.
 */
export function useSiteMetricsMap(siteIds: string[]): {
  map: Record<string, SiteMetrics>
  done: number
  total: number
  isPending: boolean
  error: unknown
} {
  const w = useWindowParams()
  const metrics = useManySiteMetrics(siteIds, w)

  // Windows and horizon per site: hooks cannot be called in a loop, so this
  // relies on `useQueries` inside the two hooks below rather than mapping here.
  const windows = useManyWindows(siteIds, w)
  const masks = useManyHorizons(siteIds)

  const map = useMemo(() => {
    const out: Record<string, SiteMetrics> = {}
    for (const id of siteIds) {
      const m = metrics.byId[id]
      const win = windows[id]
      const mask = masks[id]
      if (!m || !win || !mask) continue
      // Adapt lazily, and only for sites whose three parts have all arrived.
      out[id] = adapt(id, win, m, mask)
    }
    return out
  }, [siteIds, metrics.byId, windows, masks])

  return {
    map,
    done: Object.keys(map).length,
    total: siteIds.length,
    isPending: metrics.isPending,
    error: metrics.error,
  }
}

const adapt = (
  id: string,
  win: WindowsDTO,
  m: MetricsDTO,
  mask: HorizonMask,
): SiteMetrics => adaptSite(id, win, m, mask).metrics

function useManyWindows(siteIds: string[], w: WindowParams): Record<string, WindowsDTO> {
  const results = useQueries({
    queries: siteIds.map((id) => ({
      queryKey: ['windows', getEngineVersion(), id, w.start, w.end, w.stepS],
      staleTime: 5 * 60 * 1000,
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        api.windows(id, { start: w.start, end: w.end, step_s: w.stepS }, signal),
    })),
  })
  return Object.fromEntries(
    results.flatMap((r, i) => (r.data ? [[siteIds[i], r.data]] : [])),
  ) as Record<string, WindowsDTO>
}

function useManyHorizons(siteIds: string[]): Record<string, HorizonMask> {
  const results = useQueries({
    queries: siteIds.map((id) => ({
      queryKey: ['horizon', getEngineVersion(), id],
      staleTime: Infinity,
      gcTime: Infinity,
      queryFn: async ({ signal }: { signal: AbortSignal }) =>
        adaptHorizon(await api.horizon(id, 1, signal)),
    })),
  })
  return Object.fromEntries(
    results.flatMap((r, i) => (r.data ? [[siteIds[i], r.data]] : [])),
  ) as Record<string, HorizonMask>
}
