/**
 * TanStack Query hooks. The server-state half of the split from ADR-2:
 *
 *   zustand owns what the user chose.   TanStack owns what the server said.
 *
 * Nothing derived from the server is ever `set()` into zustand. That rule is
 * the whole reason two state systems are tolerable in one app.
 *
 * Every key carries `engine_version`. Without it a backend redeploy keeps
 * serving the previous geometry out of the client cache — the worst failure
 * available here, because nothing looks wrong.
 */
import { useQueries, useQuery, type UseQueryResult } from '@tanstack/react-query'
import { api, type CompareDTO, type MetricsDTO, type TimelineDTO, type WindowsDTO } from './client'
import {
  adaptHorizon,
  adaptMeta,
  adaptSite,
  adaptSiteBrief,
  type AdaptedSite,
  type AdaptedSiteBrief,
  type Meta,
} from './adapters'
import type { HorizonMask } from '../types'

/** Bumped by the backend; read from any response and folded into every key. */
let engineVersion = 'unknown'
export const setEngineVersion = (v: string) => {
  engineVersion = v
}
export const getEngineVersion = () => engineVersion

const FIVE_MIN = 5 * 60 * 1000

export interface WindowParams {
  start: string
  end: string
  stepS: number
}

const windowKey = (w: WindowParams) => [w.start, w.end, w.stepS] as const

// ---------------------------------------------------------------------------
// Sites
// ---------------------------------------------------------------------------

export interface SiteFilters {
  q?: string
  region?: string
  latMin?: number
  latMax?: number
  minSunFraction?: number
  maxLongestDarkS?: number
}

export function useSites(filters: SiteFilters = {}) {
  return useQuery({
    queryKey: ['sites', engineVersion, filters],
    staleTime: FIVE_MIN,
    queryFn: async ({ signal }) => {
      const dto = await api.sites(
        {
          q: filters.q,
          region: filters.region,
          lat_min: filters.latMin,
          lat_max: filters.latMax,
          min_sun_fraction: filters.minSunFraction,
          max_longest_dark_s: filters.maxLongestDarkS,
          limit: 100,
        },
        signal,
      )
      setEngineVersion(dto.meta.engine_version)
      return {
        items: dto.items.map(adaptSiteBrief) as AdaptedSiteBrief[],
        total: dto.total,
        meta: adaptMeta(dto.meta),
      }
    },
  })
}

export function useSiteDetail(siteId: string | undefined) {
  return useQuery({
    queryKey: ['site', engineVersion, siteId],
    enabled: Boolean(siteId),
    staleTime: FIVE_MIN,
    queryFn: ({ signal }) => api.site(siteId as string, signal),
  })
}

// ---------------------------------------------------------------------------
// Horizon — fetched once per session and never again
// ---------------------------------------------------------------------------

/**
 * A mask is immutable for an engine version, and both `HorizonProfile` and
 * `PolarMap` want it. `staleTime: Infinity` is the single biggest
 * request-count win available in this app.
 */
export function useHorizon(siteId: string | undefined): UseQueryResult<HorizonMask> {
  return useQuery({
    queryKey: ['horizon', engineVersion, siteId],
    enabled: Boolean(siteId),
    staleTime: Infinity,
    gcTime: Infinity,
    queryFn: async ({ signal }) => adaptHorizon(await api.horizon(siteId as string, 1, signal)),
  })
}

// ---------------------------------------------------------------------------
// The window endpoints
// ---------------------------------------------------------------------------

const windowQuery = (w: WindowParams) => ({ start: w.start, end: w.end, step_s: w.stepS })

export function useWindows(siteId: string | undefined, w: WindowParams) {
  return useQuery({
    queryKey: ['windows', engineVersion, siteId, ...windowKey(w)],
    enabled: Boolean(siteId),
    staleTime: FIVE_MIN,
    queryFn: ({ signal }) => api.windows(siteId as string, windowQuery(w), signal),
  })
}

export function useMetrics(siteId: string | undefined, w: WindowParams) {
  return useQuery({
    queryKey: ['metrics', engineVersion, siteId, ...windowKey(w)],
    enabled: Boolean(siteId),
    staleTime: FIVE_MIN,
    queryFn: ({ signal }) => api.metrics(siteId as string, windowQuery(w), signal),
  })
}

