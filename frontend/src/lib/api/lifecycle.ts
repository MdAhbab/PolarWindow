import type { components } from './schema'

/**
 * The lifecycle sections' wire shapes, as `docs/lifecycle-api.md` writes them
 * (contract v1, 2026-09-27, plus the requests under its *Changes*).
 *
 * Written out here, stricter than the generated `schema.ts` in one way: every
 * Quantity field is present (null when empty), which `client.ts` guarantees
 * by filling any the server leaves out. For every route the backend already
 * serves, `ContractChecks` at the end holds these to the generated types, so
 * a shape that drifts fails the build rather than a screen.
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
  /**
   * False for an item prefilled from the mission record that nobody has
   * entered a state for: it shows "not entered yet", and is not in `counts`.
   */
  state_known: boolean
  /** The moves the state machine allows from here (ADR-17). */
  allowed_next: ReadyState[]
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
  /** Items nobody has entered a state for yet (not counted as not started). */
  not_entered: number
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
  /** What was done ("moved", "created"), when the server says. */
  action?: string
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
  note?: string
}

/** Requested in the contract's *Changes* (2026-09-27). */
export interface RiskScaleDTO {
  id: string
  name: string
  source_url: string | null
  likelihood: { level: number; words: string }[]
  consequence: { category: RiskCategory; levels: { level: number; words: string }[] }[]
  notes?: string[]
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
  since?: string | null
  /** How the counts should be read ("counts, never a chance of success"). */
  note?: string
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
  /** Null when there is no trip (`source: "none"`). */
  start: string | null
  end: string | null
  /** What part of the trip NASA's reconstruction covers; the numbers describe only that part. */
  coverage_note?: string | null
  /** The stretches NASA's reconstruction covers (never open-ended); between two is a gap with no data. */
  covered?: StretchDTO[]
  samples:{ t: string; earth_km: number; moon_km: number; light: 'lit' | 'penumbral' | 'dark'; heard: boolean }[]
  shadow: StretchDTO[]
  heard: StretchDTO[]
  numbers: { sunlight_h: QuantityDTO; heard_h: QuantityDTO; longest_shadow_h: QuantityDTO; longest_unheard_h: QuantityDTO }
  burns: { t: string; name: string; dv_m_s: QuantityDTO }[]
  /** Why `burns` is empty, when it is. */
  burns_note?: string | null
  moon_pull: { equal_pull_km: number; sphere_of_influence_km: number; t_equal_pull: string | null } | null
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
  /** The dates this answer covers, and how they were chosen. */
  start?: string
  end?: string
  window_note?: string | null
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
  bookings: { station: string; start: string; end: string; entered_by: string; note?: string | null }[]
  /** One-way light time between the Moon and Earth over these dates, seconds. */
  light_time_s?: { min: number; max: number }
  /** When the longest message wait begins. */
  longest_wait_from?: string | null
  /** Time in sunlight over the same dates, for "dark and out of contact". */
  sun_total_h?: QuantityDTO
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
  /** The provider as people know it ("NOAA SWPC"); the backend adds it to the contract's shape. */
  provider_name?: string
  product: string
  /** The pad or buoy the product is for, if any. */
  location?: string | null
  /** When the product was last fetched or checked. */
  last_ok: string | null
  /** The time the data itself refers to (model run, issue time, newest reading). */
  data_time?: string | null
  /** How old the data is, in seconds; null if there is none yet. */
  age_s: number | null
  stale: boolean
  staleness_budget_s?: number
  next_run: string | null
  /** Failed attempts in a row. */
  errors: number | string | string[] | null
  last_error?: string | null
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

// ---------------------------------------------------------------------------
// Held to the generated schema (docs/openapi.json via `npm run codegen`)
// ---------------------------------------------------------------------------

type S = components['schemas']
/** Compiles only when `A` fits `B`. */
type Fits<A extends B, B> = A
/**
 * A field with a default is optional in the generated types but always sent
 * (the API serialises defaults), so the checks compare it as present.
 */
type Present<T> = T extends (infer U)[]
  ? Present<U>[]
  : T extends object
    ? { [K in keyof T]-?: Present<Exclude<T[K], undefined>> }
    : T

/**
 * Each served shape must fit the one written here. A field the backend
 * renames, drops or retypes breaks the build on this line.
 */
export type ContractChecks = [
  Fits<Present<S['SectionStatus']>, SectionStatusDTO>,
  Fits<Present<S['ReadyItem']>, ReadyItemDTO>,
  Fits<Present<S['Milestone']>, MilestoneDTO>,
  Fits<Present<S['Risk']>, RiskDTO>,
  Fits<Present<S['RiskScale']>, RiskScaleDTO>,
  Fits<Present<S['Part']>, PartDTO>,
  Fits<Present<S['PartImpact']>, PartImpactDTO>,
  Fits<Present<S['Lesson']>, LessonDTO>,
  Fits<Present<S['LandingHistory']>, LandingHistoryDTO>,
  Fits<Present<S['HistoryEntry']>, AuditEntryDTO>,
  Fits<Present<S['LifecycleMeta']>, LifecycleMetaDTO>,
  Fits<Present<S['FeedOut']>, FeedDTO>,
  Fits<Present<S['JobRefOut']>, JobRefDTO>,
  Fits<Present<S['UserOut']>, UserDTO>,
  Fits<Present<S['QuantityOut']>, QuantityDTO>,
  Fits<Present<S['Parameter']>, ParameterDTO>,
  Fits<Present<S['Contact']>, ContactDTO>,
  Fits<Present<S['Trip']>, TripDTO>,
  // `counts` is typed as a plain map in the schema; its keys are checked in the fixture tests.
  Fits<Present<Omit<S['Ready'], 'counts'>>, Omit<ReadyDTO, 'counts'>>,
]
