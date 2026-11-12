/**
 * Whether a page can keep up with a drifting background. The ambient glow
 * (components/AmbientGlow.tsx) measures a few animation frames once after
 * load; on a machine with no graphics acceleration they come far apart (the
 * glow's three full-screen layers cost scrolling 50 ms a frame where 16.7 ms
 * is wanted) and the glow's drift is switched off. The fields stay, still.
 *
 * This file is only the decision; it knows nothing of the page.
 */

/** A frame this far from the one before it, or more, is a slow frame (a 60 Hz screen gives 16.7 ms). */
export const SLOW_FRAME_MS = 30

/** Fewer gaps than this say nothing: the answer is "keeps up". */
export const MIN_FRAME_GAPS = 5

/** A gap this long is the tab being hidden or the page being busy, not the machine's speed: it is left out. */
export const STALL_MS = 1000

/** The gaps between consecutive timestamps, in the order given (milliseconds). */
export function frameGaps(stamps: readonly number[]): number[] {
  const gaps: number[] = []
  for (let i = 1; i < stamps.length; i++) {
    const g = stamps[i] - stamps[i - 1]
    if (Number.isFinite(g) && g >= 0) gaps.push(g)
  }
  return gaps
}

/** The median of a list of numbers; NaN for an empty list. */
export function median(values: readonly number[]): number {
  if (values.length === 0) return Number.NaN
  const s = [...values].sort((a, b) => a - b)
  const mid = Math.floor(s.length / 2)
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2
}

/**
 * True when the page cannot keep up: the median gap between frames is over
 * `limit`. A gap of a second or more (a hidden tab, a stall) is not counted,
 * and too few gaps left means no verdict (false), so a short or interrupted
 * sample never switches the glow off by mistake.
 */
export function framesTooSlow(gaps: readonly number[], limit: number = SLOW_FRAME_MS): boolean {
  const usable = gaps.filter((g) => Number.isFinite(g) && g >= 0 && g < STALL_MS)
  if (usable.length < MIN_FRAME_GAPS) return false
  return median(usable) > limit
}