export function useTimeline(siteId: string | undefined, w: WindowParams, enabled = true) {
  return useQuery({
    queryKey: ['timeline', engineVersion, siteId, ...windowKey(w)],
    enabled: Boolean(siteId) && enabled,
    staleTime: FIVE_MIN,
    queryFn: ({ signal }) => api.timeline(siteId as string, windowQuery(w), signal),
  })
}

// ---------------------------------------------------------------------------
// The composed view a screen actually wants
// ---------------------------------------------------------------------------

export interface SiteView {
  data: AdaptedSite | undefined
  meta: Meta | undefined
  isPending: boolean
  isFetching: boolean
  error: unknown
}

/**
 * One site, assembled from the three endpoints that carry its parts.
 *
 * `withTimeline` is false for every site except the focused one — exactly as
 * the old Worker only sent per-sample tracks for the site on screen. 2,835
 * samples times two bodies times seven sites is 1.5 MB nobody looks at.
 */
export function useSiteView(
  siteId: string | undefined,
  w: WindowParams,
  withTimeline = false,
): SiteView {
  const windows = useWindows(siteId, w)
  const metrics = useMetrics(siteId, w)
  const horizon = useHorizon(siteId)
  const timeline = useTimeline(siteId, w, withTimeline)

  const ready = windows.data && metrics.data && horizon.data
  const data = ready
    ? adaptSite(
        siteId as string,
        windows.data as WindowsDTO,
        metrics.data as MetricsDTO,
        horizon.data as HorizonMask,
        withTimeline ? (timeline.data as TimelineDTO | undefined) : undefined,
      )
    : undefined

  return {
    data,
    meta: data?.meta,
    isPending: windows.isPending || metrics.isPending || horizon.isPending,
    isFetching:
      windows.isFetching || metrics.isFetching || horizon.isFetching || timeline.isFetching,
    error: windows.error ?? metrics.error ?? horizon.error ?? timeline.error,
  }
}

/**
 * Several sites at once, resolving independently.
 *
 * `useQueries` over a dynamic array is why ADR-2 chose TanStack over SWR: the
 * existing `LoadingPanel` shows sites as they arrive, and collapsing them into
 * one aggregate request would delete a piece of UX that already works.
 */
export function useManySiteMetrics(siteIds: string[], w: WindowParams) {
  const results = useQueries({
    queries: siteIds.map((id) => ({
      queryKey: ['metrics', engineVersion, id, ...windowKey(w)],
      staleTime: FIVE_MIN,
      queryFn: ({ signal }: { signal: AbortSignal }) => api.metrics(id, windowQuery(w), signal),
    })),
  })
  const done = results.filter((r) => r.isSuccess).length
  return {
    results,
    byId: Object.fromEntries(
      results.flatMap((r, i) => (r.data ? [[siteIds[i], r.data as MetricsDTO]] : [])),
    ) as Record<string, MetricsDTO>,
    done,
    total: siteIds.length,
    isPending: results.some((r) => r.isPending),
    error: results.find((r) => r.error)?.error,
  }
}

// ---------------------------------------------------------------------------
// Compare
// ---------------------------------------------------------------------------

export function useCompare(siteIds: string[], w: WindowParams, rankBy: string) {
  return useQuery({
    queryKey: ['compare', engineVersion, [...siteIds].sort(), ...windowKey(w), rankBy],
    enabled: siteIds.length >= 2,
    staleTime: FIVE_MIN,
    queryFn: ({ signal }): Promise<CompareDTO> =>
      api.compare(
        { site_ids: siteIds, start: w.start, end: w.end, step_s: w.stepS, rank_by: rankBy },
        signal,
      ),
  })
}

// ---------------------------------------------------------------------------
// Health — drives the SAMPLE DATA badge and the kernel warning
// ---------------------------------------------------------------------------

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    staleTime: 30_000,
    refetchInterval: 60_000,
    retry: false,
    queryFn: ({ signal }) => api.health(signal),
  })
}
