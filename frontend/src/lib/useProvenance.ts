import { useHealth } from './api/queries'
import { useSnapshotActive } from './api/snapshot'
import type { Provenance } from '../components/ui'

/**
 * What the badge should say, from the service's own report of itself.
 *
 * Deliberately pessimistic while the health check is in flight or has failed:
 * claiming "measured" before knowing would be exactly the overstatement the
 * badge exists to prevent.
 */
export function useProvenance(): Provenance {
  const { data, isPending, error } = useHealth()
  // Saved answers are on screen: that is the first thing to know about them.
  if (useSnapshotActive()) return 'snapshot'
  if (isPending || error || !data) return 'partial'
  const kernels = Boolean(data.kernels?.loaded)
  const dem = Boolean(data.dem?.regional_present)
  if (kernels && dem) return 'measured'
  if (kernels || dem) return 'partial'
  return 'unavailable'
}
