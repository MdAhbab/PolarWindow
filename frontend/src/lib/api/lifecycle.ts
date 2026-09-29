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
  /** `time` is the landing; for a designed opportunity its `lo`/`hi` are the allowed landing stretch it falls in. */
  landing: { time: QuantityDTO; sun_elevation_deg: QuantityDTO; sunlight_after_h: QuantityDTO; earth_up: boolean }
  weather: 'forecast' | 'climatology' | 'none'
  /** What the weather rules can show for this opportunity, and why there are no forecast numbers when there are none. */
  weather_note: string
  /** How `t0` was worked out: again from NASA's reconstruction, designed from the pad, or as published. */
  basis: 'reconstructed' | 'designed' | 'published'
  /** One or two plain sentences: how, and anything unusual (a coast longer than any flown one). */
  note: string
  /** The climb's direction; missing, with the reason, for a flown launch. */
  azimuth_deg: QuantityDTO
  dv_tli_m_s: QuantityDTO
  coast_min: QuantityDTO
}

export interface LaunchCalendarDTO {
  /** Set, with no opportunities, when there is nothing to work from (cancelled; pad, vehicle or spot not published). */
  none_reason: string | null
  /** The dates searched; null for a flown mission (its one launch). */
  start: string | null
  end: string | null
  /** Which dates were used, in words ("The next 90 days.", "The launch it flew."). */
  dates_note: string | null
  pads: { id: string; name: string; lat_deg: number | null; lon_deg: number | null; operator: string }[]
  opportunities: OpportunityDTO[]
  landing_rule: {
    sun_elevation_min_deg: QuantityDTO
    sun_elevation_max_deg: QuantityDTO
    earth_required: boolean
    note: string
  }
  published_t0: QuantityDTO | null
  /** The vehicle whose limits apply. */
  vehicle_id: string | null
}

export type ModelSystem = 'GEFS' | 'ECMWF-ENS' | 'AIFS-ENS'

export interface RuleRowDTO {
  id: string
  text: string
  source_url: string
  class: 'model' | 'proxy' | 'observation'
  limit: QuantityDTO
  /** Units a limit can be entered in, the published one first; empty when none is published (any unit is taken). */
  units: string[]
  /** The team's note with an entered limit. */
  limit_note: string | null
  per_system: { system: ModelSystem; share: ShareDTO | null; missing_reason: string | null }[]
  one_forecast: { system: 'NWS' | 'HRRR' | 'GEOS-FP'; value: QuantityDTO; over: boolean }[]
  disagreement: boolean
  observed: { state: 'clear' | 'seen' | 'no_data'; detail: string } | null
  /** How often the limit was broken in past years at the launch's month and hour (wind rules with a known limit). */
  climatology: { share: number; years: string; source: string } | null
}

/** A limit the team entered for a vehicle (`GET /vehicles/{id}/limits`), with its note. */
export interface EnteredLimitDTO {
  rule_id: string
  value: number
  unit: string
  note: string | null
  entered_by: string
  entered_at: string
}

export interface VehicleLimitsDTO {
  vehicle_id: string
  limits: EnteredLimitDTO[]
}

/** The official launch forecast as the team entered it, quoted as issued. */
export interface OfficialForecastDTO {
  id: number
  probability_pct: number
  concerns: string[]
  pdf_url: string
  entered_by: string
  entered_at: string
}

/** `PUT /launch/official-forecast` answers with the forecast as stored (the same shape the weather answer carries). */
export type StoredForecastDTO = OfficialForecastDTO

/** `DELETE /launch/official-forecast`: the forecast taken back, and the one entered before it (now shown), if any. */
export interface RemovedForecastDTO {
  removed_id: number
  official: StoredForecastDTO | null
}

