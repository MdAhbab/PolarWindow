/**
 * Wire format → the types the components already consume.
 *
 * The design is finished and its components take `SiteMetrics`, `Arc`,
 * `TrackSample` and `HorizonMask` as defined in `../types.ts`. Rather than
 * rewrite thirty components to speak the API's dialect, every difference is
 * resolved here, once:
 *
 *   seconds        → hours          (the wire is SI; the product reads in hours)
 *   ISO 8601       → tH             (hours from the window start)
 *   snake_case     → camelCase
 *   parallel arrays→ TrackSample[]
 *   number[]       → Float32Array   (maskElevationAt indexes a typed array)
 *
 * One place to get wrong, and one place to test — `adapters.test.ts` pins the
 * unit conversions and the window-edge flags, so a units bug here fails a test
 * rather than a judge.
 */
import type {
  Arc,
  Body,
  BodyResult,
  CompoundEvent,
  HorizonMask,
  Site,
  SiteMetrics,
  TrackSample,
} from '../types'
import type { ArcDTO, HorizonDTO, MetaDTO, MetricsDTO, SiteBriefDTO, TimelineDTO, WindowsDTO } from './client'

const S_PER_H = 3600

export const toHours = (seconds: number): number => seconds / S_PER_H

/**
 * Snap a window the way the server does, so the client's cache key is the
 * server's cache key.
 *
 * The start floors to the step grid and the *length* rounds to a whole number
 * of steps. Without this the client keys on the raw instants: two windows the
 * server treats as one become two cache entries and two requests.
 */
export function quantiseWindow(
  startMs: number,
  endMs: number,
  stepS: number,
): { start: string; end: string } {
  const stepMs = stepS * 1000
  // The server's grid is anchored at 2000-01-01T00:00Z, not the Unix epoch;
  // the two coincide only for steps that divide 946,684,800 s.
  const anchor = Date.UTC(2000, 0, 1)
  const s = anchor + Math.floor((startMs - anchor) / stepMs) * stepMs
  const steps = Math.max(1, Math.round((endMs - startMs) / stepMs))
  const iso = (ms: number) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, 'Z')
  return { start: iso(s), end: iso(s + steps * stepMs) }
}

/** Hours from `start` to `iso`. The frontend's whole time axis is this unit. */
export function hoursFrom(start: string, iso: string): number {
  return (Date.parse(iso) - Date.parse(start)) / 3_600_000
}

/**
 * Uncertainty, in the form the UI branches on.
 *
 * `grazing` and `coverage < 1` are different claims and stay separate:
 * grazing means an edge cannot be timed, partial coverage means terrain is
 * missing. Collapsing them into one "uncertain" flag would lose which one to
 * tell the user about.
 */
export interface Uncertainty {
  demVerticalErrorM: number
  demResolutionM: number
  coverage: number
  horizonElDeg: number
  /** null when at least one crossing is a graze — a stronger claim than a big number. */
  edgeTimingH: number | null
  grazing: boolean
  partialCoverage: boolean
  penumbraSunDeg: number
  penumbraEarthDeg: number
  notes: string[]
}

export interface Meta {
  computedAt: string
  engineVersion: string
  cache: 'hit' | 'miss' | 'bypass'
  computeMs: number | null
  resolution: {
    azimuthDeg: number
    azimuthCount: number
    timeStepS: number
    maxRangeM: number
    demProduct: string
    demResolutionM: number
    ephemeris: string
    frame: string
  }
  uncertainty: Uncertainty
}

export function adaptMeta(m: MetaDTO): Meta {
  const u = m.uncertainty
  return {
    computedAt: m.computed_at,
    engineVersion: m.engine_version,
    cache: m.cache,
    computeMs: m.compute_ms ?? null,
    resolution: {
      azimuthDeg: m.resolution.azimuth_deg,
      azimuthCount: m.resolution.azimuth_count,
      timeStepS: m.resolution.time_step_s,
      maxRangeM: m.resolution.max_range_m,
      demProduct: m.resolution.dem_product,
      demResolutionM: m.resolution.dem_resolution_m,
      ephemeris: m.resolution.ephemeris,
      frame: m.resolution.frame,
    },
    uncertainty: {
      demVerticalErrorM: u.dem_vertical_error_m,
      demResolutionM: u.dem_resolution_m,
      coverage: u.coverage,
      horizonElDeg: u.horizon_el_deg,
      edgeTimingH: u.edge_timing_s === null ? null : toHours(u.edge_timing_s),
      grazing: u.grazing,
      partialCoverage: u.coverage < 0.999,
      penumbraSunDeg: u.penumbra_sun_deg,
      penumbraEarthDeg: u.penumbra_earth_deg,
      notes: u.notes,
    },
  }
}

