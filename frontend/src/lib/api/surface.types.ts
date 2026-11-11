/**
 * Shapes for the lander tools on a site (ADR-20, 21, 22), written by hand from
 * the backend's pydantic schemas, which are the source of truth:
 * `backend/app/api/v1/schemas/{energy,dispersion}.py` and `common.py`.
 */

export type ProvenanceWord = 'computed' | 'published' | 'entered' | 'assumed'

/** `QuantityOut`: a number with its margin in exactly one form, or the reason it has none. */
export interface QuantityDTO {
  value: number | null
  unit: string
  provenance: ProvenanceWord
  pm?: number | null
  lo?: number | null
  hi?: number | null
  factor?: number | null
  /** A lower bound: the dates cut it short. */
  open?: boolean
  no_margin_reason?: string | null
  missing_reason?: string | null
  source?: string | null
}

/** `TimeQuantityOut`: hours after the window start, with UTC copies. */
export interface TimeQuantityDTO extends QuantityDTO {
  value_utc?: string | null
  lo_utc?: string | null
  hi_utc?: string | null
}

export interface MetaLiteDTO {
  computed_at: string
  engine_version: string
  cache?: 'hit' | 'miss' | 'bypass' | 'memo'
  compute_ms?: number | null
  [k: string]: unknown
}

// ---------------------------------------------------------------------------
// Power and temperature: POST /sites/{site_id}/energy
// ---------------------------------------------------------------------------

/** `FigureIn`: a figure with its provenance. A bare number means entered by the caller. */
export interface FigureInDTO {
  value: number | string
  provenance?: 'entered' | 'published' | 'assumed'
  source?: string | null
}

export type ArrayGeometry = 'vertical_faces' | 'top_deck_flat' | 'sun_tracking'

export const LANDER_NUMBER_FIELDS = [
  'array_area_m2',
  'face_count',
  'face_azimuth_offset_deg',
  'cell_efficiency',
  'dust_loss_fraction',
  'battery_capacity_wh',
  'initial_soc_fraction',
  'avionics_w',
  'payload_w',
  'load_dissipation_fraction',
  'heater_power_w',
  'heater_setpoint_c',
  'initial_bus_temp_c',
  'operational_min_c',
  'survival_min_c',
  'bus_absorptivity',
  'bus_side_area_m2',
  'bus_top_area_m2',
  'bus_emissivity',
  'regolith_emissivity',
  'regolith_absorptivity',
  'view_factor',
  'base_area_m2',
  'radiator_emissivity',
  'radiator_area_m2',
  'heat_capacity_j_per_k',
] as const

export type LanderNumberField = (typeof LANDER_NUMBER_FIELDS)[number]
export type LanderField = LanderNumberField | 'array_geometry'

/** `LanderIn`: every figure optional on the wire; a missing required one is a 422 naming it. */
export type LanderInDTO = Partial<Record<LanderNumberField, number | FigureInDTO>> & {
  array_geometry?: ArrayGeometry | FigureInDTO
}

export interface EnergyRequestDTO {
  start?: string | null
  end?: string | null
  step_s?: number | null
  lander: LanderInDTO
  lander_example_id?: string | null
  ground_radius_m?: number
}

export interface BandDTO {
  lo: (number | null)[]
  value: (number | null)[]
  /** Null where the warm end of the ground range is unknown. */
  hi: (number | null)[]
}

export interface EnergySeriesDTO {
  /** Seconds from the window start. */
  t_s: number[]
  t_utc: (string | null)[]
  p_gen_w: number[]
  /** 1 while the Sun's centre is above the skyline. */
  lit: number[]
  soc_wh: BandDTO
  t_bus_c: BandDTO
}

export interface EnergyKeyDTO {
  energy_generated: QuantityDTO
  lowest_soc: QuantityDTO
  battery_empty_at: TimeQuantityDTO
  lowest_bus_temperature: QuantityDTO
  hours_below_operational: QuantityDTO
  survival_threshold_crossed_at: TimeQuantityDTO
}

/** One echoed lander figure (a QuantityOut for numbers; value, unit, provenance, source for words). */
export interface EchoedFigureDTO {
  value: number | string | null
  unit?: string
  provenance: ProvenanceWord
  source?: string | null
  pm?: number | null
  lo?: number | null
  hi?: number | null
  no_margin_reason?: string | null
}

export interface GroundRangeDTO {
  lo: number
  hi: number | null
}

