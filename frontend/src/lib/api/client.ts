/**
 * Thin typed fetch over the POLAR WINDOW API.
 *
 * Types come from `schema.ts`, which is generated from the backend's OpenAPI
 * document (`npm run codegen`). Nothing in this file hand-writes a response
 * shape: if the contract changes, the build breaks here rather than a
 * component rendering `undefined` at a judge.
 *
 * The only hand-written part is error handling, because the server's problem
 * detail carries a `ui` block the ErrorPanel renders directly — so the copy for
 * a failure lives with the code that knows what failed.
 */
import type { components, paths } from './schema'

export type Schemas = components['schemas']
export type SiteListDTO = Schemas['SiteList']
export type SiteBriefDTO = Schemas['SiteBrief']
export type SiteDetailDTO = Schemas['SiteDetail']
export type HorizonDTO = Schemas['HorizonResponse']
export type TimelineDTO = Schemas['TimelineResponse']
export type WindowsDTO = Schemas['WindowsResponse']
export type MetricsDTO = Schemas['MetricsResponse']
export type CompareDTO = Schemas['CompareResponse']
export type AgentDTO = Schemas['AgentResponse']
export type MetaDTO = Schemas['Meta']
export type ArcDTO = Schemas['Arc']
export type CompareItemDTO = Schemas['CompareItem']
export type MissionListDTO = Schemas['MissionList']
export type MissionBriefDTO = Schemas['MissionBrief']
export type MissionDetailDTO = Schemas['MissionDetail']
export type PublishedDateDTO = Schemas['PublishedDate']
export type CalendarDTO = Schemas['CalendarResponse']
export type AgentRunListDTO = Schemas['AgentRunList']
export type AgentRunDTO = Schemas['AgentRunView']
export type ToolCallDTO = Schemas['ToolCallView']
export type ProvenanceItemDTO = Schemas['ProvenanceItem']

export const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? 'http://localhost:8000/api/v1'

/**
 * A failure the UI can render without inventing words for it.
 *
 * `stillWorks` is the field that stops an error from being a shrug: every
 * problem detail the server emits says what is unaffected, so a missing DEM
 * does not read as "everything is broken".
 */
export class ApiError extends Error {
  readonly status: number
  readonly title: string
  readonly detail: string
  readonly stillWorks: string
  readonly retryable: boolean
  readonly action: string | null

  constructor(status: number, body: unknown) {
    const p = (body as { detail?: Record<string, unknown> })?.detail ?? {}
    const ui = (p.ui ?? {}) as Record<string, unknown>
    const title = (p.title as string) ?? 'Something went wrong'
    super(title)
    this.name = 'ApiError'
    this.status = status
    this.title = title
    this.detail = (p.detail as string) ?? 'The request could not be completed.'
    this.stillWorks =
      (ui.still_works as string) ??
      'Other sites and windows are unaffected.'
    this.retryable = Boolean(ui.retryable ?? status >= 500)
    this.action = (ui.action as string) ?? null
  }
}

/** Thrown when the API cannot be reached at all. Distinct from a 4xx/5xx. */
export class ApiUnreachable extends ApiError {
  constructor(cause: unknown) {
    super(0, {
      detail: {
        title: 'Cannot reach the service that does the calculations',
        // The browser's own message ("TypeError: Failed to fetch") says nothing
        // a reader can act on; where the service should be does.
        detail: `Nothing answered at ${serviceHost()}. The service may be stopped, still starting, or blocked by the network.`,
        ui: {
          still_works:
            'Nothing has been calculated incorrectly — there is simply nothing to calculate with. The interface, the terrain map and anything already on screen are unaffected.',
          retryable: true,
          action: 'Check the service is running',
        },
      },
    })
    this.name = 'ApiUnreachable'
    this.cause = cause
  }
}

function serviceHost(): string {
  try {
    return new URL(API_BASE).host
  } catch {
    return API_BASE
  }
}

type Scalar = string | number | boolean
export type Query = Record<string, Scalar | readonly Scalar[] | null | undefined>

