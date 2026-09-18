import type { SiteMetrics } from '../types'

/**
 * Placeholder survival limit: the longest continuous darkness the lander is
 * assumed to ride out on stored energy, hours. A real mission replaces this
 * with its own thermal-battery number and every verdict in the app follows.
 *
 * The only numeric literal the screens use that the API does not supply --
 * deliberately, because the backend returns durations and refuses to return
 * verdicts: a verdict needs a thermal model this system does not have.
 */
export const SURVIVAL_LIMIT_H = 120

/**
 * The value of one of the four numbers, for display.
 *
 * Ranking is not done here: order, ranks and ties come from `POST /compare`,
 * so the screen and the API cannot disagree about which site leads.
 */
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
