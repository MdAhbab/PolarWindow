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
import { DATA_MODE, SnapshotMiss, fromSnapshot, isSnapshotActive, markLive, snapshotTileUrl } from './snapshot'
import { currentToken, renewToken } from '../session'
import type {
  AuditEntryDTO,
  ContactDTO,
  FeedsDTO,
  JobRefDTO,
  LandingHistoryDTO,
  LaunchCalendarDTO,
  LaunchWeatherDTO,
  LessonDTO,
  ParameterDTO,
  PartDTO,
  PartImpactDTO,
  ReadyDTO,
  ReadyItemDTO,
  ReturnDTO,
  RiskDTO,
  RiskScalesDTO,
  RoverSightDTO,
  SectionDTO,
  StoredForecastDTO,
  SectionStatusDTO,
  TripDTO,
  UserDTO,
} from './lifecycle'

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
export type SettingsDTO = Schemas['SettingsOut']
export type ModelStateDTO = Schemas['ModelState']
export type ClearedDTO = Schemas['Cleared']

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
  /** The server sent its own problem detail (a title and what still works), not a bare status. */
  readonly problem: boolean

  constructor(status: number, body: unknown) {
    const raw = (body as { detail?: unknown })?.detail
    const p = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
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
    this.problem = typeof p.title === 'string'
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
            'Nothing has been calculated incorrectly. There is simply nothing to calculate with. The interface, the terrain map and anything already on screen are unaffected.',
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

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

/** The calls the server checks a session on: the AI panels (they cost quota) and the settings. */
const SESSION_PATHS = /^\/(agents\/(explain|advise|brief|ask)$|settings|auth\/me)/

/**
 * The project manager's writes (ADR-17): each needs a named session. Reads of
 * the same paths stay public, so the token goes only on a write.
 */
const WRITE_PATHS =
  /^\/(missions\/[^/]+\/(ready\/items|parts|risks|lessons\/[^/]+\/adopt|launch\/official-forecast|contact\/bookings|return\/limits)|ready\/items\/|parts\/|risks\/|vehicles\/[^/]+\/limits|feeds\/[^/]+\/refresh|parameters\/)/

interface RequestOptions {
  signal?: AbortSignal
  query?: Query
  body?: unknown
  method?: Method
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  return (await requestWithStatus<T>(path, opts)).body
}

/**
 * The answer and its HTTP status. A lifecycle section answers 202 with a job
 * while it is being worked out, and the caller needs to tell that apart from
 * the answer itself.
 */
async function requestWithStatus<T>(
  path: string,
  { signal, query, body, method: asked }: RequestOptions = {},
): Promise<{ status: number; body: T }> {
  const method: Method = asked ?? (body ? 'POST' : 'GET')
  const pathAndQuery = `${path}${qs(query)}`
  // A snapshot build never calls the network: the saved answers are the data.
  if (DATA_MODE === 'snapshot') return fromSaved<T>(method, pathAndQuery, body)

  // Only the calls that need a session carry it. Reading is public, and an
  // Authorization header on a read would make the browser ask permission
  // (a CORS preflight) before every slider step.
  const needsSession = SESSION_PATHS.test(path) || (method !== 'GET' && WRITE_PATHS.test(path))
  const send = (token: string | null) => {
    const headers: Record<string, string> = {}
    if (body) headers['content-type'] = 'application/json'
    if (token && needsSession) headers.authorization = `Bearer ${token}`
    return fetch(`${API_BASE}${pathAndQuery}`, {
      signal,
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    })
  }

  let res: Response
  try {
    const token = currentToken()
    res = await send(token)
    // The server no longer accepts this session (it restarted with a new
    // secret, or the session ended). Sign in again once, then retry once.
    if (res.status === 401 && needsSession) {
      const fresh = await renewToken()
      if (fresh) res = await send(fresh)
    }
  } catch (cause) {
    // An abort is the caller superseding itself, not a failure. Rethrow it so
    // TanStack Query drops the result quietly instead of showing an error.
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
    // The service is unreachable: answer from the offline copy where it has
    // this request, and say so in the badge; otherwise the error stands.
    try {
      return await fromSaved<T>(method, pathAndQuery, body)
    } catch (miss) {
      if (miss instanceof SnapshotMiss) throw new ApiUnreachable(cause)
      throw miss
    }
  }
  markLive()
  if (!res.ok) {
    let parsed: unknown = null
    try {
      parsed = await res.json()
    } catch {
      /* a non-JSON error body is still an error; the defaults cover it */
    }
    throw new ApiError(res.status, parsed)
  }
  return { status: res.status, body: (res.status === 204 ? null : await res.json()) as T }
}

/** A saved answer, returned exactly as received; a saved error is still an error. */
async function fromSaved<T>(method: Method, pathAndQuery: string, body: unknown): Promise<{ status: number; body: T }> {
  let saved: { status: number; json: unknown }
  try {
    saved = await fromSnapshot(method, pathAndQuery, body)
  } catch (e) {
    if (e instanceof SnapshotMiss && DATA_MODE === 'snapshot') throw new NotInSnapshot()
    throw e
  }
  if (saved.status >= 400) throw new ApiError(saved.status, saved.json)
  return { status: saved.status, body: saved.json as T }
}

/** A view the offline copy does not hold. Says what does work, like any error here. */
export class NotInSnapshot extends ApiError {
  constructor() {
    super(404, {
      detail: {
        title: 'Not in this offline copy',
        detail: 'This build carries saved answers from the live service, and this view was not among them.',
        ui: {
          still_works:
            'The demo path is saved: every mission and its page, the sites and dates they open, Compare and the AI log. Other dates and sites need the live service.',
          retryable: false,
        },
      },
    })
    this.name = 'NotInSnapshot'
  }
}

const enc = encodeURIComponent

/** A section's answer, or the job working it out (202, ADR-12). */
export type SectionResult<T> = { kind: 'answer'; section: SectionDTO<T> } | { kind: 'job'; job: JobRefDTO }

async function section<T>(path: string, query: Query | undefined, signal?: AbortSignal): Promise<SectionResult<T>> {
  const r = await requestWithStatus<SectionDTO<T> | JobRefDTO>(path, { query, signal })
  if (r.status === 202) return { kind: 'job', job: r.body as JobRefDTO }
  return { kind: 'answer', section: fillQuantities(r.body) as SectionDTO<T> }
}

const QUANTITY_DEFAULTS = {
  pm: null,
  lo: null,
  hi: null,
  factor: null,
  open: false,
  no_margin_reason: null,
  missing_reason: null,
  source: null,
}

/**
 * Every Quantity with all its fields. The API sends a field with a default
 * even when empty, but the schema marks it optional; filling any that are
 * left out here means "no margin" is always `null`, never `undefined`, in
 * every check a screen makes.
 */
export function fillQuantities<T>(x: T): T {
  if (Array.isArray(x)) return x.map(fillQuantities) as T
  if (x && typeof x === 'object') {
    const o = x as Record<string, unknown>
    const out: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(o)) out[k] = fillQuantities(v)
    if ('provenance' in o && 'unit' in o && 'value' in o) return { ...QUANTITY_DEFAULTS, ...out } as T
    return out as T
  }
  return x
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

  settings: (signal?: AbortSignal) => request<SettingsDTO>('/settings', { signal }),

  saveAi: (body: Schemas['AiSettingsIn']) => request<SettingsDTO>('/settings/ai', { body, method: 'PUT' }),

  resetAi: () => request<SettingsDTO>('/settings/ai/reset', { method: 'POST' }),

  retryModels: () => request<SettingsDTO>('/settings/ai/retry', { method: 'POST' }),

  clearRunLog: () => request<ClearedDTO>('/settings/agent-runs', { method: 'DELETE' }),

  clearCache: () => request<ClearedDTO>('/settings/cache', { method: 'DELETE' }),

  agentRuns: (limit = 50, signal?: AbortSignal) =>
    request<AgentRunListDTO>('/agents/runs', { query: { limit }, signal }),

  // -- the lifecycle sections (docs/lifecycle-api.md) ------------------------

  sections: (missionId: string, signal?: AbortSignal) =>
    request<SectionDTO<SectionStatusDTO[]>>(`/missions/${enc(missionId)}/sections`, { signal }),

  ready: (missionId: string, signal?: AbortSignal) =>
    section<ReadyDTO>(`/missions/${enc(missionId)}/ready`, undefined, signal),

  launch: (missionId: string, q: Query, signal?: AbortSignal) =>
    section<LaunchCalendarDTO>(`/missions/${enc(missionId)}/launch`, q, signal),

  launchWeather: (missionId: string, opportunity: string, signal?: AbortSignal) =>
    section<LaunchWeatherDTO>(`/missions/${enc(missionId)}/launch/weather`, { opportunity }, signal),

  trip: (missionId: string, signal?: AbortSignal) => section<TripDTO>(`/missions/${enc(missionId)}/trip`, undefined, signal),

  contact: (missionId: string, q: Query, signal?: AbortSignal) =>
    section<ContactDTO>(`/missions/${enc(missionId)}/contact`, q, signal),

  rover: (missionId: string, rover: string | undefined, signal?: AbortSignal) =>
    request<SectionDTO<RoverSightDTO>>(`/missions/${enc(missionId)}/contact/rover`, { query: { rover }, signal }),

  returnSection: (missionId: string, signal?: AbortSignal) =>
    section<ReturnDTO>(`/missions/${enc(missionId)}/return`, undefined, signal),

  job: (jobId: number, signal?: AbortSignal) => request<JobRefDTO>(`/jobs/${jobId}`, { signal }),

  parts: (missionId: string, signal?: AbortSignal) =>
    request<{ parts: PartDTO[] }>(`/missions/${enc(missionId)}/parts`, { signal }),

  partImpact: (partId: string, signal?: AbortSignal) =>
    request<PartImpactDTO>(`/parts/${enc(partId)}/impact`, { signal }),

  riskScales: (signal?: AbortSignal) => request<RiskScalesDTO>('/risk-scales', { signal }),

  landingHistory: (signal?: AbortSignal) => request<LandingHistoryDTO>('/landing-history', { signal }),

  lessons: async (missionId: string, signal?: AbortSignal): Promise<LessonDTO[]> => {
    const r = await request<LessonDTO[] | { lessons: LessonDTO[] }>('/lessons', { query: { mission: missionId }, signal })
    return Array.isArray(r) ? r : r.lessons
  },

  itemHistory: (itemId: string, signal?: AbortSignal) =>
    request<AuditEntryDTO[] | { entries: AuditEntryDTO[] }>(`/ready/items/${enc(itemId)}/history`, { signal }),

  history: (entity: string, id: string, signal?: AbortSignal) =>
    request<{ entries: AuditEntryDTO[] }>('/history', { query: { entity, id }, signal }),

  feeds: (signal?: AbortSignal) => request<FeedsDTO>('/feeds', { signal }),

  parameters: async (signal?: AbortSignal) =>
    fillQuantities(await request<{ parameters: ParameterDTO[] }>('/parameters', { signal })),

  me: (signal?: AbortSignal) => request<{ user: UserDTO }>('/auth/me', { signal }),

  // -- the project manager's writes (a named session) ------------------------

  addReadyItem: (missionId: string, body: { kind: string; name: string; organisation: string | null }) =>
    request<ReadyItemDTO>(`/missions/${enc(missionId)}/ready/items`, { body, method: 'POST' }),

  moveReadyItem: (
    itemId: string,
    body: { state: string; date: string; evidence_url: string; note: string | null; blocked_reason?: string | null },
  ) => request<ReadyItemDTO>(`/ready/items/${enc(itemId)}`, { body, method: 'PATCH' }),

  addPart: (missionId: string, body: Omit<PartDTO, 'id' | 'changed_at' | 'changed_by'>) =>
    request<PartDTO>(`/missions/${enc(missionId)}/parts`, { body, method: 'POST' }),

  changePart: (partId: string, body: Partial<Omit<PartDTO, 'id' | 'changed_at' | 'changed_by'>>) =>
    request<PartDTO>(`/parts/${enc(partId)}`, { body, method: 'PATCH' }),

  addRisk: (missionId: string, body: Omit<RiskDTO, 'id'>) =>
    request<RiskDTO>(`/missions/${enc(missionId)}/risks`, { body, method: 'POST' }),

  changeRisk: (riskId: string, body: Partial<Omit<RiskDTO, 'id'>>) =>
    request<RiskDTO>(`/risks/${enc(riskId)}`, { body, method: 'PATCH' }),

  adoptLesson: (missionId: string, lessonId: string) =>
    request<unknown>(`/missions/${enc(missionId)}/lessons/${enc(lessonId)}/adopt`, { method: 'POST' }),

  /** Answers with the forecast as stored (who entered it, and when). */
  officialForecast: (missionId: string, body: { probability_pct: number; concerns: string[]; pdf_url: string }) =>
    request<StoredForecastDTO>(`/missions/${enc(missionId)}/launch/official-forecast`, { body, method: 'PUT' }),

  vehicleLimits: (vehicleId: string, body: { limits: { rule_id: string; value: number; unit: string; note: string | null }[] }) =>
    request<unknown>(`/vehicles/${enc(vehicleId)}/limits`, { body, method: 'PUT' }),

  bookPass: (missionId: string, body: { station: string; start: string; end: string; note?: string | null }) =>
    request<unknown>(`/missions/${enc(missionId)}/contact/bookings`, { body, method: 'POST' }),

  /** Replaces both lists (a part left out is cleared), and answers with the Return section. */
  returnLimits: (
    missionId: string,
    body: {
      booster: { wave_height_m: number | null; wind_m_s: number | null }
      capsule: { wave_height_m: number | null; wind_m_s: number | null }
    },
  ) => request<SectionDTO<ReturnDTO>>(`/missions/${enc(missionId)}/return/limits`, { body, method: 'PUT' }),

  refreshFeed: (provider: string) => request<unknown>(`/feeds/${enc(provider)}/refresh`, { method: 'POST' }),

  /** Answers with every parameter, as `GET /parameters` does; 422 in the server's words when out of range. */
  setParameter: async (id: string, body: { value: number; note: string | null }) =>
    fillQuantities(await request<{ parameters: ParameterDTO[] }>(`/parameters/${enc(id)}`, { body, method: 'PUT' })),

  tileUrl: (layer: 'hillshade' | 'illumination' | 'psr', z: number, x: number, y: number) =>
    isSnapshotActive() ? snapshotTileUrl(layer, z, x, y) : `${API_BASE}/tiles/${layer}/${z}/${x}/${y}.png`,
}
