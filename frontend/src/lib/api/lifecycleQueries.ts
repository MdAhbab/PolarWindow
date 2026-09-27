/**
 * TanStack Query hooks for the six mission sections (docs/lifecycle-api.md).
 *
 * A section answers in one of three ways, and each hook says which:
 *   - the answer (`Section<T>`);
 *   - 202 with a job: it is being worked out. The job is polled at
 *     `GET /jobs/{id}` every `poll_after_s`, and the section is asked again
 *     once, when the job is done;
 *   - an error, rendered from the server's problem detail.
 *
 * Section queries wait for `/sections` to settle, because its `meta.engines`
 * goes into their keys (ADR-13). If `/sections` fails they run anyway.
 */
import { useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, api, type SectionResult } from './client'
import { keys, setLifecycleEngines } from './queries'
import type { AuditEntryDTO, JobRefDTO, SectionDTO, SectionId, SectionStatusDTO } from './lifecycle'

const MINUTE = 60_000

/** A 4xx other than a timeout is an answer ("not offered", "not found"): retrying cannot change it. */
const retryServerErrors = (count: number, err: unknown) =>
  !(err instanceof ApiError && err.status >= 400 && err.status < 500) && count < 1

export function useSections(missionId: string | undefined) {
  return useQuery({
    queryKey: keys.sections(missionId),
    enabled: Boolean(missionId),
    staleTime: MINUTE,
    retry: retryServerErrors,
    queryFn: async ({ signal }): Promise<SectionDTO<SectionStatusDTO[]>> => {
      const dto = await api.sections(missionId as string, signal)
      setLifecycleEngines(dto.meta.engines)
      return dto
    },
  })
}

/** One step's status from `/sections`, when the server gives it. */
export function useSectionStatus(missionId: string | undefined, section: SectionId): SectionStatusDTO | undefined {
  return useSections(missionId).data?.data.find((s) => s.section === section)
}

/** Where a section's answer stands. */
export type SectionView<T> =
  | { status: 'pending' }
  | { status: 'answer'; section: SectionDTO<T>; refreshing: boolean }
  | { status: 'working'; job: JobRefDTO }
  | { status: 'error'; error: unknown; retry: () => void }

/**
 * One section's answer, following a 202 through its job.
 *
 * `params` are what the answer depends on besides the mission (the dates,
 * the chosen opportunity); they go into the key.
 */
export function useSection<T>(
  section: Exclude<SectionId, 'landing'> | 'launch-weather',
  missionId: string | undefined,
  fetcher: (signal: AbortSignal) => Promise<SectionResult<T>>,
  params: unknown[] = [],
  enabled = true,
): SectionView<T> {
  const sections = useSections(missionId)
  const settled = !sections.isPending || sections.fetchStatus === 'idle'
  const q = useQuery({
    queryKey: keys.lifecycle(section, missionId, ...params),
    enabled: Boolean(missionId) && settled && enabled,
    staleTime: 5 * MINUTE,
    retry: retryServerErrors,
    queryFn: ({ signal }) => fetcher(signal),
  })
  const job = q.data?.kind === 'job' ? q.data.job : undefined
  const polled = useJob(job)
  const asked = useRef<number | null>(null)
  const { refetch } = q

  // The job finished: ask for the section once more, and only once per job,
  // so a server that answers 202 again cannot start a loop.
  useEffect(() => {
    const done = polled.data?.status === 'done'
    if (!job || !done || asked.current === job.job_id) return
    asked.current = job.job_id
    void refetch()
  }, [job, polled.data?.status, refetch])

  if (q.error) return { status: 'error', error: q.error, retry: () => void q.refetch() }
  if (!q.data) return { status: 'pending' }
  if (q.data.kind === 'answer') return { status: 'answer', section: q.data.section, refreshing: q.isFetching }
  const latest = polled.data ?? q.data.job
  if (latest.status === 'failed') {
    return {
      status: 'error',
      error: new ApiError(500, {
        detail: {
          title: 'Working this out failed',
          detail: latest.message || 'The calculation stopped before it finished.',
          ui: { still_works: 'The other sections and the landing numbers are unaffected.', retryable: true },
        },
      }),
      retry: () => {
        asked.current = null
        void q.refetch()
      },
    }
  }
  if (polled.error) return { status: 'error', error: polled.error, retry: () => void polled.refetch() }
  return { status: 'working', job: latest }
}