export function adaptHorizon(dto: HorizonDTO): HorizonMask {
  return {
    elDeg: new Float32Array(dto.el_deg),
    rangeM: new Float32Array(dto.range_m),
    tolDeg: new Float32Array(dto.tol_deg),
    maxElDeg: dto.max_el_deg,
    maxElBearingDeg: dto.max_el_bearing_deg,
  }
}

function adaptArc(dto: ArcDTO, body: Body, windowStart: string): Arc {
  const startH = hoursFrom(windowStart, dto.start)
  return {
    body,
    up: dto.up,
    startH,
    endH: startH + toHours(dto.duration_s),
    hours: toHours(dto.duration_s),
    toleranceH: toHours(dto.tolerance_s),
    ...(dto.start_tolerance_s != null ? { startToleranceH: toHours(dto.start_tolerance_s) } : {}),
    ...(dto.end_tolerance_s != null ? { endToleranceH: toHours(dto.end_tolerance_s) } : {}),
    grazing: dto.grazing,
    openStart: dto.open_start,
    openEnd: dto.open_end,
    ...(dto.blocked_by_bearing_deg !== null && dto.blocked_by_bearing_deg !== undefined
      ? {
          blockedByBearingDeg: dto.blocked_by_bearing_deg,
          blockedByElDeg: dto.blocked_by_el_deg ?? undefined,
        }
      : {}),
  }
}

/**
 * Visibility state, as the backend reports it.
 *
 * Three values, not two: the Sun's disc is about 0.27 deg across seen from the
 * Moon and Earth's is nearly 1 deg, so there is a real band where the body is
 * partly occluded — measured at roughly 10 % of samples on a polar site. The
 * design already distinguishes "blocked" (hatch at +45 deg) from "uncertain"
 * (hatch at -45 deg); penumbral takes the uncertain hatch. No new colour.
 */
export const DARK = 0
export const PENUMBRAL = 1
export const LIT = 2

function adaptSamples(
  dto: TimelineDTO,
  body: 'sun' | 'earth',
  windowStart: string,
): TrackSample[] {
  const t = dto.t_s
  const b = dto[body]
  const startOffsetH = hoursFrom(windowStart, dto.start)
  const out: TrackSample[] = new Array(t.length)
  for (let i = 0; i < t.length; i++) {
    out[i] = {
      tH: startOffsetH + toHours(t[i]),
      azDeg: b.az_deg[i],
      elDeg: b.el_deg[i],
      maskElDeg: b.mask_el_deg[i],
      marginDeg: b.margin_deg[i],
    }
  }
  return out
}

/** Per-sample visibility state, kept alongside the samples rather than inside
 *  them so `TrackSample` stays the shape the existing components expect. */
export function visibilityStates(dto: TimelineDTO, body: 'sun' | 'earth'): Int8Array {
  return Int8Array.from(dto[body].state)
}

function adaptBody(
  windows: WindowsDTO,
  body: Body,
  samples: TrackSample[],
): BodyResult {
  const w = windows[body]
  const arcs = w.arcs.map((a) => adaptArc(a, body, windows.start))
  const longest = arcs
    .filter((a) => !a.up)
    .reduce<Arc | undefined>((best, a) => (!best || a.hours > best.hours ? a : best), undefined)
  return {
    body,
    arcs,
    upHours: toHours(w.up_s),
    downHours: toHours(w.down_s),
    fractionUp: w.fraction_up,
    longestDownH: toHours(w.longest_down_s),
    longestDownToleranceH: toHours(w.longest_down_tolerance_s),
    longestDownArc: longest,
    longestDownOpen: w.longest_down_open,
    samples,
  }
}

export interface AdaptedSite {
  metrics: SiteMetrics
  meta: Meta
  /** The server's autonomy packet, in hours. Never recomputed on the client. */
  autonomy: Autonomy
  /** Present only for the focused site; the others travel as arcs only. */
  sunStates?: Int8Array
  earthStates?: Int8Array
}

/**
 * Assemble the shape `SiteMetrics` consumers expect from the three endpoints
 * that carry its parts.
 *
 * `timeline` is optional by design: only the focused site needs its 2,835
 * samples per body, exactly as the old Worker only sent them for one site.
 */
