/**
 * The lifecycle sections' wire shapes, exactly as `docs/lifecycle-api.md`
 * writes them (contract v1, 2026-09-27, plus the requests under its
 * *Changes*).
 *
 * Written by hand only until the backend's OpenAPI document carries these
 * routes; then each type here becomes an alias of `Schemas[...]` from the
 * generated `schema.ts`, and a shape that drifted fails the build here.
 * Components never read these: `lib/lifecycle/adapt.ts` turns them into what
 * the screens draw.
 */

export type Provenance = 'computed' | 'published' | 'entered' | 'assumed'

/** ADR-9: exactly one margin form, or `no_margin_reason`; a null value has `missing_reason`. */
export interface QuantityDTO {
  value: number | null
  unit: string
  provenance: Provenance
  pm: number | null
  lo: number | null
  hi: number | null
  factor: number | null
  /** A lower bound: the dates cut it short. */
  open: boolean
  no_margin_reason: string | null
  missing_reason: string | null
  /** Who entered it, or the URL it was published at. */
  source: string | null
}

/** A share of model runs, with its exact 95 % interval (fractions, 0 to 1). */
export interface ShareDTO {
  k: number
  n: number
  lo: number
  hi: number
  checked: boolean
}

export interface SourceRefDTO {
  name: string
  url: string | null
  issued_at: string | null
  fetched_at: string | null
  licence: string | null
  snapshot_id: number | null
}

export interface LifecycleMetaDTO {
  computed_at: string
  uncertainty: { kind: 'composite'; parts: { source: string; note: string }[] }
  engines: Record<string, string>
  sources: SourceRefDTO[]
  stale: boolean
  compute_ms: number | null
}

export interface StretchDTO {
  start: string
  end: string
  open_start: boolean
  open_end: boolean
}

export interface JobRefDTO {
  job_id: number
  status: 'queued' | 'running' | 'done' | 'failed'
  progress: number | null
  message: string
  poll_after_s: number
  assessment_id?: number | null
}

export interface SectionDTO<T> {
  data: T
  meta: LifecycleMetaDTO
}

export type SectionId = 'ready' | 'launch' | 'trip' | 'landing' | 'contact' | 'return'
export type SectionState = 'available' | 'computing' | 'needs_input' | 'not_applicable' | 'no_data'

export interface SectionStatusDTO {
  section: SectionId
  state: SectionState
  summary: string
  as_of: string | null
}

// ---------------------------------------------------------------------------
// Ready
// ---------------------------------------------------------------------------

export type ReadyState =
  | 'not_started'
  | 'in_build'
  | 'in_test'
  | 'test_passed'
  | 'delivered'
  | 'integrated'
  | 'verified_on_lander'
  | 'ready'
  | 'blocked'

export type ItemKind =
  | 'lander'
  | 'payload'
  | 'rover'
  | 'launch_vehicle'
  | 'range'
  | 'ground_booking'
  | 'relay_agreement'
  | 'ops_team'
  | 'licence'

export type TestKind = 'vibration' | 'shock' | 'thermal_vacuum' | 'emi_emc' | 'functional'

export interface ReadyItemDTO {
  id: string
  kind: ItemKind
  name: string
  organisation: string | null
  state: ReadyState
  blocked_reason: string | null
  changed_at: string | null
  changed_by: string | null
  evidence_url: string | null
  source: 'public' | 'entered'
  tests: { kind: TestKind; result: 'passed' | 'failed' | 'not_done'; report_url: string | null; date: string | null }[]
}

export interface MilestoneDTO {
  id: string
  name: string
  date: QuantityDTO
  done: boolean
  source: string | null
}

export type RiskCategory = 'safety' | 'technical' | 'cost' | 'schedule'

export interface RiskDTO {
  id: string
  title: string
  cause: string
  consequence_text: string
  scale_id: string
  ratings: { category: RiskCategory; likelihood: number; consequence: number }[]
  trend: 'rising' | 'steady' | 'falling'
  owner: string | null
  mitigation: string | null
  links: { readiness_items: string[]; parts: string[]; lessons: string[] }
}