export interface LaunchWeatherDTO {
  t0: string
  /** Negative for a launch in the past. */
  lead_time_h: number
  pad_id: string
  vehicle_id: string | null
  /** One sentence on what is covered. */
  note: string
  rules: RuleRowDTO[]
  official: OfficialForecastDTO | null
  range_conflicts: { name: string; t0: string; pad: string }[]
  /** Where `range_conflicts` come from, or why they are not known. */
  range_note: string
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
  covered: StretchDTO[]
  samples:{ t: string; earth_km: number; moon_km: number; light: 'lit' | 'penumbral' | 'dark'; heard: boolean }[]
  shadow: StretchDTO[]
  heard: StretchDTO[]
  numbers: { sunlight_h: QuantityDTO; heard_h: QuantityDTO; longest_shadow_h: QuantityDTO; longest_unheard_h: QuantityDTO }
  burns: { t: string; name: string; dv_m_s: QuantityDTO }[]
  /** Why `burns` is empty, when it is. */
  burns_note?: string | null
  /** A budget for corrections on the way under assumed errors; null with `corrections_note` saying why. */
  corrections: CorrectionsDTO | null
  corrections_note: string | null
  moon_pull: { equal_pull_km: number; sphere_of_influence_km: number; t_equal_pull: string | null } | null
  /** A screening estimate for a flown trip; null with `radiation_note` saying why. */
  radiation: RadiationDTO | null
  radiation_note?: string | null
}

/** Screening only: belt maps good to a factor of two, cosmic rays ±30 %, past events as measured at 1 AU. */
export interface RadiationDTO {
  /** Factor 2; `open` = the climb out before NASA's reconstruction is not counted (a lower bound). */
  belt_hours: QuantityDTO
  belt_passes: number
  /** Electrons above 1 MeV, per cm², whole trip. */
  electron_fluence_gt1mev: QuantityDTO
  /** Trapped protons above 10 MeV, per cm², whole trip. */
  fluence_gt10mev: QuantityDTO
  /** mGy a day in silicon, before shielding. */
  gcr_dose_mgy_day: QuantityDTO
  surface: { site_id: string; open_sky: QuantityDTO; gcr_dose_mgy_day: QuantityDTO } | null
  surface_note: string | null
  sep_events: { t: string; link: string }[]
  sep_note: string
  scenarios: { id: string; name: string; fluence_gt10mev: QuantityDTO; fluence_gt30mev: QuantityDTO; source_url: string }[]
  screening_note: string
  confirm_in: string[]
}

/** `GET /space-weather`: what the Sun is doing now, as NOAA SWPC and NASA DONKI report it. */
export interface SpaceWeatherDTO {
  now: {
    kp: QuantityDTO
    proton_10mev_pfu: QuantityDTO
    proton_100mev_pfu: QuantityDTO
    xray_class: string | null
    /** Why there is no X-ray class; null when there is one. */
    xray_missing_reason: string | null
    solar_wind_km_s: QuantityDTO
    bz_nt: QuantityDTO
    /** SWPC headlines of the last 24 h. */
    alerts: string[]
    /** Why the alert list is not shown; null when it is current, so `[]` means no alert in 24 h. */
    alerts_missing_reason: string | null
  }
  outlook: {
    issued: string | null
    days: string | null
    /** SWPC's day 1-3 chance of a radiation storm (S1 or greater), verbatim. */
    s1_or_greater_pct: number[] | null
    kp_max_expected: number | null
    /** The three-day forecast, word for word. */
    text: string | null
    missing_reason: string | null
  }
  donki: {
    cme: { id: string; start: string | null; speed_m_s: number | null; earth_arrival_estimates: string[] | null; link: string | null }[]
    flares: { id: string; peak: string | null; class: string | null; link: string | null }[]
    sep: { id: string; time: string | null; instruments: (string | null)[] | null; link: string | null }[]
    /** How many DONKI gave per kind over `days` (the lists keep the newest 20); null for a kind not shown. */
    counts: { cme: number | null; flares: number | null; sep: number | null }
    days: number | null
    missing_reason: string | null
  }
  note: string
}

