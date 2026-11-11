/**
 * The wire contract for the "experience" release (docs/experience-plan.md):
 * projects the team enters, files read into a project form, what-if scenarios
 * for steps that have no published data, the quick Ask chat, and the activity
 * tray. Types only: no fetch, no hooks.
 *
 * This file is the single source of truth for these shapes. The backend's
 * Pydantic schemas mirror it field for field (snake_case, as sent), and each
 * frontend feature writes its own hooks against it. Change a shape here first.
 *
 * Reused from elsewhere: `JobRefDTO`, `SectionDTO`, `SectionId`,
 * `SectionState`, `LaunchCalendarDTO`, `TripDTO`, `ContactDTO`, `ReturnDTO`
 * (./lifecycle) and `MissionDetailDTO`, `MissionBriefDTO`, `AgentDTO` (./client).
 */

import type { AgentDTO, MissionBriefDTO, MissionDetailDTO } from './client'
import type {
  ContactDTO,
  JobRefDTO,
  LaunchCalendarDTO,
  ReturnDTO,
  SectionDTO,
  SectionId,
  SectionState,
  TripDTO,
} from './lifecycle'

// ---------------------------------------------------------------------------
// Missions gain two fields (both always present from this release on)
// ---------------------------------------------------------------------------

/** `catalogue`: a CLPS record compiled from published sources. `project`: entered by the team. */
export type MissionOrigin = 'catalogue' | 'project'

/** Added to MissionBrief and MissionDetail. */
export interface MissionOriginFields {
  origin: MissionOrigin
  /** Who entered a project; null for a catalogue record. */
  owner_name: string | null
}

/**
 * A mission source gains `kind`. For `entered` and `file` the `url` is the
 * empty string and must be drawn as words, never as a link.
 */
export type SourceKind = 'published' | 'entered' | 'file'

// ---------------------------------------------------------------------------
// Projects: GET /projects/options, GET|POST /projects, GET|PUT|DELETE /projects/{id}
// ---------------------------------------------------------------------------

export type DatePrecision = 'second' | 'minute' | 'day' | 'month' | 'quarter' | 'year'

/** A date as the team knows it. `as_published` is written by the server when omitted. */
export interface ProjectDateIn {
  /** ISO date or datetime (UTC). */
  date: string
  precision: DatePrecision
  as_published?: string | null
}

/** Exactly one of `site_id` or the three coordinate fields. */
export interface ProjectTargetIn {
  /** An existing site (candidate or mission target): its skyline is already built. */
  site_id?: string | null
  name?: string | null
  lat_deg?: number | null
  /** Degrees east, 0-360 (−180..180 is accepted and normalised). */
  lon_deg?: number | null
}

export interface ProjectPayloadIn {
  name: string
  acronym?: string | null
  organisation?: string | null
  /** InstrumentType values (see lib/missions.ts INSTRUMENT_TYPES). */
  instrument_types: string[]
  purpose?: string | null
}

export interface ProjectLifecycleIn {
  /** Catalogue ids from /projects/options. */
  vehicle_id?: string | null
  pad_id?: string | null
  transfer_type?: 'direct' | 'phasing_loops' | 'low_energy' | 'unknown' | null
  flight_days?: number | null
  lunar_orbit_days?: number | null
  sun_el_min_deg?: number | null
  sun_el_max_deg?: number | null
  bands?: string[]
  ground_stations?: string[]
  relays?: string[]
  mass_kg?: number | null
  returns?: 'none' | 'sample_capsule' | 'crew' | null
}

/** The project form. Only `name` is required; everything else may be left unknown. */
export interface ProjectIn {
  name: string
  provider?: string | null
  lander?: string | null
  /** The spacecraft's own name ("Athena"). */
  vehicle_name?: string | null
  task_order?: string | null
  status?: 'planned' | 'in_transit' | 'operating' | 'completed'
  target?: ProjectTargetIn | null
  launch?: ProjectDateIn | null
  landing?: ProjectDateIn | null
  end_of_mission?: ProjectDateIn | null
  planned_surface_days?: number | null
  lifecycle?: ProjectLifecycleIn | null
  payloads?: ProjectPayloadIn[]
  notes?: string[]
  /** The file reading this form was filled from, so each field keeps its evidence. */
  intake_id?: number | null
}

