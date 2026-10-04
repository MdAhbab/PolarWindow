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
import type {
  ArcDTO,
  CalendarDTO,
  HorizonDTO,
  MetaDTO,
  MetricsDTO,
  MissionBriefDTO,
  MissionDetailDTO,
  PublishedDateDTO,
  SiteBriefDTO,
  TimelineDTO,
  WindowsDTO,
} from './client'

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
  /**
   * False when no elevation model covers the site (a CLPS target outside
   * 80°S): the skyline is a smooth sphere. The numbers are still real SPICE
   * geometry and are still shown, in the uncertain state.
   */
  terrainModelled: boolean
  notes: string[]
}

export interface Meta {
  computedAt: string
  engineVersion: string
  cache: 'hit' | 'miss' | 'bypass' | 'memo'
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
      // Absent on a v1 payload: every v1 site was inside the polar model.
      terrainModelled: u.terrain_modelled ?? true,
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
      kind: dto.kind ?? 'candidate',
      coordinateRule: dto.coordinate_rule ?? 'derived_open_sky',
      terrainModelled: dto.terrain_modelled ?? true,
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

// ---------------------------------------------------------------------------
// Contract v2: CLPS missions
// ---------------------------------------------------------------------------

export type MissionStatus = MissionBriefDTO['status']
export type InstrumentType = MissionBriefDTO['payload_types'][number]
export type DatePrecision = PublishedDateDTO['precision']
export type CoordinateKind = NonNullable<MissionBriefDTO['target']>['coordinate_kind']
export type SurfaceBasis = MissionBriefDTO['surface_window']['basis']
export type MissionRegion = NonNullable<MissionBriefDTO['region']>

/**
 * A date as a source published it.
 *
 * `asPublished` is the phrase the UI shows ("late 2027"). `startMs` and `endMs`
 * are the span the precision implies, used only to *place* the date on the
 * programme timeline -- a year-precision date is stored as 1 January, and
 * drawing it as that day would claim a precision the source never gave.
 */
export interface PublishedDate {
  iso: string
  precision: DatePrecision
  asPublished: string
  startMs: number
  endMs: number
}

/** The end of the span a published date with this precision covers. */
export function precisionSpanEnd(startMs: number, precision: DatePrecision): number {
  const d = new Date(startMs)
  const y = d.getUTCFullYear()
  const m = d.getUTCMonth()
  switch (precision) {
    case 'second':
      return startMs + 1_000
    case 'minute':
      return startMs + 60_000
    case 'day':
      return Date.UTC(y, m, d.getUTCDate() + 1)
    case 'month':
      return Date.UTC(y, m + 1, 1)
    case 'quarter':
      return Date.UTC(y, m + 3, 1)
    case 'year':
      return Date.UTC(y + 1, 0, 1)
  }
}

export function adaptPublishedDate(dto: PublishedDateDTO | null): PublishedDate | null {
  if (!dto) return null
  const startMs = Date.parse(dto.date)
  return {
    iso: dto.date,
    precision: dto.precision,
    asPublished: dto.as_published,
    startMs,
    endMs: precisionSpanEnd(startMs, dto.precision),
  }
}

export interface MissionTarget {
  name: string
  latDeg: number
  /** Degrees east, 0–360, as the API sends it. */
  lonDeg: number
  coordinateKind: CoordinateKind
  sourceUrl: string
  featureId: number | null
}

export interface SurfaceWindow {
  startIso: string | null
  endIso: string | null
  basis: SurfaceBasis
  note: string
}

/** The four numbers at the target over its surface window, in hours. Null, never zeros. */
export interface MissionSummary {
  windowStartIso: string
  windowEndIso: string
  sunHours: number
  earthHours: number
  longestDarkH: number
  longestBlackoutH: number
  sunFraction: number
  earthFraction: number
  longestDarkOpen: boolean
  longestBlackoutOpen: boolean
  grazing: boolean
  terrainModelled: boolean
}

export interface Mission {
  id: string
  name: string
  vehicleName: string | null
  taskOrder: string | null
  provider: string | null
  lander: string | null
  status: MissionStatus
  region: MissionRegion | null
  targetName: string | null
  target: MissionTarget | null
  launch: PublishedDate | null
  landing: PublishedDate | null
  payloadTypes: InstrumentType[]
  payloadCount: number
  siteId: string | null
  terrainModelled: boolean | null
  surfaceWindow: SurfaceWindow
  summary: MissionSummary | null
  /** Field names no source confirms. The UI prints "Unconfirmed" for them, never a guess. */
  unconfirmedFields: string[]
  dataVersion: string
}

export interface Payload {
  id: string
  name: string
  acronym: string | null
  organisation: string | null
  instrumentTypes: InstrumentType[]
  purpose: string
  sourceUrl: string
  unconfirmed: boolean
}

export interface MissionSource {
  url: string
  title: string
  publisher: string
  /** ISO date the source was last read. */
  accessed: string
}

export interface TargetSite {
  id: string
  code: string
  name: string
  latDeg: number
  lonDeg: number
  elevM: number | null
  kind: 'candidate' | 'mission_target'
  coordinateRule: 'derived_open_sky' | 'published'
  terrainModelled: boolean
  sourceNote: string
}

export interface MissionDetail extends Mission {
  outcomeNote: string
  endOfMission: PublishedDate | null
  plannedSurfaceDays: number | null
  payloads: Payload[]
  sources: MissionSource[]
  notes: string[]
  /** Published landing ellipse as [lat, lon] vertices; null when none is published. */
  ellipseRing: [number, number][] | null
  site: TargetSite | null
  /** Rovers the lander carries, as the rover line-of-sight endpoint knows them; empty when none. */
  rovers: { id: string; name: string; organisation: string | null }[]
  meta: Meta
}

export function adaptMission(dto: MissionBriefDTO): Mission {
  const t = dto.target
  const sw = dto.surface_window
  const sm = dto.summary
  return {
    id: dto.id,
    name: dto.name,
    vehicleName: dto.vehicle_name,
    taskOrder: dto.task_order,
    provider: dto.provider,
    lander: dto.lander,
    status: dto.status,
    region: dto.region,
    targetName: dto.target_name,
    target: t
      ? {
          name: t.name,
          latDeg: t.lat_deg,
          lonDeg: t.lon_deg,
          coordinateKind: t.coordinate_kind,
          sourceUrl: t.source_url,
          featureId: t.feature_id ?? null,
        }
      : null,
    launch: adaptPublishedDate(dto.launch),
    landing: adaptPublishedDate(dto.landing),
    payloadTypes: dto.payload_types,
    payloadCount: dto.payload_count,
    siteId: dto.site_id,
    terrainModelled: dto.terrain_modelled,
    surfaceWindow: { startIso: sw.start, endIso: sw.end, basis: sw.basis, note: sw.note },
    summary: sm
      ? {
          windowStartIso: sm.window_start,
          windowEndIso: sm.window_end,
          sunHours: toHours(sm.sunlit_s),
          earthHours: toHours(sm.earth_contact_s),
          longestDarkH: toHours(sm.longest_dark_s),
          longestBlackoutH: toHours(sm.longest_blackout_s),
          sunFraction: sm.sun_fraction_up,
          earthFraction: sm.earth_fraction_up,
          longestDarkOpen: sm.longest_dark_open,
          longestBlackoutOpen: sm.longest_blackout_open,
          grazing: sm.grazing,
          terrainModelled: sm.terrain_modelled,
        }
      : null,
    unconfirmedFields: dto.unconfirmed_fields,
    dataVersion: dto.data_version,
  }
}

/**
 * The mission's rovers as the service lists them (contact_service `_rovers`):
 * payloads that move first, then the listed rovers, each once. The first is
 * the one the line-of-sight endpoint answers for by default.
 */
function missionRovers(dto: MissionDetailDTO): MissionDetail['rovers'] {
  const out = new Map<string, MissionDetail['rovers'][number]>()
  for (const p of dto.payloads) if (p.instrument_types.includes('rover_mobility')) out.set(p.id, { id: p.id, name: p.name, organisation: p.organisation })
  for (const r of dto.lifecycle?.rovers ?? []) if (!out.has(r.id)) out.set(r.id, { id: r.id, name: r.name, organisation: r.organisation })
  return [...out.values()]
}

export function adaptMissionDetail(dto: MissionDetailDTO): MissionDetail {
  return {
    ...adaptMission(dto),
    outcomeNote: dto.outcome_note,
    endOfMission: adaptPublishedDate(dto.end_of_mission),
    plannedSurfaceDays: dto.planned_surface_days,
    payloads: dto.payloads.map((p) => ({
      id: p.id,
      name: p.name,
      acronym: p.acronym,
      organisation: p.organisation,
      instrumentTypes: p.instrument_types,
      purpose: p.purpose,
      sourceUrl: p.source_url,
      unconfirmed: p.unconfirmed,
    })),
    sources: dto.sources.map((x) => ({
      url: x.url,
      title: x.title,
      publisher: x.publisher,
      accessed: x.accessed,
    })),
    notes: dto.notes,
    ellipseRing: dto.ellipse_ring
      ? dto.ellipse_ring.filter((v) => v.length >= 2).map((v) => [v[0], v[1]] as [number, number])
      : null,
    site: dto.site
      ? {
          id: dto.site.id,
          code: dto.site.code,
          name: dto.site.name,
          latDeg: dto.site.lat_deg,
          lonDeg: dto.site.lon_deg,
          elevM: dto.site.elev_m,
          kind: dto.site.kind,
          coordinateRule: dto.site.coordinate_rule,
          terrainModelled: dto.site.terrain_modelled,
          sourceNote: dto.site.source_note,
        }
      : null,
    rovers: missionRovers(dto),
    meta: adaptMeta(dto.meta),
  }
}

/** The latest date any of a mission's sources was read: what "Unconfirmed" is "as of". */
export function latestAccessed(sources: MissionSource[]): string | null {
  let best: string | null = null
  for (const s of sources) if (!best || s.accessed > best) best = s.accessed
  return best
}

// ---------------------------------------------------------------------------
// Contract v2: the calendar behind the month strip
// ---------------------------------------------------------------------------

export interface CalendarBucket {
  startIso: string
  endIso: string
  startMs: number
  endMs: number
  sunFraction: number
  earthFraction: number
  sunHours: number
  earthHours: number
  longestDarkH: number
  /** The bucket's edge, not the terrain, ended the longest night: a lower bound. */
  longestDarkOpen: boolean
  longestBlackoutH: number
  longestBlackoutOpen: boolean
}

export interface Calendar {
  siteId: string
  startIso: string
  endIso: string
  bucket: 'day' | 'month'
  stepS: number
  items: CalendarBucket[]
  meta: Meta
}

export function adaptCalendar(dto: CalendarDTO): Calendar {
  return {
    siteId: dto.site_id,
    startIso: dto.start,
    endIso: dto.end,
    bucket: dto.bucket,
    stepS: dto.step_s,
    items: dto.items.map((b) => ({
      startIso: b.start,
      endIso: b.end,
      startMs: Date.parse(b.start),
      endMs: Date.parse(b.end),
      sunFraction: b.sun_fraction_up,
      earthFraction: b.earth_fraction_up,
      sunHours: toHours(b.sunlit_s),
      earthHours: toHours(b.earth_contact_s),
      longestDarkH: toHours(b.longest_dark_s),
      longestDarkOpen: b.longest_dark_open,
      longestBlackoutH: toHours(b.longest_blackout_s),
      longestBlackoutOpen: b.longest_blackout_open,
    })),
    meta: adaptMeta(dto.meta),
  }
}