/** Never a prediction: sizes of the corrections under the listed assumed errors, over many runs. */
export interface CorrectionsDTO {
  label: string
  burns: { name: string; t: string; p95_m_s: QuantityDTO; p99_m_s: QuantityDTO }[]
  total_p95_m_s: QuantityDTO
  /** `lo`/`hi`: its 95 % interval. */
  total_p99_m_s: QuantityDTO
  /** The same total worked out linearly, as a check. */
  linear_p99_m_s: QuantityDTO
  /** Median; `lo`/`hi` the 1st and 99th percentile. */
  arrival_altitude_km: QuantityDTO
  runs: number
  /** Runs with no close pass of the Moon. */
  missed: number
  assumptions: { what: string; value: string }[]
  plan_note: string
  flown_note: string
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

/** A relay's published or assumed orbit: heights above the mean radius. */
export interface RelayOrbitDTO {
  periapsis_km: QuantityDTO
  apoapsis_km: QuantityDTO
  inclination_deg: QuantityDTO
  arg_periapsis_deg: QuantityDTO
  period_h: QuantityDTO
}

export type RelayLaunchStatus = 'operating' | 'planned' | 'not_launched' | 'launched_not_operating'

export interface RelayRowDTO {
  id: string
  name: string
  /** Time it adds to direct contact, as a range. */
  adds_h: QuantityDTO
  /** Its launch note, or its status when there is none. */
  status: string
  /** Time the lander can reach Earth through it, as a range (net-4). */
  via_h?: QuantityDTO
  launch_status?: RelayLaunchStatus
  /** False for a relay added to compare (`?relay=`), not planned for this mission. */
  for_this_mission?: boolean
  orbit?: RelayOrbitDTO
  orbit_note?: string | null
  /** What was swept to get the ranges; null when nothing was worked out. */
  sweep_note?: string | null
}

/** A real lunar orbiter's passes over the landing spot: geometry only, never a relay service (F2). */
export interface OrbiterDTO {
  id: string
  name: string
  operator: string | null
  naif_id: number | null
  note: string
  /** The recorded JPL Horizons trajectory. */
  source: { name: string; url: string | null; issued_at: string | null; fetched_at: string | null; licence: string | null; snapshot_id: number | null } | null
  /** The part of the dates the trajectory covers. */
  covered: StretchDTO | null
  /** Above the landing spot's terrain skyline. */
  passes: (StretchDTO & { max_elevation_deg: number | null })[]
  pass_count: number
  in_view_h: QuantityDTO
  longest_pass_min: QuantityDTO
  longest_gap_h: QuantityDTO
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
  relays: RelayRowDTO[]
  /** With a relay in the graph: the two waits without it. Null otherwise. */
  direct_only?: { longest_unheard_h: QuantityDTO; longest_message_wait_min: QuantityDTO } | null
  /** One plain sentence on what "through the relay" means. */
  relay_note?: string | null
  link_budget_note: string | null
  /** Real lunar orbiters' passes over the landing spot: they could see the lander, and relay for none. */
  orbiters?: OrbiterDTO[]
  /** Why the orbiters that could see the lander are not relays for it. */
  orbiters_note?: string | null
  bookings: { station: string; start: string; end: string; entered_by: string; note?: string | null }[]
  /** One-way light time between the Moon and Earth over these dates, seconds. */
  light_time_s?: { min: number; max: number }
  /** When the longest message wait begins. */
  longest_wait_from?: string | null
  /** Time in sunlight over the same dates, for "dark and out of contact". */
  sun_total_h?: QuantityDTO
}

/** Whether a rover at a spot and the lander can see each other; uncertain when the terrain's error could tip it. */
export type SightState = 'clear' | 'blocked' | 'uncertain'

/**
 * The line of sight around the lander, ray by ray: `sight[i][j]` is the state
 * at `bearings_deg[i]` (clockwise from north) and `ranges_m[j]` from the
 * lander. `radio` is the same for the first Fresnel zone, which needs more room.
 */
export interface ViewshedDTO {
  bearings_deg: number[]
  ranges_m: number[]
  sight: SightState[][]
  radio: SightState[][]
}

export interface RoverSightDTO {
  /** The rover, the rays and what the shares are over (F5). */
  rover?: { id: string; name: string } | null
  share_basis?: 'drive' | 'ground' | null
  radius_m?: number | null
  /** Where the lander is: the centre of the viewshed and of its tiles. Null with no map. */
  lander?: { lat_deg: number; lon_deg: number } | null
  viewshed?: ViewshedDTO | null
  /** The address of the map's tiles under the API base, with `{z}`, `{x}` and `{y}`; `?layer=` is `terrain`, `sight` or `radio`. */
  viewshed_tile: string | null
  out_of_sight_share: QuantityDTO
  /** Percent where the radio path is not clear (first Fresnel zone). */
  radio_not_clear_share?: QuantityDTO
  /** Antenna heights and the radio frequency: assumed unless given. */
  assumptions?: { lander_antenna_m: QuantityDTO; rover_antenna_m: QuantityDTO; radio_mhz: QuantityDTO } | null
  /** The elevation model the rays are read from. */
  terrain?: { product: string; post_m: number; vertical_error_m: number } | null
  /** What clear, blocked and uncertain mean here, in one plain paragraph. */
  note?: string | null
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
  /** Null when the zone's size is not published. */
  pm_km: number | null
}

/** The team's sea limits: always a Quantity, missing with its reason until entered. */
export interface SeaLimitsDTO {
  wave_height_m: QuantityDTO
  wind_m_s: QuantityDTO
}

export interface ReturnDTO {
  /** Null for a cancelled delivery, or when the launch vehicle is not published. */
  booster: {
    landing: 'droneship' | 'land' | 'expended' | 'unknown'
    /** Null when its position is not published (a droneship's is not). */
    zone: ZoneDTO | null
    /** Plain words: where it came down, or the vehicle's practice and the flown CLPS landings. */
    note: string
    /** Null for a landing on land. */
    wave_height_m: QuantityDTO | null
    wind_m_s: QuantityDTO | null
    limits: SeaLimitsDTO
    hazard_area_seen: boolean | null
  } | null
  /** Null for a cancelled delivery. */
  capsule: {
    applicable: boolean
    reason: string | null
    zone: ZoneDTO | null
    wave_height_m: QuantityDTO | null
    wind_m_s: QuantityDTO | null
    daylight: boolean | null
    limits: SeaLimitsDTO
    /** The capsule entry model against OSIRIS-REx's landing; null when that check has not been run here. */
    model_check: CapsuleModelCheckDTO | null
  } | null
}

/** The capsule entry model flown from OSIRIS-REx's reconstructed entry state, against where its capsule landed. */
export interface CapsuleModelCheckDTO {
  case: string
  distance_km: number
  /** Over the published drag range. */
  distance_range_km: number[]
  limit_km: number
  passed: boolean
  /** The mission's own simulation. */
  mission_team_km: number
  /** The 99 % area, long by wide. */
  ellipse_99_km: number[]
  measured_inside_ellipse: boolean
  checked_at: string
  sources: string[]
  /** Plain words. */
  note: string
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
  Fits<Present<S['RelayRow']>, RelayRowDTO>,
  Fits<Present<S['Orbiter']>, OrbiterDTO>,
  Fits<Present<S['RoverOut']>, RoverSightDTO>,
  Fits<Present<S['Trip']>, TripDTO>,
  Fits<Present<S['LaunchCalendar']>, LaunchCalendarDTO>,
  Fits<Present<S['LaunchWeather']>, LaunchWeatherDTO>,
  Fits<Present<S['Return']>, ReturnDTO>,
  Fits<Present<S['CapsuleModelCheck']>, CapsuleModelCheckDTO>,
  Fits<Present<S['OfficialForecast']>, OfficialForecastDTO>,
  Fits<Present<S['OfficialForecastOut']>, StoredForecastDTO>,
  Fits<Present<S['OfficialForecastRemoved']>, RemovedForecastDTO>,
  Fits<Present<S['Radiation']>, RadiationDTO>,
  Fits<Present<S['SpaceWeather']>, SpaceWeatherDTO>,
  Fits<Present<S['VehicleLimits']>, VehicleLimitsDTO>,
  // `counts` is typed as a plain map in the schema; its keys are checked in the fixture tests.
  Fits<Present<Omit<S['Ready'], 'counts'>>, Omit<ReadyDTO, 'counts'>>,
]