/** POST /projects (201) and PUT /projects/{id} (200). */
export interface ProjectSavedDTO {
  mission: MissionDetailDTO & MissionOriginFields
  /**
   * Set when the target is a new coordinate: its skyline is being built
   * (job kind `site_build`). Until it is done, Surface and Contact say so.
   */
  site_job: JobRefDTO | null
}

/** GET /projects: the team's own projects, newest first. */
export interface ProjectListDTO {
  items: (MissionBriefDTO & MissionOriginFields)[]
  total: number
}

/** DELETE /projects/{id} */
export interface ProjectDeletedDTO {
  id: string
  deleted: true
}

export interface OptionDTO {
  value: string
  label: string
  /** A short second line: an operator, a place, coordinates. */
  hint?: string | null
}

/** GET /projects/options: every choice the form offers, from the catalogues. Public. */
export interface ProjectOptionsDTO {
  vehicles: OptionDTO[]
  pads: OptionDTO[]
  /** Existing sites a project can target, candidates first. */
  sites: (OptionDTO & { lat_deg: number; lon_deg: number; kind: 'candidate' | 'mission_target' })[]
  providers: string[]
  landers: string[]
  instrument_types: OptionDTO[]
  relays: OptionDTO[]
  /** Largest upload POST /projects/intake takes, in bytes. */
  max_upload_bytes: number
  /** File kinds the reader accepts, as extensions without the dot. */
  accepted_extensions: string[]
  /** False with no model key: files are read by rules (dates, names, coordinates) only. */
  model_reading: boolean
}

// ---------------------------------------------------------------------------
// Intake: POST /projects/intake?filename=<name>  (raw body, the file's bytes;
// Content-Type is the file's media type). Named session. 200 with a draft.
// ---------------------------------------------------------------------------

/** Dotted paths into ProjectIn: "name", "landing.date", "lifecycle.vehicle_id", "payloads". */
export type ProjectFieldPath = string

export interface IntakeFieldDTO {
  /** `stated`: the file says it. `inferred`: worked out from what it says. `not_found`: left empty. */
  confidence: 'stated' | 'inferred' | 'not_found'
  /** The words in the file this was read from, at most ~240 characters. */
  evidence: string | null
  /** 1-based page (PDF) or line (text), when known. */
  page: number | null
  /** Why an inferred value was chosen, or why nothing was found. */
  note: string | null
}

export interface IntakeDTO {
  intake_id: number
  filename: string
  media_type: string
  size_bytes: number
  /** `model`: read by the AI model. `rules`: read by pattern rules (no model, or it did not answer). */
  method: 'model' | 'rules'
  model: string | null
  /** The form, filled with what was found. Unknown fields are absent or null, never guessed. */
  draft: ProjectIn
  /** One entry per form field the reader looked for, found or not. */
  fields: Record<ProjectFieldPath, IntakeFieldDTO>
  /** Plain sentences: a scanned page that could not be read, two dates that disagree. */
  warnings: string[]
  /** How many characters of text were read from the file. */
  characters_read: number
}

// ---------------------------------------------------------------------------
// Scenarios: a what-if for a step with no published data. Every value in a
// scenario is labelled with where it came from, and no scenario value is ever
// written into the mission's record.
// ---------------------------------------------------------------------------

/** The steps a scenario can work out. Ready is entered by people, never assumed. */
export type ScenarioSection = Exclude<SectionId, 'ready'>

/**
 * Where an assumed value came from, in the order they are tried:
 * `you` (typed or said), `published` (the mission record), `live` (fetched
 * from a data source for this scenario), `default` (a precedent or catalogue
 * value, named in `note`).
 */
