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
import { useCallback, useEffect, useMemo } from 'react'
import {
  keepPreviousData,
  useQueries,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from '@tanstack/react-query'
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

/**
 * Bumped by the backend; read from the site list and folded into every key.
 *
 * `App` renders no screen until the site list has loaded, so every window
 * query is keyed with the real version from its first render. A redeploy
 * mid-session is caught by `useEngineVersionWatch`, which resets the cache
 * rather than leaving geometry from the old engine on screen.
 */
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

/**
 * Every cache key in one place, so "is the engine version in the key?" is a
 * question with one answer rather than nine.
 *
 * `sites` is the exception and deliberately so: the site list is what *reports*
 * the engine version, so keying it on the version it has not yet delivered
 * would be circular. `useEngineVersionWatch` resets it along with everything
 * else when the version changes.
 */
export const keys = {
  sites: (filters: SiteFilters) => ['sites', filters] as const,
  site: (siteId: string | undefined) => ['site', engineVersion, siteId] as const,
  horizon: (siteId: string | undefined) => ['horizon', engineVersion, siteId] as const,
  windows: (siteId: string | undefined, w: WindowParams) =>
    ['windows', engineVersion, siteId, ...windowKey(w)] as const,
  metrics: (siteId: string | undefined, w: WindowParams) =>
    ['metrics', engineVersion, siteId, ...windowKey(w)] as const,
  timeline: (siteId: string | undefined, w: WindowParams) =>
    ['timeline', engineVersion, siteId, ...windowKey(w)] as const,
  compare: (siteIds: string[], w: WindowParams, rankBy: string) =>
    ['compare', engineVersion, [...siteIds].sort(), ...windowKey(w), rankBy] as const,
  health: () => ['health'] as const,
}

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
    queryKey: keys.sites(filters),
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
    queryKey: keys.site(siteId),
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
    queryKey: keys.horizon(siteId),
    enabled: Boolean(siteId),
    staleTime: Infinity,
    gcTime: Infinity,
    queryFn: async ({ signal }) => adaptHorizon(await api.horizon(siteId as string, 1, signal)),
  })
}

// ---------------------------------------------------------------------------
// The window endpoints
// ---------------------------------------------------------------------------
//
// Every window-dependent query keeps the previous window's data while the next
// one loads (ADR-2, design hand-off section 7): the numbers stay on screen and
// then roll to the new values (M4) instead of flashing to a skeleton.

const windowQuery = (w: WindowParams) => ({ start: w.start, end: w.end, step_s: w.stepS })

export function useWindows(siteId: string | undefined, w: WindowParams) {
  return useQuery({
    queryKey: keys.windows(siteId, w),
    enabled: Boolean(siteId),
    staleTime: FIVE_MIN,
    placeholderData: keepPreviousData,
    queryFn: ({ signal }) => api.windows(siteId as string, windowQuery(w), signal),
  })
}

export function useMetrics(siteId: string | undefined, w: WindowParams) {
  return useQuery({
    queryKey: keys.metrics(siteId, w),
    enabled: Boolean(siteId),
    staleTime: FIVE_MIN,
    placeholderData: keepPreviousData,
    queryFn: ({ signal }) => api.metrics(siteId as string, windowQuery(w), signal),
  })
}

export function useTimeline(siteId: string | undefined, w: WindowParams, enabled = true) {
  return useQuery({
    queryKey: keys.timeline(siteId, w),
    enabled: Boolean(siteId) && enabled,
    staleTime: FIVE_MIN,
    placeholderData: keepPreviousData,
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
 *
 * The adapted object is memoised on the query data, so a re-render that does
 * not change the data (every frame of M1, for instance) does not rebuild
 * thousands of samples.
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

  const tl = withTimeline ? (timeline.data as TimelineDTO | undefined) : undefined
  const data = useMemo(
    () =>
      windows.data && metrics.data && horizon.data
        ? adaptSite(
            siteId as string,
            windows.data as WindowsDTO,
            metrics.data as MetricsDTO,
            horizon.data as HorizonMask,
            tl,
          )
        : undefined,
    [siteId, windows.data, metrics.data, horizon.data, tl],
  )

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
export interface ManySiteMetrics {
  byId: Record<string, MetricsDTO>
  done: number
  total: number
  isPending: boolean
  error: unknown
}

export function useManySiteMetrics(siteIds: string[], w: WindowParams): ManySiteMetrics {
  // `combine` keeps the result referentially stable while the data is
  // unchanged. Rebuilding `byId` on every render -- the previous shape --
  // invalidated every memo downstream, so the map screen re-adapted fifteen
  // sites on every animation frame of the date slider.
  const combine = useCallback(
    (results: UseQueryResult<unknown>[]): ManySiteMetrics => ({
      byId: Object.fromEntries(
        results.flatMap((r, i) => (r.data ? [[siteIds[i], r.data as MetricsDTO]] : [])),
      ) as Record<string, MetricsDTO>,
      done: results.filter((r) => r.isSuccess).length,
      total: siteIds.length,
      isPending: results.some((r) => r.isPending),
      error: results.find((r) => r.error)?.error,
    }),
    [siteIds],
  )
  return useQueries({
    queries: siteIds.map((id) => ({
      queryKey: keys.metrics(id, w),
      staleTime: FIVE_MIN,
      placeholderData: keepPreviousData,
      queryFn: ({ signal }: { signal: AbortSignal }) => api.metrics(id, windowQuery(w), signal),
    })),
    combine,
  })
}

// ---------------------------------------------------------------------------
// Compare
// ---------------------------------------------------------------------------

/**
 * The server's ranking, ties included.
 *
 * `placeholderData` matters more here than anywhere: changing the ranking
 * metric changes the key, and without the previous order held on screen the
 * columns would fall back to their unranked positions before sliding to the
 * new ones -- two moves (M3) where the design has one.
 */
export function useCompare(siteIds: string[], w: WindowParams, rankBy: string) {
  return useQuery({
    queryKey: keys.compare(siteIds, w, rankBy),
    enabled: siteIds.length >= 2,
    staleTime: FIVE_MIN,
    placeholderData: keepPreviousData,
    queryFn: ({ signal }): Promise<CompareDTO> =>
      api.compare(
        { site_ids: siteIds, start: w.start, end: w.end, step_s: w.stepS, rank_by: rankBy },
        signal,
      ),
  })
}

// ---------------------------------------------------------------------------
// Health — drives the provenance badge and the engine-version watch
// ---------------------------------------------------------------------------

export function useHealth() {
  return useQuery({
    queryKey: keys.health(),
    staleTime: 30_000,
    refetchInterval: 60_000,
    retry: false,
    queryFn: ({ signal }) => api.health(signal),
  })
}

/**
 * Drop every cached answer when the backend's engine version changes.
 *
 * Keys carry the version, but a key is only rebuilt when a component
 * re-renders; without this, a screen that stays mounted across a redeploy
 * keeps showing numbers from the previous engine -- the worst failure here,
 * because nothing looks wrong.
 */
export function useEngineVersionWatch(): void {
  const client = useQueryClient()
  const live = useHealth().data?.engine_version
  useEffect(() => {
    if (!live || getEngineVersion() === 'unknown' || live === getEngineVersion()) return
    setEngineVersion(live)
    void client.resetQueries({ predicate: (q) => q.queryKey[0] !== 'health' })
  }, [live, client])
}
