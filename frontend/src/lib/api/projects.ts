/**
 * The projects calls (docs/experience-plan.md, "Projects"): the form's choices,
 * the team's projects, saving and deleting one, and reading a file into the form.
 *
 * Written against `experience.types.ts`. Writes and the file reading need a
 * named session (ADR-17); the choices and the list are public. Nothing here
 * works from the offline copy: adding a project needs the live service.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { API_BASE, ApiError, ApiUnreachable, api } from './client'
import { DATA_MODE } from './snapshot'
import { currentToken, renewToken } from '../session'
import type {
  IntakeDTO,
  ProjectDeletedDTO,
  ProjectIn,
  ProjectListDTO,
  ProjectOptionsDTO,
  ProjectSavedDTO,
} from './experience.types'
import type { RadioFigures } from '../../components/project/formModel'

/** True in a build that has no service to talk to. */
export const PROJECTS_OFFLINE = DATA_MODE === 'snapshot'

/**
 * A refusal that names the fields it is about. The server's problem detail may
 * carry `errors: [{ field, message }]` (or FastAPI's `loc` and `msg`); each is
 * kept by its dotted path so the form can show it beside the field.
 */
export class ProjectApiError extends ApiError {
  readonly fields: Record<string, string>
  constructor(status: number, body: unknown) {
    super(status, body)
    this.name = 'ProjectApiError'
    this.fields = fieldErrorsOf(body)
  }
}

function fieldErrorsOf(body: unknown): Record<string, string> {
  const out: Record<string, string> = {}
  const raw = (body as { detail?: unknown } | null)?.detail
  const list: unknown[] = Array.isArray(raw)
    ? raw
    : Array.isArray((raw as { errors?: unknown })?.errors)
      ? ((raw as { errors: unknown[] }).errors)
      : []
  for (const e of list) {
    const x = e as { field?: unknown; loc?: unknown; message?: unknown; msg?: unknown }
    const path =
      typeof x.field === 'string'
        ? x.field
        : Array.isArray(x.loc)
          ? x.loc.filter((p) => p !== 'body' && p !== 'query').join('.')
          : ''
    const msg = typeof x.message === 'string' ? x.message : typeof x.msg === 'string' ? x.msg : ''
    if (path && msg && !(path in out)) out[path] = msg
  }
  return out
}

async function problem(res: Response): Promise<ProjectApiError> {
  let parsed: unknown = null
  try {
    parsed = await res.json()
  } catch {
    /* the defaults say enough */
  }
  return new ProjectApiError(res.status, parsed)
}

async function call<T>(
  method: 'GET' | 'POST' | 'PUT' | 'DELETE',
  path: string,
  { body, signal, session = method !== 'GET' }: { body?: unknown; signal?: AbortSignal; session?: boolean } = {},
): Promise<T> {
  const send = (token: string | null) => {
    const headers: Record<string, string> = {}
    if (body !== undefined) headers['content-type'] = 'application/json'
    if (token && session) headers.authorization = `Bearer ${token}`
    return fetch(`${API_BASE}${path}`, {
      method,
      signal,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  }
  let res: Response
  try {
    res = await send(currentToken())
    if (res.status === 401 && session) {
      const fresh = await renewToken()
      if (fresh) res = await send(fresh)
    }
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
    throw new ApiUnreachable(cause)
  }
  if (!res.ok) throw await problem(res)
  return (await res.json()) as T
}

const enc = encodeURIComponent

export const projectsApi = {
  options: (signal?: AbortSignal) => call<ProjectOptionsDTO>('GET', '/projects/options', { signal }),
  list: (signal?: AbortSignal) => call<ProjectListDTO>('GET', '/projects', { signal }),
  create: (body: ProjectIn) => call<ProjectSavedDTO>('POST', '/projects', { body }),
  update: (id: string, body: ProjectIn) => call<ProjectSavedDTO>('PUT', `/projects/${enc(id)}`, { body }),
  remove: (id: string) => call<ProjectDeletedDTO>('DELETE', `/projects/${enc(id)}`),
}

/** How far a file's upload has got, and what the reader is doing with it. */
export type IntakeStage = 'sending' | 'reading'
export interface IntakeProgress {
  stage: IntakeStage
  /** 0-1 while sending; null once the whole file is with the service. */
  fraction: number | null
}

/**
 * Sends the raw file (the body is its bytes, the Content-Type its own) and
 * answers with the draft and its evidence. An XMLHttpRequest, because that is
 * what reports how much of the file has been sent; fetch does not.
 */
export function postIntake(
  file: File,
  onProgress: (p: IntakeProgress) => void,
  signal?: AbortSignal,
): Promise<IntakeDTO> {
  const attempt = (token: string | null) =>
    new Promise<{ status: number; text: string }>((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', `${API_BASE}/projects/intake?filename=${enc(file.name)}`)
      xhr.setRequestHeader('content-type', file.type || 'application/octet-stream')
      if (token) xhr.setRequestHeader('authorization', `Bearer ${token}`)
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && e.total > 0) onProgress({ stage: 'sending', fraction: e.loaded / e.total })
      }
      xhr.upload.onload = () => onProgress({ stage: 'reading', fraction: null })
      xhr.onerror = () => reject(new ApiUnreachable(new Error('network')))
      xhr.onabort = () => reject(new DOMException('Aborted', 'AbortError'))
      xhr.onload = () => resolve({ status: xhr.status, text: xhr.responseText })
      signal?.addEventListener('abort', () => xhr.abort())
      onProgress({ stage: 'sending', fraction: 0 })
      xhr.send(file)
    })
  return (async () => {
    let r = await attempt(currentToken())
    if (r.status === 401) {
      const fresh = await renewToken()
      if (fresh) r = await attempt(fresh)
    }
    let parsed: unknown = null
    try {
      parsed = JSON.parse(r.text)
    } catch {
      /* not JSON */
    }
    if (r.status < 200 || r.status >= 300) throw new ProjectApiError(r.status, parsed)
    return parsed as IntakeDTO
  })()
}