export type AssumptionBasis = 'you' | 'published' | 'live' | 'default'

/** The fields a scenario may assume. */
export type AssumptionFieldId =
  | 'vehicle_id'
  | 'pad_id'
  | 'site_id'
  | 'launch_from'
  | 'launch_to'
  | 'landing_date'
  | 'surface_days'
  | 'transfer_type'
  | 'sun_el_min_deg'
  | 'sun_el_max_deg'
  | 'relays'

export interface AssumptionSourceDTO {
  name: string
  url: string | null
  /** When a live value was fetched. */
  fetched_at: string | null
}

export interface AssumptionDTO {
  field: AssumptionFieldId
  label: string
  /** A catalogue id, an ISO date, a number, or a list of relay ids. */
  value: string | number | string[] | null
  /** The value in words: a vehicle's name, a date as written, "14 days". */
  display: string
  unit: string | null
  basis: AssumptionBasis
  source: AssumptionSourceDTO | null
  /** For `default`: which precedent or rule gave it. For `live`: what the source said. */
  note: string | null
}

export interface AssumptionFieldDTO {
  field: AssumptionFieldId
  label: string
  /** One sentence: what this decides. */
  help: string
  kind: 'choice' | 'multi_choice' | 'date' | 'number'
  unit: string | null
  options: OptionDTO[] | null
  min: number | null
  max: number | null
  /** What is used when the scenario does not set it, with its basis. Null: it must be given. */
  default: AssumptionDTO | null
  /** The steps this field feeds. */
  sections: ScenarioSection[]
}

export interface GapDTO {
  section: ScenarioSection
  state: SectionState
  /** What the mission record lacks for this step, in plain words; empty when nothing. */
  missing: { field: AssumptionFieldId; label: string; why: string }[]
  /** True when assuming the missing fields would let the step be worked out. */
  can_explore: boolean
}

/** GET /missions/{id}/scenarios/gaps. Public. */
export interface ScenarioGapsDTO {
  mission_id: string
  gaps: GapDTO[]
  fields: AssumptionFieldDTO[]
  /** Worked out ahead of time: open at once. */
  presets: ScenarioBriefDTO[]
  /** Example prompts for this mission, to show as chips. */
  suggestions: string[]
}

/** POST /missions/{id}/scenarios/interpret  {prompt, section?}. Signed in (spends model quota). */
export interface InterpretRequest {
  prompt: string
  section?: ScenarioSection | null
}

export interface InterpretedDTO {
  /** Every field of the scenario, each with its basis: what was said is `you`. */
  assumptions: AssumptionDTO[]
  /** How the prompt was read, in one sentence. */
  interpreted_as: string
  /** Parts of the prompt that could not be turned into a value. */
  unresolved: string[]
  method: 'model' | 'rules'
  /** A preset this reading matches exactly: opening it needs no computing. */
  matches_preset: string | null
}

/** POST /missions/{id}/scenarios. Named session. */
export interface ScenarioIn {
  name?: string | null
  /** Kept with the scenario, shown above its assumptions. */
  prompt?: string | null
  /** Only the values the person set; the rest are resolved (published, live, default). */
  assumptions: { field: AssumptionFieldId; value: string | number | string[] | null }[]
  /** Default: every step the assumptions allow. */
  sections?: ScenarioSection[]
}

export type ScenarioStatus = 'queued' | 'running' | 'done' | 'failed'

export interface ScenarioPhaseDTO {
  /** `inputs` (resolve and fetch live values), then one per section worked out. */
  id: 'inputs' | ScenarioSection
  label: string
  state: 'pending' | 'active' | 'done' | 'skipped' | 'failed'
  /** What is happening or what happened, in words ("Asked Launch Library 2: nothing listed"). */
  detail: string | null
}

export interface ScenarioBriefDTO {
  id: string
  mission_id: string
  name: string
  prompt: string | null
  status: ScenarioStatus
  /** 0..1 over all phases. */
  progress: number
  /** One sentence for the tray and the list. */
  message: string
  preset: boolean
  sections: ScenarioSection[]
  created_at: string
  created_by_name: string | null
}

