/**
 * The bridge between the store's window and the server's answers.
 *
 * Exposes the same hook names the screens already call — `useFocusedMetrics`,
 * `useMetricsFor` — so replacing the Web Worker with HTTP touched no component
 * that only consumed them. What changed is where the data comes from and, more
 * importantly, that the four states (loading, empty, error, uncertain) are now
 * expressible per-site rather than as one global `compute.status`.
 */
import { useMemo } from 'react'
import type { SiteMetrics } from './types'
import { MODEL_EPOCH_MS, useMission, DEFAULT_STEP_S } from './store'
import {
  useCompare,
  useHealth,
  useManySiteMetrics,
  useSites,
  useSiteView,
  type WindowParams,
} from './api/queries'
import { adaptAutonomy, quantiseWindow, toHours, type Meta } from './api/adapters'
import type { MetricsDTO } from './api/client'

/**
 * The current window, in the form the API takes, snapped exactly as the
 * server snaps it -- so the client's cache key and the server's are the same
 * key, and two windows the server treats as one never cost two requests.
 */
export function useWindowParams(): WindowParams {
  const windowStartH = useMission((s) => s.windowStartH)
  const windowHours = useMission((s) => s.windowHours)
  return useMemo(() => windowParamsFor(windowStartH, windowHours), [windowStartH, windowHours])
}

/**
 * The sampling step for a window of this length.
 *
 * 900 s over one lunar day is the step the golden fixtures pin, and it stays
 * the step for anything up to 45 days. A movable window (v2) can be two years
 * long, and 900 s over 730 days is 70,080 samples per body: coarser steps keep
 * every window under about 9,000 samples, inside the API's 300–7,200 s bounds.
 */
export function stepForHours(hours: number): number {
  if (hours <= 45 * 24) return DEFAULT_STEP_S
  if (hours <= 120 * 24) return 1800
  if (hours <= 400 * 24) return 3600
  return 7200
}

export function windowParamsFor(windowStartH: number, windowHours: number): WindowParams {
  const stepS = stepForHours(windowHours)
  const startMs = MODEL_EPOCH_MS + windowStartH * 3_600_000
  const { start, end } = quantiseWindow(startMs, startMs + windowHours * 3_600_000, stepS)
  return { start, end, stepS }
}

/**
 * Metrics for the focused site, including its per-sample tracks.
 *
 * Only this site gets a timeline — 2,835 samples times two bodies times every
 * site on screen is over a megabyte nobody looks at. The old Worker made the
 * same call for the same reason.
 */
export function useFocusedMetrics(): SiteMetrics | undefined {
  const siteId = useMission((s) => s.siteId)
  const w = useWindowParams()
  return useSiteView(siteId, w, true).data?.metrics
}

/** Metrics for one site, arcs only. */
export function useMetricsFor(siteId: string): SiteMetrics | undefined {
  const w = useWindowParams()
  return useSiteView(siteId, w, false).data?.metrics
}

/** The focused site's full view, including `meta` for the uncertainty state. */
export function useFocusedView() {
  const siteId = useMission((s) => s.siteId)
  const w = useWindowParams()
  return useSiteView(siteId, w, true)
}

export interface ComputeState {
  status: 'idle' | 'running' | 'ready' | 'error'
  done: number
  total: number
  error?: string
}

/**
 * Progress across a set of sites, in the shape `LoadingPanel` already draws.
 *
 * Derived from query state rather than pushed into a store, so it cannot drift
 * from what is actually in flight.
 */
export function useComputeState(siteIds: string[]): ComputeState {
  const w = useWindowParams()
  const { done, total, isPending, error } = useManySiteMetrics(siteIds, w)
  if (error) {
    return { status: 'error', done, total, error: String((error as Error).message ?? error) }
  }
  if (isPending) return { status: 'running', done, total }
  return { status: 'ready', done: total, total }
}

/** The four numbers for several sites at once, keyed by site id. */
export function useMetricsMap(siteIds: string[]): Record<string, MetricsDTO> {
  const w = useWindowParams()
  return useManySiteMetrics(siteIds, w).byId
}

export { useSites, useCompare, useHealth, adaptAutonomy, toHours }
export type { Meta, WindowParams }
