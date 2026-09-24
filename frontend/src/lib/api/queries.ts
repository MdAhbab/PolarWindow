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
import { useCallback, useEffect, useMemo, useRef } from 'react'
import {
  keepPreviousData,
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from '@tanstack/react-query'
import {
  ApiError,
  api,
  type AgentDTO,
  type CompareDTO,
  type MetricsDTO,
  type Schemas,
  type TimelineDTO,
  type WindowsDTO,
} from './client'
import {
  adaptCalendar,
  adaptHorizon,
  adaptMeta,
  adaptMission,
  adaptMissionDetail,
  adaptSite,
  adaptSiteBrief,
  type AdaptedSite,
  type AdaptedSiteBrief,
  type InstrumentType,
  type Meta,
  type Mission,
  type MissionStatus,
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

/**
 * Each mission record's `data_version` (a hash of its row in `missions.json`),
 * as last reported by the list. Folded into the mission-detail key, so a record
 * that changed server-side is fetched again rather than served from the client
 * cache: the engine version does not move when only mission facts change.
 */
const missionVersions = new Map<string, string>()
export const setMissionVersions = (items: { id: string; dataVersion: string }[]) => {
  for (const m of items) missionVersions.set(m.id, m.dataVersion)
}
export const resetMissionVersions = () => missionVersions.clear()

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
  missions: (filters: MissionFilters) =>
    ['missions', engineVersion, normaliseMissionFilters(filters)] as const,
  mission: (missionId: string | undefined) =>
    ['mission', engineVersion, missionId, (missionId && missionVersions.get(missionId)) || null] as const,
  calendar: (siteId: string | undefined, span: CalendarSpan | undefined, bucket: CalendarBucketSize) =>
    ['calendar', engineVersion, siteId, span?.start, span?.end, bucket] as const,
  agentRuns: () => ['agentRuns'] as const,
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
  /** `all` so mission targets resolve by id; the Map narrows to candidates itself. */
  kind?: 'candidate' | 'mission_target' | 'all'
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
          kind: filters.kind,
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
  /** Retry every part of the view; the ErrorPanel's Retry calls this. */
  refetch: () => void
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

  const { refetch: rw } = windows
  const { refetch: rm } = metrics
  const { refetch: rh } = horizon
  const { refetch: rt } = timeline
  const refetch = useCallback(() => {
    void rw()
    void rm()
    void rh()
    if (withTimeline) void rt()
  }, [rw, rm, rh, rt, withTimeline])

  return {
    data,
    meta: data?.meta,
    isPending: windows.isPending || metrics.isPending || horizon.isPending,
    isFetching:
      windows.isFetching || metrics.isFetching || horizon.isFetching || timeline.isFetching,
    error: windows.error ?? metrics.error ?? horizon.error ?? timeline.error,
    refetch,
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
// Missions (contract v2)
// ---------------------------------------------------------------------------

export interface MissionFilters {
  /** Any of these statuses. */
  status?: MissionStatus[]
  /** Missions carrying at least one payload of any of these types. */
  payloadType?: InstrumentType[]
  provider?: string
  region?: string
  from?: string
  to?: string
  q?: string
}

/**
 * One canonical form per filter set: arrays sorted and de-duplicated, empty
 * values dropped, keys in a fixed order. Selecting Volatiles then Imaging and
 * Imaging then Volatiles is one query, not two.
 */
export function normaliseMissionFilters(f: MissionFilters): MissionFilters {
  const out: MissionFilters = {}
  const list = <T extends string>(v: T[] | undefined) =>
    v && v.length ? [...new Set(v)].sort() : undefined
  const text = (v: string | undefined) => (v && v.trim() ? v.trim() : undefined)
  const status = list(f.status)
  const payloadType = list(f.payloadType)
  if (status) out.status = status
  if (payloadType) out.payloadType = payloadType
  if (text(f.provider)) out.provider = text(f.provider)
  if (text(f.region)) out.region = text(f.region)
  if (text(f.from)) out.from = text(f.from)
  if (text(f.to)) out.to = text(f.to)
  if (text(f.q)) out.q = text(f.q)
  return out
}

export interface MissionList {
  items: Mission[]
  total: number
  meta: Meta
}

export function useMissions(filters: MissionFilters = {}) {
  const f = normaliseMissionFilters(filters)
  return useQuery({
    queryKey: keys.missions(f),
    staleTime: FIVE_MIN,
    // A chip toggle keeps the previous list on screen until the next arrives,
    // so the list and the count never flash empty between two real answers.
    placeholderData: keepPreviousData,
    queryFn: async ({ signal }): Promise<MissionList> => {
      const dto = await api.missions(
        {
          status: f.status,
          payload_type: f.payloadType,
          provider: f.provider,
          region: f.region,
          from: f.from,
          to: f.to,
          q: f.q,
        },
        signal,
      )
      const items = dto.items.map(adaptMission)
      setMissionVersions(items)
      return { items, total: dto.total, meta: adaptMeta(dto.meta) }
    },
  })
}

export function useMission(missionId: string | undefined) {
  return useQuery({
    queryKey: keys.mission(missionId),
    enabled: Boolean(missionId),
    staleTime: FIVE_MIN,
    // A 404 is an answer ("that mission isn't in the list"), not a blip.
    retry: (count, err) => !(err instanceof ApiError && err.status === 404) && count < 1,
    queryFn: async ({ signal }) => adaptMissionDetail(await api.mission(missionId as string, signal)),
  })
}

// ---------------------------------------------------------------------------
// Calendar (contract v2): the month strip under the window picker
// ---------------------------------------------------------------------------

export interface CalendarSpan {
  start: string
  end: string
}
export type CalendarBucketSize = 'day' | 'month'

export function useCalendar(
  siteId: string | undefined,
  span: CalendarSpan | undefined,
  bucket: CalendarBucketSize = 'month',
) {
  return useQuery({
    queryKey: keys.calendar(siteId, span, bucket),
    enabled: Boolean(siteId && span),
    staleTime: FIVE_MIN,
    placeholderData: keepPreviousData,
    queryFn: async ({ signal }) =>
      adaptCalendar(
        await api.calendar(
          siteId as string,
          { start: span?.start, end: span?.end, bucket },
          signal,
        ),
      ),
  })
}

// ---------------------------------------------------------------------------
// Agents (contract v2): Explain, Advise, Brief, Ask, and the run log
// ---------------------------------------------------------------------------

export type AgentKind = 'explain' | 'advise' | 'brief' | 'ask'

export interface AgentRequests {
  explain: Schemas['ExplainRequest']
  advise: Schemas['AdviseRequest']
  brief: Schemas['BriefRequest']
  ask: Schemas['AskRequest']
}

/**
 * One agent call, cancellable.
 *
 * A mutation, not a query: every call is a new run with its own log entry,
 * and caching an answer by its question would hide that. `cancel` aborts the
 * request through its signal and returns the card to idle; the run log is
 * refreshed whenever a call settles, so "How the AI got this" always has the
 * run it is asked to show.
 */
export function useAgent<K extends AgentKind>(kind: K, scope?: readonly unknown[]) {
  const client = useQueryClient()
  const ctrl = useRef<AbortController | null>(null)
  const mutation = useMutation({
    mutationKey: ['agent', kind, ...(scope ?? [])],
    mutationFn: (body: AgentRequests[K]): Promise<AgentDTO> => {
      ctrl.current?.abort()
      const c = new AbortController()
      ctrl.current = c
      const call = api[kind] as (b: AgentRequests[K], s?: AbortSignal) => Promise<AgentDTO>
      return call(body, c.signal)
    },
    retry: false,
    onSettled: () => client.invalidateQueries({ queryKey: keys.agentRuns() }),
  })
  const { reset } = mutation
  const cancel = useCallback(() => {
    ctrl.current?.abort()
    ctrl.current = null
    reset()
  }, [reset])
  useEffect(() => () => ctrl.current?.abort(), [])
  return { ...mutation, cancel }
}

export function useAgentRuns(enabled = true) {
  return useQuery({
    queryKey: keys.agentRuns(),
    enabled,
    staleTime: 0,
    queryFn: ({ signal }) => api.agentRuns(50, signal),
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
