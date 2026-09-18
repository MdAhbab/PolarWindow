export type Body = 'sun' | 'earth'

export type Face = 'planner' | 'educator' | 'public'

export type MetricKey = 'sunHours' | 'earthHours' | 'longestDark' | 'longestBlackout'

/** A terrain feature, placed relative to the site in the local ENU frame. */
export interface TerrainFeature {
  kind: 'ridge' | 'massif' | 'knoll' | 'crater'
  /** Compass bearing of the feature's centre, degrees from north, clockwise. */
  bearingDeg: number
  /** Ground range from the site to the feature's centre, metres. */
  rangeM: number
  /** Height above the site's own plane, metres. Negative for a crater floor. */
  heightM: number
  /** Extent across the line of sight, metres. This is what sets the angular span. */
  widthM: number
  /** Extent along the line of sight, metres. */
  depthM: number
}

export interface TerrainSpec {
  seed: number
  /** Amplitude of the fractal roughness, metres. */
  roughnessM: number
  features: TerrainFeature[]
}

export interface Site {
  id: string
  code: string
  name: string
  /** Selenographic latitude, degrees. Negative is south. */
  latDeg: number
  /** Selenographic longitude, degrees east. */
  lonDeg: number
  /** Elevation relative to the 1737.4 km reference sphere, metres. */
  elevM: number
  note: string
  terrain: TerrainSpec
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
  /** Half-width of the timing error on this arc, hours. */
  toleranceH: number
  /** True when the crossing is so shallow the timing is effectively unknown. */
  grazing: boolean
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
  samples: TrackSample[]
}

/** Both bodies below the skyline at once: no power and no link. */
export interface CompoundEvent {
  startH: number
  endH: number
  hours: number
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
  /** Wall-clock milliseconds the ray-cast and the track sampling took. */
  computeMs: number
}

export interface MissionWindow {
  /** Hours from the model epoch at which the window opens. */
  startH: number
  hours: number
  /** Calendar date the window opens, for display only. */
  startISO: string
}
