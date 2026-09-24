export type Body = 'sun' | 'earth'

export type Face = 'planner' | 'educator' | 'public'

export type MetricKey = 'sunHours' | 'earthHours' | 'longestDark' | 'longestBlackout'

export interface Site {
  id: string
  code: string
  name: string
  /** Selenographic latitude, degrees. Negative is south. */
  latDeg: number
  /** Selenographic longitude, degrees east. */
  lonDeg: number
  /**
   * Elevation relative to the 1737.4 km reference sphere, metres. Null where no
   * elevation model covers the site (a CLPS target outside 80°S): an unknown
   * height is not zero, so it is never shown as one.
   */
  elevM: number | null
  note: string
  /**
   * How the landing point was found: on the rim of a named polar crater (so it
   * borders that crater's permanently shadowed floor), on a massif/plateau, or
   * used exactly as published (a CLPS mission target).
   */
  searchKind: 'rim' | 'massif' | 'published'
  /** A derived candidate, or the site standing for a CLPS mission's target. */
  kind: 'candidate' | 'mission_target'
  /** Searched in the DEM for open sky, or used exactly as published. */
  coordinateRule: 'derived_open_sky' | 'published'
  /** False outside the 80–90°S elevation model: the skyline is a smooth sphere. */
  terrainModelled: boolean
}

export interface HorizonMask {
  /** Skyline elevation in degrees, one entry per whole degree of bearing. */
  elDeg: Float32Array
  /** Ground range at which each bearing's skyline is set, metres. */
  rangeM: Float32Array
  /** Angular uncertainty per bearing, degrees, from the DEM's vertical error. */
  tolDeg: Float32Array
  maxElDeg: number
  maxElBearingDeg: number
}

export interface TrackSample {
  tH: number
  azDeg: number
  elDeg: number
  maskElDeg: number
  /** elDeg - maskElDeg. Positive means visible. */
  marginDeg: number
}

export interface Arc {
  body: Body
  /** True when the body is above the local skyline for this stretch. */
  up: boolean
  startH: number
  endH: number
  hours: number
  /** Timing error of this arc's duration (both edges in quadrature), hours. */
  toleranceH: number
  /** Timing error of the crossing that starts / ends this arc, hours; absent at a window edge. */
  startToleranceH?: number
  endToleranceH?: number
  /** True when the crossing is so shallow the timing is effectively unknown. */
  grazing: boolean
  /**
   * The arc was already under way when the window opened / is still under way
   * when it closes. Its real length is longer than `hours`: a lower bound.
   */
  openStart?: boolean
  openEnd?: boolean
  /** For a dark arc: the bearing of the terrain that is doing the blocking. */
  blockedByBearingDeg?: number
  blockedByElDeg?: number
}

export interface BodyResult {
  body: Body
  arcs: Arc[]
  upHours: number
  downHours: number
  fractionUp: number
  longestDownH: number
  longestDownToleranceH: number
  longestDownArc?: Arc
  /** The longest down arc touches a window edge, so `longestDownH` is a lower bound. */
  longestDownOpen?: boolean
  samples: TrackSample[]
}

/** Both bodies below the skyline at once: no power and no link. */
export interface CompoundEvent {
  startH: number
  endH: number
  hours: number
  openStart?: boolean
  openEnd?: boolean
}

export interface SiteMetrics {
  siteId: string
  windowStartH: number
  windowHours: number
  sun: BodyResult
  earth: BodyResult
  compound: CompoundEvent[]
  worstCompoundH: number
  mask: HorizonMask
  /** Wall-clock milliseconds the server spent on this window's geometry. */
  computeMs: number
  /** The window's opening instant, ISO 8601 UTC, as the server quantised it. */
  windowStartIso?: string
}
