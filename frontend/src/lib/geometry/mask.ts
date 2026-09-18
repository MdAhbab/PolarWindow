import type { HorizonMask } from '../types'

/**
 * Horizon-mask lookup helpers.
 *
 * The ray-cast that *built* these masks used to live here, against a synthetic
 * height field. It now runs in the backend against the LOLA polar DEM at 0.25
 * degree resolution out to 50 km, so what remains on the client is the
 * interpolation the charts need -- and `DEM_VERTICAL_ERROR_M`, kept only as the
 * fallback for a response that somehow arrives without `meta.uncertainty`.
 * Prefer the value from `meta`: it is per-site and per-product, this one is not.
 */

/**
 * Vertical accuracy of the elevation model, metres. FALLBACK ONLY.
 * The authoritative figure is `meta.uncertainty.dem_vertical_error_m`.
 */
export const DEM_VERTICAL_ERROR_M = 2.0

function lerpWrapped(arr: Float32Array, azDeg: number): number {
  const a = ((azDeg % 360) + 360) % 360
  const i = Math.floor(a)
  const f = a - i
  const j = (i + 1) % 360
  return arr[i] + (arr[j] - arr[i]) * f
}

export function maskElevationAt(mask: HorizonMask, azDeg: number): number {
  return lerpWrapped(mask.elDeg, azDeg)
}

export function maskToleranceAt(mask: HorizonMask, azDeg: number): number {
  return lerpWrapped(mask.tolDeg, azDeg)
}

export function maskRangeAt(mask: HorizonMask, azDeg: number): number {
  return lerpWrapped(mask.rangeM, azDeg)
}