export function adaptSite(
  siteId: string,
  windows: WindowsDTO,
  metrics: MetricsDTO,
  mask: HorizonMask,
  timeline?: TimelineDTO,
): AdaptedSite {
  const windowStartH = 0
  const windowHours = hoursFrom(windows.start, windows.end)
  const sunSamples = timeline ? adaptSamples(timeline, 'sun', windows.start) : []
  const earthSamples = timeline ? adaptSamples(timeline, 'earth', windows.start) : []

  const compound: CompoundEvent[] = windows.compound.map((c) => {
    const startH = hoursFrom(windows.start, c.start)
    return {
      startH,
      endH: startH + toHours(c.duration_s),
      hours: toHours(c.duration_s),
      openStart: c.open_start,
      openEnd: c.open_end,
    }
  })

  return {
    metrics: {
      siteId,
      windowStartH,
      windowHours,
      sun: adaptBody(windows, 'sun', sunSamples),
      earth: adaptBody(windows, 'earth', earthSamples),
      compound,
      worstCompoundH: toHours(windows.worst_compound_s),
      mask,
      computeMs: metrics.meta.compute_ms ?? 0,
      windowStartIso: windows.start,
    },
    meta: adaptMeta(metrics.meta),
    autonomy: adaptAutonomy(metrics),
    sunStates: timeline ? visibilityStates(timeline, 'sun') : undefined,
    earthStates: timeline ? visibilityStates(timeline, 'earth') : undefined,
  }
}

/**
 * The autonomy packet, in hours, exactly as the server computed it.
 *
 * The client used to recompute this with its own copy of the 20 % margin, so
 * the "h of full autonomy" figure and the copy describing it could drift from
 * the server's own number. It now only converts units.
 */
export interface Autonomy {
  worstCompoundH: number
  requiredAutonomyH: number
  marginFraction: number
  /** The battery carries the longest night, whatever the radio is doing. */
  survivalNeededH: number
  compoundInsideDark: boolean
  /** The night that sizes the battery is cut by a window edge: a lower bound. */
  survivalOpen: boolean
  worstCompoundOpen: boolean
}

export function adaptAutonomy(m: MetricsDTO): Autonomy {
  return {
    worstCompoundH: toHours(m.autonomy.worst_compound_s),
    requiredAutonomyH: toHours(m.autonomy.required_autonomy_s),
    marginFraction: m.autonomy.margin_fraction,
    survivalNeededH: toHours(m.autonomy.survival_needed_s),
    compoundInsideDark: m.autonomy.compound_inside_dark,
    survivalOpen: m.autonomy.survival_open,
    worstCompoundOpen: m.autonomy.worst_compound_open,
  }
}

/**
 * A site brief, in the shape the rail and the map already draw.
 *
 * `summary` may be null — a site whose horizon has not been surveyed. It is
 * carried through as null, never zeroed: a zero is a measurement, and absence
 * is not. The UI has an uncertain state for exactly this.
 */
export interface AdaptedSiteBrief {
  site: Site
  summary: {
    sunHours: number
    earthHours: number
    longestDark: number
    longestBlackout: number
    sunFraction: number
    earthFraction: number
    worstCompoundH: number
    grazing: boolean
    longestDarkOpen: boolean
    longestBlackoutOpen: boolean
    referenceWindowStart: string
    referenceWindowEnd: string
  } | null
}

export function adaptSiteBrief(dto: SiteBriefDTO): AdaptedSiteBrief {
  return {
    site: {
      id: dto.id,
      code: dto.code,
      name: dto.name,
      latDeg: dto.lat_deg,
      lonDeg: dto.lon_deg,
      elevM: dto.elev_m,
      note: dto.note,
      searchKind: dto.search_kind,
    },
    summary: dto.summary
      ? {
          sunHours: toHours(dto.summary.sunlit_s),
          earthHours: toHours(dto.summary.earth_contact_s),
          longestDark: toHours(dto.summary.longest_dark_s),
          longestBlackout: toHours(dto.summary.longest_blackout_s),
          sunFraction: dto.summary.sun_fraction_up,
          earthFraction: dto.summary.earth_fraction_up,
          worstCompoundH: toHours(dto.summary.worst_compound_s),
          grazing: dto.summary.grazing,
          longestDarkOpen: dto.summary.longest_dark_open,
          longestBlackoutOpen: dto.summary.longest_blackout_open,
          referenceWindowStart: dto.summary.reference_window_start,
          referenceWindowEnd: dto.summary.reference_window_end,
        }
      : null,
  }
}