export interface ScenarioResultsDTO {
  launch?: SectionDTO<LaunchCalendarDTO>
  trip?: SectionDTO<TripDTO>
  contact?: SectionDTO<ContactDTO>
  return?: SectionDTO<ReturnDTO>
  /** Surface: the four numbers at the assumed spot over the assumed dates. */
  landing?: SectionDTO<{
    site_id: string
    site_name: string
    window_start: string
    window_end: string
    sunlit_s: number
    earth_contact_s: number
    longest_dark_s: number
    longest_blackout_s: number
    sun_fraction_up: number
    earth_fraction_up: number
    longest_dark_open: boolean
    longest_blackout_open: boolean
    terrain_modelled: boolean
  }>
}

/** GET /scenarios/{id}; also the body of POST /missions/{id}/scenarios (201, or 200 when it already exists). */
export interface ScenarioDTO extends ScenarioBriefDTO {
  assumptions: AssumptionDTO[]
  phases: ScenarioPhaseDTO[]
  /** One plain sentence per section once worked out; never a verdict. */
  summaries: Partial<Record<ScenarioSection, string>>
  /** Null until done. A section the assumptions could not support is absent, and `skipped` in phases. */
  results: ScenarioResultsDTO | null
  /** Seconds to wait before asking again; 0 once done or failed. */
  poll_after_s: number
  error: string | null
}

/** GET /missions/{id}/scenarios. Public. Presets first, then newest. */
export interface ScenarioListDTO {
  items: ScenarioBriefDTO[]
}

// ---------------------------------------------------------------------------
// Ask: POST /agents/chat. Signed in. Same envelope as the other agents.
// ---------------------------------------------------------------------------

export interface ChatMessageDTO {
  role: 'user' | 'assistant'
  text: string
}

/** Where the person is, so "this mission" and "these dates" mean something. */
export interface ChatContextDTO {
  path: string
  mission_id?: string | null
  site_id?: string | null
  section?: SectionId | null
  scenario_id?: string | null
  start?: string | null
  end?: string | null
}

export interface ChatRequest {
  /** The conversation so far, oldest first; the last one is the question. At most 12. */
  messages: ChatMessageDTO[]
  context?: ChatContextDTO | null
}

export interface ChatActionDTO {
  label: string
  /** An in-app path ("/missions/im-3/launch") the answer points to. */
  href: string
}

/** `AgentDTO.result` for a chat answer. */
export interface ChatResultDTO {
  /** Two to four sentences. Every number traces to `provenance`. */
  answer: string
  interpreted_as: string
  /** Up to three next questions, as chips. */
  follow_ups: string[]
  /** Up to three places in the app that hold the full answer. */
  actions: ChatActionDTO[]
}

export type ChatResponseDTO = Omit<AgentDTO, 'result'> & { result: ChatResultDTO | null }

// ---------------------------------------------------------------------------
// Activity: GET /activity. Public. What is being worked out now, app-wide.
// ---------------------------------------------------------------------------

export interface ActivityItemDTO {
  /** Stable across polls: "job:123" or "scenario:<id>". */
  key: string
  kind: 'launch' | 'trip' | 'contact' | 'rover' | 'site_build' | 'scenario'
  /** "Launch opportunities for Griffin-1", "Scenario: Falcon Heavy from 39A". */
  label: string
  mission_id: string | null
  mission_name: string | null
  /** Where the answer is (or will be) shown. */
  href: string | null
  status: 'queued' | 'running' | 'done' | 'failed'
  progress: number | null
  message: string
  started_at: string
  finished_at: string | null
}

export interface ActivityDTO {
  /** Queued and running, oldest first. */
  active: ActivityItemDTO[]
  /** Finished in the last 15 minutes, newest first (at most 10). */
  recent: ActivityItemDTO[]
  /** Seconds to wait before asking again: short while anything is active. */
  poll_after_s: number
}
