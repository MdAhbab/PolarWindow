import type { Arc } from './types'

/** One crossing's timing margin, in hours from the window start. */
export interface Band {
  fromH: number
  toH: number
  grazing: boolean
}

/**
 * The −45° uncertainty band at every crossing, from the arcs themselves.
 *
 * Each crossing is the end of one arc and the start of the next; its margin is
 * the next arc's `startToleranceH` (the server reports each edge separately).
 * A window edge is not a crossing and gets no band -- the window cut the arc,
 * nothing was timed there. Bands are clipped to the window and merged where
 * they overlap, so a chart can draw them as one continuous hatch.
 *
 * This is presentation of server numbers, not geometry: nothing here computes
 * a position or a time the API did not return.
 */
export function crossingBands(arcs: Arc[], windowHours: number): Band[] {
  const raw: Band[] = []
  for (let i = 1; i < arcs.length; i++) {
    const a = arcs[i]
    const prev = arcs[i - 1]
    const half = a.startToleranceH ?? prev.endToleranceH
    if (half === undefined || !(half > 0)) continue
    raw.push({
      fromH: Math.max(0, a.startH - half),
      toH: Math.min(windowHours, a.startH + half),
      grazing: a.grazing || prev.grazing,
    })
  }
  raw.sort((x, y) => x.fromH - y.fromH)
  const merged: Band[] = []
  for (const b of raw) {
    const last = merged[merged.length - 1]
    if (last && b.fromH <= last.toH) {
      last.toH = Math.max(last.toH, b.toH)
      last.grazing = last.grazing || b.grazing
    } else {
      merged.push({ ...b })
    }
  }
  return merged
}