/** A job, polled at the pace the server asks for, until it is done or failed. */
export function useJob(job: JobRefDTO | undefined) {
  return useQuery({
    queryKey: keys.job(job?.job_id),
    enabled: Boolean(job) && job?.status !== 'done' && job?.status !== 'failed',
    staleTime: 0,
    gcTime: MINUTE,
    retry: retryServerErrors,
    queryFn: ({ signal }) => api.job((job as JobRefDTO).job_id, signal),
    refetchInterval: (query) => {
      const d = query.state.data
      if (d && (d.status === 'done' || d.status === 'failed')) return false
      return Math.max(1, d?.poll_after_s ?? job?.poll_after_s ?? 2) * 1000
    },
  })
}

// ---------------------------------------------------------------------------
// The pieces rows open on request
// ---------------------------------------------------------------------------

export function useParts(missionId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: keys.lifecycle('parts', missionId),
    enabled: Boolean(missionId) && enabled,
    retry: retryServerErrors,
    queryFn: ({ signal }) => api.parts(missionId as string, signal),
  })
}

export function usePartImpact(partId: string | null) {
  return useQuery({
    queryKey: ['partImpact', partId],
    enabled: Boolean(partId),
    retry: retryServerErrors,
    queryFn: ({ signal }) => api.partImpact(partId as string, signal),
  })
}

export function useRiskScales(enabled: boolean) {
  return useQuery({
    queryKey: keys.riskScales(),
    enabled,
    staleTime: Infinity,
    retry: retryServerErrors,
    queryFn: ({ signal }) => api.riskScales(signal),
  })
}

export function useLandingHistory(enabled: boolean) {
  return useQuery({
    queryKey: keys.landingHistory(),
    enabled,
    staleTime: Infinity,
    retry: retryServerErrors,
    queryFn: ({ signal }) => api.landingHistory(signal),
  })
}

export function useLessons(missionId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: keys.lifecycle('lessons', missionId),
    enabled: Boolean(missionId) && enabled,
    retry: retryServerErrors,
    queryFn: ({ signal }) => api.lessons(missionId as string, signal),
  })
}

/** A record's change history, newest first. Readiness items have their own route. */
export type HistoryEntity = 'ready_item' | 'part' | 'risk' | 'booking' | 'forecast' | 'limits' | 'parameter' | 'lesson' | 'feed'

export function useHistory(entity: HistoryEntity, id: string | null) {
  return useQuery({
    queryKey: ['history', entity, id],
    enabled: Boolean(id),
    staleTime: 0,
    retry: retryServerErrors,
    queryFn: async ({ signal }): Promise<AuditEntryDTO[]> => {
      const r = entity === 'ready_item' ? await api.itemHistory(id as string, signal) : await api.history(entity, id as string, signal)
      const entries = Array.isArray(r) ? r : r.entries
      return [...entries].sort((a, b) => Date.parse(b.at) - Date.parse(a.at))
    },
  })
}

export function useFeeds(enabled: boolean) {
  return useQuery({
    queryKey: keys.feeds(),
    enabled,
    staleTime: 0,
    refetchInterval: enabled ? MINUTE : false,
    retry: retryServerErrors,
    queryFn: ({ signal }) => api.feeds(signal),
  })
}

export function useParameters(enabled: boolean) {
  return useQuery({
    queryKey: keys.parameters(),
    enabled,
    staleTime: 0,
    retry: retryServerErrors,
    queryFn: ({ signal }) => api.parameters(signal),
  })
}

/**
 * A write the project manager makes. On success every lifecycle answer and
 * every history is asked for again, so the screen shows what the server now
 * holds, never a guess of it.
 */
export function useLifecycleWrite<A, R = unknown>(fn: (args: A) => Promise<R>) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['lifecycle'] })
      void client.invalidateQueries({ queryKey: ['history'] })
      void client.invalidateQueries({ queryKey: keys.feeds() })
      void client.invalidateQueries({ queryKey: keys.parameters() })
    },
  })
}