export interface ReadyDTO {
  counts: Record<ReadyState, number>
  items: ReadyItemDTO[]
  milestones: MilestoneDTO[]
  risks: RiskDTO[]
  parts: { total: number; spares: number; lost: number; damaged: number; failed: number }
  lessons_available: number
  lessons_adopted: number
}

export interface AuditEntryDTO {
  at: string
  by: string
  before: unknown
  after: unknown
  note: string | null
}

export type PartStatus = 'installed' | 'spare' | 'in_test' | 'damaged' | 'failed' | 'lost'

/** Requested in the contract's *Changes* (2026-09-27). */
export interface PartDTO {
  id: string
  name: string
  part_number: string | null
  serial: string | null
  parent_item_id: string | null
  status: PartStatus
  location: string | null
  changed_at: string | null
  changed_by: string | null
}

export interface PartImpactDTO {
  stops_working: { id: string; name: string; kind: string }[]
}

/** Requested in the contract's *Changes* (2026-09-27). */
export interface RiskScaleDTO {
  id: string
  name: string
  source_url: string | null
  likelihood: { level: number; words: string }[]
  consequence: { category: RiskCategory; levels: { level: number; words: string }[] }[]
}

export interface RiskScalesDTO {
  default_id: string
  scales: RiskScaleDTO[]
}

export interface LandingAttemptDTO {
  mission: string
  agency: string
  date: string
  outcome: string
  cause: string | null
  source_url: string | null
}

export interface LandingHistoryDTO {
  attempts: LandingAttemptDTO[]
  counts: { attempts: number; landed_working: number; landed_tipped_or_partial: number; failed: number }
}

export interface LessonDTO {
  id: string
  text: string
  from_mission: string
  year: number
  source_url: string | null
  checklist_item: string | null
  /** Requested: whether this mission has adopted it. */
  adopted?: boolean
}

// ---------------------------------------------------------------------------
// Launch
// ---------------------------------------------------------------------------

export interface OpportunityDTO {
  id: string
  pad_id: string
  pad_name: string
  vehicle_id: string
  /** Unit "s since epoch": a launch time with its ± in seconds. */
  t0: QuantityDTO
  kind: 'instantaneous' | 'window'
  window_open: string | null
  window_close: string | null
  transfer: { type: 'direct' | 'phasing_loops'; flight_days: QuantityDTO; orbit_wait_days: QuantityDTO }
  landing: { time: QuantityDTO; sun_elevation_deg: QuantityDTO; sunlight_after_h: QuantityDTO; earth_up: boolean }
  weather: 'forecast' | 'climatology' | 'none'
}

export interface LaunchCalendarDTO {
  pads: { id: string; name: string; lat_deg: number; lon_deg: number; operator: string }[]
  opportunities: OpportunityDTO[]
  landing_rule: {
    sun_elevation_min_deg: QuantityDTO
    sun_elevation_max_deg: QuantityDTO
    earth_required: boolean
    note: string
  }
  published_t0: QuantityDTO | null
  /** Requested: the vehicle whose limits apply. */
  vehicle_id?: string | null
}

export type ModelSystem = 'GEFS' | 'ECMWF-ENS' | 'AIFS-ENS'

export interface RuleRowDTO {
  id: string
  text: string
  source_url: string
  class: 'model' | 'proxy' | 'observation'
  limit: QuantityDTO
  per_system: { system: ModelSystem; share: ShareDTO | null; missing_reason: string | null }[]
  one_forecast: { system: 'NWS' | 'HRRR' | 'GEOS-FP'; value: QuantityDTO; over: boolean }[]
  disagreement: boolean
  observed: { state: 'clear' | 'seen' | 'no_data'; detail: string } | null
  climatology: { share: number; years: string; source: string } | null
}

export interface LaunchWeatherDTO {
  t0: string
  lead_time_h: number
  rules: RuleRowDTO[]
  official: {
    probability_pct: number
    concerns: string[]
    pdf_url: string
    entered_by: string
    entered_at: string
  } | null
  space_weather_now: { kp: QuantityDTO; proton_10mev_pfu: QuantityDTO; xray_class: string | null; alerts: string[] }
  range_conflicts: { name: string; t0: string; pad: string }[]
}

