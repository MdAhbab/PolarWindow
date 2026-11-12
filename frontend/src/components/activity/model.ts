/**
 * The activity tray's pure logic: how full the shell's ring is, what each
 * item's state is in a shape and words, and which scenarios have just
 * finished (for the toast). No fetch and no React here.
 */
import { create } from 'zustand'
import type { ActivityDTO, ActivityItemDTO } from '../../lib/api/experience.types'
import type { IconName } from '../Icon'

/** Whether the tray is open: the ring opens it, and so does Home's "Being worked out". */
export const useActivityTray = create<{ isOpen: boolean; setOpen: (open: boolean) => void }>((set) => ({
  isOpen: false,
  setOpen: (isOpen) => set({ isOpen }),
}))

export interface RingState {
  /** How many things are queued or running. */
  count: number
  /**
   * The ring's fill, 0 to 1: the mean of the running items' own progress.
   * Null when something is active but none has given a figure yet, so the
   * ring says "working" without claiming how far.
   */
  fraction: number | null
}

const clamp01 = (v: number) => Math.min(1, Math.max(0, v))

/** The ring, from the feed: empty and still when nothing is being worked out. */
export function ringState(data: ActivityDTO | undefined): RingState {
  const active = data?.active ?? []
  if (!active.length) return { count: 0, fraction: 0 }
  const known = active.filter((a) => typeof a.progress === 'number' && Number.isFinite(a.progress))
  if (!known.length) return { count: active.length, fraction: null }
  // Queued items with no figure count as not started, so a queue never reads as half done.
  const sum = active.reduce((acc, a) => acc + (typeof a.progress === 'number' && Number.isFinite(a.progress) ? clamp01(a.progress) : 0), 0)
  return { count: active.length, fraction: sum / active.length }
}

/** The ring button's name: what it holds, in words. */
export function ringLabel(ring: RingState, live: boolean): string {
  if (!live) return 'Activity: not available in the saved copy'
  if (!ring.count) return 'Activity: nothing is being worked out'
  const what = `${ring.count} ${ring.count === 1 ? 'thing is' : 'things are'} being worked out`
  return ring.fraction === null ? `Activity: ${what}` : `Activity: ${what}, ${Math.round(ring.fraction * 100)}% done`
}

/** An item's state as a glyph and words, never colour alone. */
export const STATUS_WORDS: Record<ActivityItemDTO['status'], { icon: IconName; words: string }> = {
  queued: { icon: 'ring', words: 'Waiting its turn' },
  running: { icon: 'quarter', words: 'Working it out' },
  done: { icon: 'check', words: 'Done' },
  failed: { icon: 'alert', words: 'Did not finish' },
}

/** What kind of answer an item is working out, in words. */
export const KIND_WORDS: Record<ActivityItemDTO['kind'], string> = {
  launch: 'Launch opportunities',
  trip: 'Trip',
  contact: 'Contact',
  rover: 'Rover line of sight',
  site_build: 'Skyline for a new landing spot',
  scenario: 'Scenario',
}

/** The progress figure in words, or null when the item has none. */
export function progressWords(item: Pick<ActivityItemDTO, 'progress' | 'status'>): string | null {
  if (item.status === 'done' || item.status === 'failed') return null
  if (typeof item.progress !== 'number' || !Number.isFinite(item.progress)) return null
  return `${Math.round(clamp01(item.progress) * 100)}% done`
}

/** "started 3 min ago", "finished just now": the item's age from its own times. */
export function whenWords(item: Pick<ActivityItemDTO, 'started_at' | 'finished_at'>, nowMs: number): string | null {
  const finished = item.finished_at ? Date.parse(item.finished_at) : NaN
  const started = Date.parse(item.started_at)
  const at = Number.isNaN(finished) ? started : finished
  if (Number.isNaN(at)) return null
  const s = Math.max(0, (nowMs - at) / 1000)
  const ago = s < 60 ? 'just now' : s < 3600 ? `${Math.round(s / 60)} min ago` : `${Math.round(s / 3600)} h ago`
  return `${Number.isNaN(finished) ? 'started' : 'finished'} ${ago}`
}

/**
 * The scenarios that were being worked out at the last look and have
 * finished since: in `recent` now, done or failed. Only items seen active
 * count, so opening the app never toasts what finished before it was open.
 */
export function finishedScenarios(previouslyActive: ReadonlySet<string>, data: ActivityDTO): ActivityItemDTO[] {
  const stillActive = new Set(data.active.map((a) => a.key))
  return data.recent.filter(
    (r) =>
      r.kind === 'scenario' &&
      (r.status === 'done' || r.status === 'failed') &&
      previouslyActive.has(r.key) &&
      !stillActive.has(r.key),
  )
}
