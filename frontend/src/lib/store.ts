import { create } from 'zustand'
import type { MetricKey } from './types'
import { readPrefs, writePrefs } from './prefs'

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
  theme: Theme
  motion: Motion
  rankBy: MetricKey
  playing: boolean
  /** The chart on screen is being read as its table twin (the T key). */
  tableOpen: boolean
  /**
   * Single-key shortcuts (T, [ ], Space) are on. WCAG 2.1.4 requires
   * that bare-letter shortcuts can be turned off: voice-control users trigger
   * them by accident. Default on; the switch is in the settings sheet (U8).
   */
  shortcuts: boolean
  /** The "How the AI got this" drawer, and the run it should open at. */
  runLog: { open: boolean; runId: string | null }
  settingsOpen: boolean

  setSite: (id: string) => void
  toggleCompare: (id: string) => void
  setCursor: (h: number) => void
  nudgeCursor: (h: number) => void
  setWindow: (startH: number, hours: number) => void
  setTheme: (t: Theme) => void
  setMotion: (m: Motion) => void
  setRankBy: (k: MetricKey) => void
  setPlaying: (p: boolean) => void
  toggleTable: () => void
  setShortcuts: (on: boolean) => void
  openRunLog: (runId?: string | null) => void
  closeRunLog: () => void
  setSettingsOpen: (open: boolean) => void
}

/** The largest window the API computes in one request (system-design §10.6). */
export const MAX_WINDOW_HOURS = 730 * 24

/**
 * A window given as two instants, in the store's unit (hours from the model
 * epoch). A mission's surface window, a month cell and the date input all
 * arrive as instants; the store keeps hours so the slider and the rings stay
 * unchanged.
 */
export function windowFromInstants(startMs: number, endMs: number): { startH: number; hours: number } {
  const hours = Math.min(MAX_WINDOW_HOURS, Math.max(0.25, (endMs - startMs) / 3_600_000))
  return { startH: (startMs - MODEL_EPOCH_MS) / 3_600_000, hours }
}

export const DEFAULT_COMPARE = ['connecting-ridge', 'malapert-massif', 'faustini-rim']

const saved = readPrefs()
if (typeof document !== 'undefined') {
  document.documentElement.setAttribute('data-theme', saved.theme)
  document.documentElement.setAttribute('data-motion', saved.motion)
}

/** Keep the three remembered choices in step with the store. */
function remember(s: Pick<MissionState, 'theme' | 'motion' | 'shortcuts'>) {
  writePrefs({ theme: s.theme, motion: s.motion, shortcuts: s.shortcuts })
}

export const useMission = create<MissionState>((set, get) => ({
  siteId: 'connecting-ridge',
  compareIds: DEFAULT_COMPARE,
  windowStartH: 0,
  windowHours: SYNODIC_HOURS,
  cursorH: SYNODIC_HOURS * 0.42,
  theme: saved.theme,
  motion: saved.motion,
  rankBy: 'longestDark',
  playing: false,
  tableOpen: false,
  shortcuts: saved.shortcuts,
  runLog: { open: false, runId: null },
  settingsOpen: false,

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

  setWindow: (startH, hours) => {
    const h = Math.min(MAX_WINDOW_HOURS, Math.max(0.25, hours))
    const s = get()
    if (s.windowStartH === startH && s.windowHours === h) return
    // A new window is a new question: the cursor starts at its opening and
    // play stops, rather than the cursor landing at some arbitrary hour the
    // previous window happened to be showing.
    set({ windowStartH: startH, windowHours: h, cursorH: 0, playing: false })
  },

  setTheme: (theme) => {
    document.documentElement.setAttribute('data-theme', theme)
    set({ theme })
    remember(get())
  },

  setMotion: (motion) => {
    document.documentElement.setAttribute('data-motion', motion === 'reduced' ? 'reduced' : 'full')
    set({ motion })
    remember(get())
  },

  setRankBy: (rankBy) => set({ rankBy }),
  setPlaying: (playing) => set({ playing }),
  toggleTable: () => set((s) => ({ tableOpen: !s.tableOpen })),
  setShortcuts: (shortcuts) => {
    set({ shortcuts })
    remember(get())
  },
  openRunLog: (runId = null) => set({ runLog: { open: true, runId } }),
  closeRunLog: () => set((s) => ({ runLog: { open: false, runId: s.runLog.runId } })),
  setSettingsOpen: (settingsOpen) => set({ settingsOpen }),
}))