/**
 * Query string, with arrays sent as repeated keys (`status=a&status=b`), which
 * is how FastAPI reads a list parameter. Empty values are dropped rather than
 * sent as `key=`, so "no filter" and "filter on the empty string" cannot be
 * confused by the server.
 */
export function qs(params: Query | undefined): string {
  if (!params) return ''
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue
    if (Array.isArray(v)) {
      for (const item of v) if (item !== '') sp.append(k, String(item))
    } else {
      sp.set(k, String(v))
    }
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

async function request<T>(
  path: string,
  { signal, query, body }: { signal?: AbortSignal; query?: Query; body?: unknown } = {},
): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}${qs(query)}`, {
      signal,
      method: body ? 'POST' : 'GET',
      headers: body ? { 'content-type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    })
  } catch (cause) {
    // An abort is the caller superseding itself, not a failure. Rethrow it so
    // TanStack Query drops the result quietly instead of showing an error.
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
    throw new ApiUnreachable(cause)
  }
  if (!res.ok) {
    let parsed: unknown = null
    try {
      parsed = await res.json()
    } catch {
      /* a non-JSON error body is still an error; the defaults cover it */
    }
    throw new ApiError(res.status, parsed)
  }
  return (await res.json()) as T
}

/** ISO 8601 UTC, which is what every endpoint takes. */
export function iso(d: Date): string {
  return d.toISOString().replace(/\.\d{3}Z$/, 'Z')
}

export const api = {
  health: (signal?: AbortSignal) =>
    request<paths['/api/v1/healthz']['get']['responses'][200]['content']['application/json']>(
      '/healthz',
      { signal },
    ),

  sites: (query: Query = {}, signal?: AbortSignal) =>
    request<SiteListDTO>('/sites', { query, signal }),

  site: (id: string, signal?: AbortSignal) => request<SiteDetailDTO>(`/sites/${id}`, { signal }),

  horizon: (id: string, stepDeg = 1, signal?: AbortSignal) =>
    request<HorizonDTO>(`/sites/${id}/horizon`, { query: { step_deg: stepDeg }, signal }),

  timeline: (id: string, q: Query, signal?: AbortSignal) =>
    request<TimelineDTO>(`/sites/${id}/timeline`, { query: q, signal }),

  windows: (id: string, q: Query, signal?: AbortSignal) =>
    request<WindowsDTO>(`/sites/${id}/windows`, { query: q, signal }),

  metrics: (id: string, q: Query, signal?: AbortSignal) =>
    request<MetricsDTO>(`/sites/${id}/metrics`, { query: q, signal }),

  compare: (body: Schemas['CompareRequest'], signal?: AbortSignal) =>
    request<CompareDTO>('/compare', { body, signal }),

  calendar: (id: string, q: Query, signal?: AbortSignal) =>
    request<CalendarDTO>(`/sites/${id}/calendar`, { query: q, signal }),

  missions: (query: Query = {}, signal?: AbortSignal) =>
    request<MissionListDTO>('/missions', { query, signal }),

  mission: (id: string, signal?: AbortSignal) =>
    request<MissionDetailDTO>(`/missions/${encodeURIComponent(id)}`, { signal }),

  explain: (body: Schemas['ExplainRequest'], signal?: AbortSignal) =>
    request<AgentDTO>('/agents/explain', { body, signal }),

  advise: (body: Schemas['AdviseRequest'], signal?: AbortSignal) =>
    request<AgentDTO>('/agents/advise', { body, signal }),

  brief: (body: Schemas['BriefRequest'], signal?: AbortSignal) =>
    request<AgentDTO>('/agents/brief', { body, signal }),

  ask: (body: Schemas['AskRequest'], signal?: AbortSignal) =>
    request<AgentDTO>('/agents/ask', { body, signal }),

  agentRuns: (limit = 50, signal?: AbortSignal) =>
    request<AgentRunListDTO>('/agents/runs', { query: { limit }, signal }),

  tileUrl: (layer: 'hillshade' | 'illumination' | 'psr', z: number, x: number, y: number) =>
    `${API_BASE}/tiles/${layer}/${z}/${x}/${y}.png`,
}
