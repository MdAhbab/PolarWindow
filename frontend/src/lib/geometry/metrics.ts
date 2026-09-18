import type { SiteMetrics } from '../types'

/**
 * Placeholder survival limit: the longest continuous darkness the lander is
 * assumed to ride out on stored energy, hours. A real mission replaces this
 * with its own thermal-battery number and every verdict in the app follows.
 */
export const SURVIVAL_LIMIT_H = 120

/** Margin applied on top of the worst compound event when sizing autonomy. */
export const AUTONOMY_MARGIN = 0.2


export interface AutonomyPacket {
  worstCompoundH: number
  requiredAutonomyH: number
  survivalNeededH: number
  overLimit: boolean
  compoundInsideDark: boolean
}

export function autonomyPacket(m: SiteMetrics): AutonomyPacket {
  const worst = m.worstCompoundH
  const requiredAutonomyH = worst * (1 + AUTONOMY_MARGIN)
  // If the worst blackout falls inside a dark period, the battery has to carry
  // the whole night, not just the silence.
  const inside = m.compound.some((c) =>
    m.sun.arcs.some((a) => !a.up && c.startH >= a.startH - 1e-6 && c.endH <= a.endH + 1e-6),
  )
  return {
    worstCompoundH: worst,
    requiredAutonomyH,
    survivalNeededH: inside ? m.sun.longestDownH : worst,
    overLimit: m.sun.longestDownH > SURVIVAL_LIMIT_H,
    compoundInsideDark: inside,
  }
}

export function metricValue(m: SiteMetrics, key: string): number {
  switch (key) {
    case 'sunHours':
      return m.sun.upHours
    case 'earthHours':
      return m.earth.upHours
    case 'longestDark':
      return m.sun.longestDownH
    case 'longestBlackout':
      return m.earth.longestDownH
    default:
      return 0
  }
}

/** Lower is better for the two gap metrics; higher is better for the two totals. */
export function metricIsDescending(key: string): boolean {
  return key === 'sunHours' || key === 'earthHours'
}

export function rankSites(
  entries: { siteId: string; metrics: SiteMetrics }[],
  key: string,
): string[] {
  const desc = metricIsDescending(key)
  return [...entries]
    .sort((a, b) => {
      const va = metricValue(a.metrics, key)
      const vb = metricValue(b.metrics, key)
      return desc ? vb - va : va - vb
    })
    .map((e) => e.siteId)
}