const MINUTE = 60_000

export const projectKeys = {
  options: () => ['projects', 'options'] as const,
  list: () => ['projects', 'list'] as const,
}

/**
 * The radio figures a saved project states, read from its mission record (the
 * mission the form adapter does not carry them). Always asked afresh, so an
 * edit never starts from figures that were since changed.
 */
export function useStoredRadio(id: string | undefined) {
  return useQuery({
    queryKey: ['projects', 'radio', id] as const,
    enabled: Boolean(id),
    staleTime: 0,
    gcTime: 0,
    retry: 1,
    queryFn: async ({ signal }) => {
      // The generated schema predates these fields, so they are read through their own type.
      const c = (await api.mission(id as string, signal)).lifecycle?.comms as RadioFigures & { eirp_dbw?: number | null; gt_dbk?: number | null } | null | undefined
      return {
        eirp_dbw: c?.eirp_dbw ?? null,
        eirp_tol_db: c?.eirp_tol_db ?? null,
        gt_dbk: c?.gt_dbk ?? null,
        frequency_mhz: c?.frequency_mhz ?? null,
        data_rates_kbps: c?.data_rates_kbps ?? [],
        required_ebn0_db: c?.required_ebn0_db ?? null,
        required_margin_db: c?.required_margin_db ?? null,
      }
    },
  })
}

/** The form's choices, from the catalogues. Public; asked for once. */
export function useProjectOptions() {
  return useQuery({
    queryKey: projectKeys.options(),
    enabled: !PROJECTS_OFFLINE,
    staleTime: 10 * MINUTE,
    retry: (n, e) => !(e instanceof ApiError && e.status < 500 && e.status > 0) && n < 1,
    queryFn: ({ signal }) => projectsApi.options(signal),
  })
}

/** The team's own projects, newest first. */
export function useProjects() {
  return useQuery({
    queryKey: projectKeys.list(),
    enabled: !PROJECTS_OFFLINE,
    staleTime: MINUTE,
    retry: false,
    queryFn: ({ signal }) => projectsApi.list(signal),
  })
}

/** Anything that shows a mission is asked for again after a project changes. */
function useRefreshMissions() {
  const client = useQueryClient()
  return () => {
    void client.invalidateQueries({ queryKey: ['missions'] })
    void client.invalidateQueries({ queryKey: ['mission'] })
    void client.invalidateQueries({ queryKey: ['lifecycle'] })
    void client.invalidateQueries({ queryKey: ['projects'] })
    void client.invalidateQueries({ queryKey: ['sites'] })
  }
}

/** Create (no id) or replace (with an id). */
export function useSaveProject() {
  const refresh = useRefreshMissions()
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: ProjectIn }) =>
      id ? projectsApi.update(id, body) : projectsApi.create(body),
    onSuccess: refresh,
  })
}

export function useDeleteProject() {
  const refresh = useRefreshMissions()
  return useMutation({ mutationFn: (id: string) => projectsApi.remove(id), onSuccess: refresh })
}

/** Reads one file into a draft. `progress` is the upload's, then "reading"; null when idle. */
export function useIntake() {
  const [progress, setProgress] = useState<IntakeProgress | null>(null)
  const m = useMutation({
    mutationFn: (file: File) => postIntake(file, setProgress),
    onSettled: () => setProgress(null),
  })
  return { ...m, progress }
}
