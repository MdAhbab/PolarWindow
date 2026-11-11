/**
 * The lander tools on a site: power and temperature (ADR-21) and the landing
 * ellipse (ADR-22). Both are asked for only when the person presses "Work it
 * out": the request body is the query key, so nothing runs on page load and an
 * unchanged form asked again comes from the cache. A saved copy calls nothing.
 * Shapes from ./surface.types.
 */
import { useQuery } from '@tanstack/react-query'
import { apiRequest } from './client'
import { LIVE_SERVICE } from './home'
import type { DispersionRequestDTO, DispersionResponseDTO } from './surface.types'
import type { EnergyRequestDTO, EnergyResponseDTO } from './surface.types'
import type { MeshRequestDTO, MeshResponseDTO } from './surface.types'

const enc = encodeURIComponent

export const surfaceApi = {
  energy: (siteId: string, body: EnergyRequestDTO, signal?: AbortSignal) =>
    apiRequest<EnergyResponseDTO>(`/sites/${enc(siteId)}/energy`, { body, signal, method: 'POST' }),
  dispersion: (siteId: string, body: DispersionRequestDTO, signal?: AbortSignal) =>
    apiRequest<DispersionResponseDTO>(`/sites/${enc(siteId)}/dispersion`, { body, signal, method: 'POST' }),
  mesh: (siteId: string, body: MeshRequestDTO, signal?: AbortSignal) =>
    apiRequest<MeshResponseDTO>(`/sites/${enc(siteId)}/mesh/simulate`, { body, signal, method: 'POST' }),
}

export const surfaceKeys = {
  energy: (siteId: string, body: EnergyRequestDTO | null) => ['surface', 'energy', siteId, body] as const,
  dispersion: (siteId: string, body: DispersionRequestDTO | null) => ['surface', 'dispersion', siteId, body] as const,
  mesh: (siteId: string, body: MeshRequestDTO | null) => ['surface', 'mesh', siteId, body] as const,
}

/** Power and temperature for the body last asked for; idle until there is one. */
export function useEnergy(siteId: string, body: EnergyRequestDTO | null) {
  return useQuery<EnergyResponseDTO>({
    queryKey: surfaceKeys.energy(siteId, body),
    enabled: LIVE_SERVICE && body !== null,
    staleTime: Infinity,
    retry: false,
    refetchOnWindowFocus: false,
    queryFn: ({ signal }) => surfaceApi.energy(siteId, body as EnergyRequestDTO, signal),
  })
}

/** The landing ellipse for the body last asked for; idle until there is one. */
export function useDispersion(siteId: string, body: DispersionRequestDTO | null) {
  return useQuery<DispersionResponseDTO>({
    queryKey: surfaceKeys.dispersion(siteId, body),
    enabled: LIVE_SERVICE && body !== null,
    staleTime: Infinity,
    retry: false,
    refetchOnWindowFocus: false,
    queryFn: ({ signal }) => surfaceApi.dispersion(siteId, body as DispersionRequestDTO, signal),
  })
}

/** The surface mesh for the body last asked for; idle until there is one. */
export function useMesh(siteId: string, body: MeshRequestDTO | null) {
  return useQuery<MeshResponseDTO>({
    queryKey: surfaceKeys.mesh(siteId, body),
    enabled: LIVE_SERVICE && body !== null,
    staleTime: Infinity,
    retry: false,
    refetchOnWindowFocus: false,
    queryFn: ({ signal }) => surfaceApi.mesh(siteId, body as MeshRequestDTO, signal),
  })
}