// ---------------------------------------------------------------------------
// Trip
// ---------------------------------------------------------------------------

export interface TripDTO {
  source: 'flown' | 'designed' | 'none'
  none_reason: string | null
  start: string
  end: string
  samples: { t: string; earth_km: number; moon_km: number; light: 'lit' | 'penumbral' | 'dark'; heard: boolean }[]
  shadow: StretchDTO[]
  heard: StretchDTO[]
  numbers: { sunlight_h: QuantityDTO; heard_h: QuantityDTO; longest_shadow_h: QuantityDTO; longest_unheard_h: QuantityDTO }
  burns: { t: string; name: string; dv_m_s: QuantityDTO }[]
  moon_pull: { equal_pull_km: number; sphere_of_influence_km: number; t_equal_pull: string | null }
  radiation: {
    belt_hours: QuantityDTO
    fluence_gt10mev: QuantityDTO
    gcr_dose_mgy_day: QuantityDTO
    screening_note: string
    confirm_in: string[]
  } | null
}

// ---------------------------------------------------------------------------
// Contact
// ---------------------------------------------------------------------------

export interface NodeDTO {
  id: string
  kind: 'station' | 'relay' | 'lander' | 'rover' | 'earth'
  name: string
  operator: string | null
  status: 'operating' | 'planned' | 'not_launched'
  orbit: 'real' | 'planned' | null
  launch_note: string | null
}

export interface LinkDTO {
  from: string
  to: string
  stretches: StretchDTO[]
  data_rate_kbps: QuantityDTO | null
  margin_db: QuantityDTO | null
}

export interface ContactDTO {
  nodes: NodeDTO[]
  links: LinkDTO[]
  numbers: {
    direct_h: QuantityDTO
    via_relay_h: QuantityDTO
    either_h: QuantityDTO
    station_hears_h: QuantityDTO
    longest_unheard_h: QuantityDTO
    longest_message_wait_min: QuantityDTO
    dark_and_unheard_h: QuantityDTO
  }
  relays: { id: string; name: string; adds_h: QuantityDTO; status: string }[]
  link_budget_note: string | null
  bookings: { station: string; start: string; end: string; entered_by: string }[]
}

export interface RoverSightDTO {
  viewshed_tile: string | null
  out_of_sight_share: QuantityDTO
  longest_out_of_sight_m: QuantityDTO
  resolvable: boolean
  reason: string | null
}

// ---------------------------------------------------------------------------
// Return
// ---------------------------------------------------------------------------

export interface ZoneDTO {
  lat_deg: number
  lon_deg: number
  pm_km: number
}

export interface ReturnDTO {
  booster: {
    landing: 'droneship' | 'land' | 'expended' | 'unknown'
    zone: ZoneDTO | null
    wave_height_m: QuantityDTO | null
    wind_m_s: QuantityDTO | null
    limits: { wave_height_m: QuantityDTO | null; wind_m_s: QuantityDTO | null }
    hazard_area_seen: boolean | null
  } | null
  capsule: {
    applicable: boolean
    reason: string | null
    zone: ZoneDTO | null
    wave_height_m: QuantityDTO | null
    wind_m_s: QuantityDTO | null
    daylight: boolean | null
  } | null
}

// ---------------------------------------------------------------------------
// Data sources, parameters, people
// ---------------------------------------------------------------------------

export interface FeedDTO {
  provider: string
  product: string
  last_ok: string | null
  age_s: number | null
  stale: boolean
  next_run: string | null
  errors: number | string | string[] | null
  licence: string | null
  breaker: 'closed' | 'open' | 'half_open'
}

export interface FeedsDTO {
  feeds: FeedDTO[]
}

export interface ParameterDTO {
  id: string
  name: string
  value: QuantityDTO
  note: string | null
  changed_by: string | null
  changed_at: string | null
}

export interface UserDTO {
  id: number
  name: string
  team: string | null
}
