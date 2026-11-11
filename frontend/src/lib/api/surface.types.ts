/**
 * Shapes for the lander tools on a site (ADR-20 to 23). Where the backend's
 * schema models a shape, the name here is an alias of the generated type in
 * `schema.ts`; where the service returns a loose `dict`, the shape is written
 * by hand from `backend/app/api/v1/schemas/{energy,dispersion,mesh}.py`.
 */
import type { components } from './schema'

type S = components['schemas']

export type ProvenanceWord = 'computed' | 'published' | 'entered' | 'assumed'

/** `QuantityOut`: a number with its margin in exactly one form, or the reason it has none. */
export type QuantityDTO = S['QuantityOut']

/** `TimeQuantityOut`: hours after the window start, with UTC copies. */
export type TimeQuantityDTO = S['TimeQuantityOut']

/** The part of `Meta` the surface tools read (the schema's `resolution` and `uncertainty` are not used here). */
export type MetaLiteDTO = Pick<S['Meta'], 'computed_at' | 'engine_version' | 'cache' | 'compute_ms'> & {
  [k: string]: unknown
}

// ---------------------------------------------------------------------------
// Power and temperature: POST /sites/{site_id}/energy
// ---------------------------------------------------------------------------

/** `FigureIn`: a figure with its provenance. A bare number means entered by the caller. */
export type FigureInDTO = S['FigureIn']

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
export type LanderInDTO = S['LanderIn']

/** `EnergyRequest`; the generated type marks defaulted fields required, so they are optional here. */
export type EnergyRequestDTO = Omit<S['EnergyRequest'], 'ground_radius_m'> & { ground_radius_m?: number }

export type BandDTO = S['Band']

export type EnergySeriesDTO = S['EnergySeries']

export type EnergyKeyDTO = S['EnergyKey']

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

// `EnergyResponse` types `inputs`, `model` and `ground` as loose dicts, so this stays hand-written.
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

/** `DispersionRequest`; `samples` has a default, so it is optional here. */
export type DispersionRequestDTO = Omit<S['DispersionRequest'], 'samples'> & { samples?: number }

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

// `DispersionResponse` types most of its blocks as loose dicts, so this stays hand-written.
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
// Aliases of the generated types.
// ---------------------------------------------------------------------------

export type RateMarginDTO = S['RateMargin']

export type PassPointDTO = S['PassPoint']

export type PassBudgetDTO = S['PassBudget']

export type StationFiguresDTO = S['StationFigures']

export type LinkBudgetDTO = S['LinkBudget']

/** The parts of the Contact answer the link budget reads. */
export type ContactBudgetDTO = Pick<S['Contact'], 'link_budget_note' | 'link_budget'> & {
  nodes: Pick<S['Node'], 'id' | 'kind' | 'name'>[]
  links: Pick<S['Link'], 'from' | 'to' | 'stretches' | 'data_rate_kbps' | 'margin_db' | 'passes'>[]
}

// ---- Rovers relaying for each other (the surface mesh, POST /sites/{id}/mesh/simulate) ----

/** `NodeIn` for a fixed node: the service also takes `waypoints` for a moving one, which the panel does not send. */
export type MeshNodeInDTO = Omit<S['NodeIn'], 'position' | 'waypoints'> & { position: S['XY'] }

export type MeshRadioInDTO = S['RadioIn']

export type MeshGuardInDTO = S['GuardIn']

/** `MeshRequest`, with the fixed-node form of `nodes`; the panel always sends `start`, `end` and `step_s` (the wire allows leaving them out). */
export type MeshRequestDTO = Omit<S['MeshRequest'], 'nodes' | 'start' | 'end' | 'step_s'> & {
  start: string | null
  end: string | null
  step_s: number
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

// `MeshResponse` types `nodes`, `links`, `helpers` and `terrain` as loose dicts, so this stays hand-written.
export interface MeshResponseDTO {
  site_id: string
  start: string
  end: string
  step_s: number
  /** The request as the service read it, with defaults filled in. */
  inputs: Record<string, unknown>
  nodes: MeshNodeOutDTO[]
  links: MeshLinkDTO[]
  helpers: MeshHelperDTO[]
  terrain: { products: string[]; post_m: number; vertical_error_m: number }
  timing_ms: Record<string, unknown>
  not_modelled: string[]
  meta: MetaLiteDTO
}