export interface EnergyGroundDTO {
  covered: boolean
  reason?: string | null
  radius_m?: number
  source?: string | null
  dark_ground_k?: GroundRangeDTO | null
  lit_ground_cap_k?: GroundRangeDTO | null
  n_triangles?: number | null
  [k: string]: unknown
}

export interface EnergyResponseDTO {
  site_id: string
  start: string | null
  end: string | null
  step_s: number
  inputs: Partial<Record<LanderField, EchoedFigureDTO>>
  model: Record<string, unknown>
  ground: EnergyGroundDTO
  series: EnergySeriesDTO
  key: EnergyKeyDTO
  not_modelled: string[]
  meta: MetaLiteDTO
}

// ---------------------------------------------------------------------------
// Landing ellipse: POST /sites/{site_id}/dispersion
// ---------------------------------------------------------------------------

export interface DispersionRequestDTO {
  /** 3-sigma half-axes in metres; azimuth is the major axis's bearing from true north, clockwise. */
  ellipse: { semi_major_m: number; semi_minor_m: number; azimuth_deg: number }
  lander: { footprint_diameter_m: number; cg_height_m: number; slope_limit_deg: number }
  samples?: number
}

export interface SourceRefDTO {
  name: string
  citation?: string
  url?: string
}

/** k of n points, with the exact 95 % interval for that many. */
export interface PointShareDTO {
  k: number
  n: number
  lo: number
  hi: number
  checked?: boolean
}

export interface ShareBlockDTO {
  limit_deg: number
  baseline_m: number
  share: PointShareDTO
  if_slopes_one_sigma_higher: PointShareDTO
}

export interface SlopeSourceDTO {
  name: string
  label: string
  pgda_5m?: boolean
  fell_back: boolean
  fallback_reason: string | null
  method?: string
  spacing_m?: number
  baseline_m: number
  baseline_note?: string
  vertical_error_m?: number | null
  vertical_error_note?: string
  source?: SourceRefDTO
  [k: string]: unknown
}

export interface IlluminationLayerDTO {
  name: string
  unit: string
  p10: QuantityDTO
  p50: QuantityDTO
  p90: QuantityDTO
  n_points: number
}

export interface IlluminationDTO {
  basis: string
  epoch?: string
  source?: SourceRefDTO
  available: boolean
  reason: string | null
  product?: string
  resolution_m?: number
  sun?: IlluminationLayerDTO
  earth?: IlluminationLayerDTO
  permanent_shadow?: { share: PointShareDTO; n_points: number }
}

export interface HeatmapDTO {
  frame: string
  east_min_m: number
  north_min_m: number
  cell_m: number
  nx: number
  ny: number
  /** Row 0 is the southernmost; null is unknown. */
  slope_deg: (number | null)[][]
  baseline_m: number
  outline: { east_m: number[]; north_m: number[] }
  points: { east_m: number[]; north_m: number[]; slope_deg: (number | null)[] }
  [k: string]: unknown
}

export interface DispersionResponseDTO {
  site_id: string
  inputs: Record<string, unknown>
  slope_source: SlopeSourceDTO
  slope: {
    unit: string
    baseline_m: number
    n_points: number
    n_with_slope: number
    p10: QuantityDTO
    p50: QuantityDTO
    p90: QuantityDTO
    margin_note?: string
  }
  tip_over: { angle: QuantityDTO; formula?: string }
  shares: { above_slope_limit: ShareBlockDTO; above_tip_over: ShareBlockDTO; basis: string }
  illumination: IlluminationDTO
  heatmap: HeatmapDTO
  sources: SourceRefDTO[]
  not_modelled: string[]
  meta: MetaLiteDTO
}

// ---------------------------------------------------------------------------
// Link budget on the Contact step (ADR-20): `Contact.link_budget`,
// `Link.passes[].{edge,peak}`, `link_budget_note` in schemas/contact.py.
// The generated schema predates these, so they are typed here.
// ---------------------------------------------------------------------------

export interface RateMarginDTO {
  /** A data rate the mission states, as stated. */
  rate_kbps: QuantityDTO
  /** Eb/N0 over the required Eb/N0 at that rate: `lo` adverse weather and tolerances, `hi` clear and favourable. */
  margin_db: QuantityDTO
}

export interface PassPointDTO {
  /** `edge`: the weaker end of the pass; `peak`: the sample of highest elevation. */
  at: 'edge' | 'peak'
  elevation_deg: QuantityDTO
  range_km: QuantityDTO
  path_loss_db: QuantityDTO
  atmosphere_db: QuantityDTO
  g_over_t_dbk: QuantityDTO
  /** The highest rate that keeps the stated margin, with weather and tolerances as `lo` and `hi`. */
  max_rate_kbps: QuantityDTO
  margins: RateMarginDTO[]
}

