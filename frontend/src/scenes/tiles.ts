import { API_BASE } from '../lib/api/client'
import { DATA_MODE, snapshotTileUrl } from '../lib/api/snapshot'

/** The LOLA hillshade tiles the Map draws: from the offline copy in a snapshot build, from the service otherwise. */
export function hillshadeTile(z: number, x: number, y: number): string {
  return DATA_MODE === 'snapshot' ? snapshotTileUrl('hillshade', z, x, y) : `${API_BASE}/tiles/hillshade/${z}/${x}/${y}.png`
}
