/**
 * Scenarios: a what-if for a step with no published data (docs/experience-plan.md).
 *
 * Fetches and hooks for the wire contract in `experience.types.ts`. A scenario
 * is worked out in the compute worker; `useScenario` follows it at the pace the
 * service asks for until it is done or failed, and keeps following it if the
 * person leaves the page and comes back (the query lives in the cache, the
 * address holds the id).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, apiRequest, fillQuantities } from './client'
import type {
  InterpretRequest,
  InterpretedDTO,
  ScenarioDTO,
  ScenarioGapsDTO,
  ScenarioIn,
  ScenarioListDTO,
} from './experience.types'

const MINUTE = 60_000
const enc = encodeURIComponent

/** A 4xx other than a timeout is an answer: retrying cannot change it. */
const retryServerErrors = (count: number, err: unknown) =>
  !(err instanceof ApiError && err.status >= 400 && err.status < 500) && count < 1

export const scenarioKeys = {
  all: ['scenarios'] as const,
  gaps: (missionId: string | undefined) => ['scenarios', 'gaps', missionId] as const,
  list: (missionId: string | undefined) => ['scenarios', 'list', missionId] as const,
  one: (id: string | undefined) => ['scenarios', 'one', id] as const,
}

export const scenarioApi = {
  gaps: (missionId: string, signal?: AbortSignal) =>
    apiRequest<ScenarioGapsDTO>(`/missions/${enc(missionId)}/scenarios/gaps`, { signal }),
  interpret: (missionId: string, body: InterpretRequest) =>
    apiRequest<InterpretedDTO>(`/missions/${enc(missionId)}/scenarios/interpret`, { body, method: 'POST' }),
  start: (missionId: string, body: ScenarioIn) =>
    apiRequest<ScenarioDTO>(`/missions/${enc(missionId)}/scenarios`, { body, method: 'POST' }),
  list: (missionId: string, signal?: AbortSignal) =>
    apiRequest<ScenarioListDTO>(`/missions/${enc(missionId)}/scenarios`, { signal }),
  one: async (id: string, signal?: AbortSignal) =>
    fillQuantities(await apiRequest<ScenarioDTO>(`/scenarios/${enc(id)}`, { signal })),
  remove: (id: string) => apiRequest<null>(`/scenarios/${enc(id)}`, { method: 'DELETE' }),
}

/** What a mission lacks for each step, the fields a scenario may assume, presets and example prompts. */
export function useScenarioGaps(missionId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: scenarioKeys.gaps(missionId),
    enabled: Boolean(missionId) && enabled,
    staleTime: MINUTE,
    retry: retryServerErrors,
    queryFn: ({ signal }) => scenarioApi.gaps(missionId as string, signal),
  })
}

/** Read a prompt into assumptions. Nothing is computed and nothing is saved. */
export function useInterpret(missionId: string) {
  return useMutation({
    mutationFn: (body: InterpretRequest) => scenarioApi.interpret(missionId, body),
  })
}

/** Start a scenario (or join the one that already exists for these assumptions). */
export function useStartScenario(missionId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: ScenarioIn) => scenarioApi.start(missionId, body),
    onSuccess: (dto) => {
      client.setQueryData(scenarioKeys.one(dto.id), dto)
      void client.invalidateQueries({ queryKey: scenarioKeys.list(missionId) })
    },
  })
}

/** True once a scenario will not change any more. */
export const isFinished = (s: Pick<ScenarioDTO, 'status'> | undefined) => s?.status === 'done' || s?.status === 'failed'

/** One scenario, polled at the pace the service asks for until it is done or failed. */
export function useScenario(id: string | undefined) {
  return useQuery({
    queryKey: scenarioKeys.one(id),
    enabled: Boolean(id) && id !== 'new',
    staleTime: 0,
    retry: retryServerErrors,
    queryFn: ({ signal }) => scenarioApi.one(id as string, signal),
    refetchInterval: (query) => {
      const d = query.state.data
      if (!d || isFinished(d)) return false
      return Math.max(1, d.poll_after_s || 2) * 1000
    },
  })
}

/** A mission's scenarios, presets first. */
export function useScenarios(missionId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: scenarioKeys.list(missionId),
    enabled: Boolean(missionId) && enabled,
    staleTime: 15_000,
    retry: retryServerErrors,
    queryFn: ({ signal }) => scenarioApi.list(missionId as string, signal),
  })
}

export function useDeleteScenario(missionId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => scenarioApi.remove(id),
    onSuccess: (_r, id) => {
      client.removeQueries({ queryKey: scenarioKeys.one(id) })
      void client.invalidateQueries({ queryKey: scenarioKeys.list(missionId) })
    },
  })
}