export interface PassBudgetDTO {
  edge: PassPointDTO
  peak: PassPointDTO
}

export interface StationFiguresDTO {
  id: string
  configuration: string
  gain_dbi: QuantityDTO
  t_amw_k: QuantityDTO
  zenith_clear_db: QuantityDTO
  zenith_adverse_db: QuantityDTO
  /** The handbook module the figures are from. */
  module: string
  source_urls: string[]
}

export interface LinkBudgetDTO {
  method: string
  band: string
  frequency_mhz: QuantityDTO
  eirp_dbw: QuantityDTO
  required_ebn0_db: QuantityDTO
  required_margin_db: QuantityDTO
  stated_rates_kbps: QuantityDTO[]
  stations: StationFiguresDTO[]
  /** Stations with no published figures: no budget is given there. */
  stations_without_figures: string[]
  not_modelled: string[]
}

/** The parts of the Contact answer the link budget reads. */
export interface ContactBudgetDTO {
  nodes: { id: string; kind: string; name: string }[]
  links: {
    from: string
    to: string
    stretches: { start: string; end: string; open_start: boolean; open_end: boolean }[]
    data_rate_kbps?: QuantityDTO | null
    margin_db?: QuantityDTO | null
    /** One per stretch, in the same order; null when no budget ran for this station. */
    passes?: PassBudgetDTO[] | null
  }[]
  link_budget_note: string | null
  link_budget?: LinkBudgetDTO | null
}

// ---- Rovers relaying for each other (the surface mesh, POST /sites/{id}/mesh/simulate) ----

export interface MeshNodeInDTO {
  id: string
  name?: string
  position: { east_m: number; north_m: number }
  antenna_height_m: number
  battery_capacity_wh: number
  initial_soc_fraction: number
  own_traffic_bps: number
  may_help: boolean
  earth_uplink_bps?: number
  earth_uplink_power_w?: number
}

export interface MeshRadioInDTO {
  frequency_hz: number
  tx_power_w: number
  forwarding_tx_power_w: number
  tx_efficiency: number
  antenna_gain_dbi: number
  bandwidth_hz: number
  noise_figure_db: number
  snr_threshold_db: number
  eps_r: number
  polarisation: 'horizontal' | 'vertical'
}

export interface MeshGuardInDTO {
  soc_cutoff_fraction: number
  quota_share_per_lunar_day: number
  max_forwarding_power_w: number
  buffer_bytes: number
}

export interface MeshRequestDTO {
  start: string | null
  end: string | null
  step_s: number
  loss_threshold_s: number
  radio: MeshRadioInDTO
  guard: MeshGuardInDTO
  nodes: MeshNodeInDTO[]
}

export type MeshSight = 'clear' | 'uncertain' | 'blocked'

export interface MeshLongestDTO {
  direct_only: QuantityDTO
  with_mesh: QuantityDTO
  with_mesh_if_uncertain_links_hold: QuantityDTO
  direct_only_starts_utc: string | null
  with_mesh_starts_utc: string | null
  with_mesh_if_uncertain_links_hold_starts_utc?: string | null
  basis: string
}

export interface MeshNodeOutDTO {
  id: string
  name: string
  may_help: boolean
  positions: { east_m: number; north_m: number }[]
  time_in_state_h: Record<string, number>
  longest_without_path_to_earth: MeshLongestDTO
}

export interface MeshLinkDTO {
  a: string
  b: string
  /** The stretch of the dates this entry covers; a pair can have several. */
  start_s: number
  end_s: number
  start_utc: string
  end_utc: string
  distance_m: number
  terrain_sight: MeshSight
  terrain_fresnel: MeshSight
  path_loss_db: number
  snr_db: number
  radio_closes: boolean
  usable: boolean
}

export interface MeshHelperDTO {
  id: string
  forwarded_mb: QuantityDTO
  dropped_mb: QuantityDTO
  buffered_at_end_mb: QuantityDTO
  energy_spent_wh: QuantityDTO
  minimum_state_of_charge: QuantityDTO
  refusals: unknown[]
  refused_hours_by_rule: Record<string, number>
}

export interface MeshResponseDTO {
  site_id: string
  start: string
  end: string
  step_s: number
  nodes: MeshNodeOutDTO[]
  links: MeshLinkDTO[]
  helpers: MeshHelperDTO[]
  terrain: { products: string[]; post_m: number; vertical_error_m: number }
  not_modelled: string[]
  meta: { computed_at: string; engine_version: string }
}
