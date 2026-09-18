import { create } from 'zustand'
import type { Face, MetricKey } from './types'

/**
 * UI state only.
 *
 * ADR-2 splits state in two and the rule is worth stating where it is enforced:
 *
 *   **zustand owns what the user chose. TanStack Query owns what the server
 *   said.** Nothing derived from the server is ever `set()` into this store.
 *
 * Before the backend existed this store also held `metrics` and a `compute`
 * state machine fed by a Web Worker. Both are gone: they were server state
 * wearing a client-state costume, and keeping them would have meant two caches
 * that could disagree. Their replacements live in `mission.ts`, with the same
 * hook names so no component had to change.
 */

export type Theme = 'dark' | 'light'
export type Motion = 'full' | 'reduced'

/**
 * The instant `tH = 0` refers to. Shared with `format.ts` so a timestamp means
 * the same thing wherever it is rendered, and used to turn the store's
 * hour-based window into the ISO 8601 the API speaks.
 */
export const MODEL_EPOCH_MS = Date.UTC(2027, 2, 14, 0, 0, 0)

/** One synodic month: the period of the Sun's azimuth sweep at the pole. */
export const SYNODIC_HOURS = 708.734

/** Sampling step the API is asked for. 900 s over 708 h is 2,835 samples. */
export const DEFAULT_STEP_S = 900

interface MissionState {
  siteId: string
  compareIds: string[]
  /** Hours from the model epoch at which the window opens. */
  windowStartH: number
  windowHours: number
  /** Where the cursor sits inside the window, hours from windowStartH. */
  cursorH: number
  face: Face
  theme: Theme
  motion: Motion
  rankBy: MetricKey
  playing: boolean

  setSite: (id: string) => void
  toggleCompare: (id: string) => void
  setCursor: (h: number) => void
  nudgeCursor: (h: number) => void
  setWindow: (startH: number, hours: number) => void
  setFace: (f: Face) => void
  setTheme: (t: Theme) => void
  setMotion: (m: Motion) => void
  setRankBy: (k: MetricKey) => void
  setPlaying: (p: boolean) => void
}

export const DEFAULT_COMPARE = ['connecting-ridge', 'malapert-massif', 'faustini-rim']

export const useMission = create<MissionState>((set, get) => ({
  siteId: 'connecting-ridge',
  compareIds: DEFAULT_COMPARE,
  windowStartH: 0,
  windowHours: SYNODIC_HOURS,
  cursorH: SYNODIC_HOURS * 0.42,
  face: 'planner',
  theme: 'dark',
  motion: 'full',
  rankBy: 'longestDark',
  playing: false,

  setSite: (siteId) => set({ siteId }),

  toggleCompare: (id) =>
    set((s) => {
      const has = s.compareIds.includes(id)
      if (has && s.compareIds.length <= 2) return s
      return { compareIds: has ? s.compareIds.filter((x) => x !== id) : [...s.compareIds, id] }
    }),

  setCursor: (h) => set((s) => ({ cursorH: Math.max(0, Math.min(s.windowHours, h)) })),

  nudgeCursor: (dh) =>
    set((s) => {
      const next = s.cursorH + dh
      const wrapped = ((next % s.windowHours) + s.windowHours) % s.windowHours
      return { cursorH: wrapped, playing: false }
    }),

  setWindow: (startH, hours) =>
    set({ windowStartH: startH, windowHours: hours, cursorH: Math.min(get().cursorH, hours) }),

  setFace: (face) => set({ face }),

  setTheme: (theme) => {
    document.documentElement.setAttribute('data-theme', theme)
    set({ theme })
  },

  setMotion: (motion) => {
    document.documentElement.setAttribute('data-motion', motion === 'reduced' ? 'reduced' : 'full')
    set({ motion })
  },

  setRankBy: (rankBy) => set({ rankBy }),
  setPlaying: (playing) => set({ playing }),
}))

/** Hours from the model epoch, as an ISO 8601 UTC instant the API accepts. */
export function isoFromHours(tH: number): string {
  return new Date(MODEL_EPOCH_MS + tH * 3_600_000).toISOString().replace(/\.\d{3}Z$/, 'Z')
}
