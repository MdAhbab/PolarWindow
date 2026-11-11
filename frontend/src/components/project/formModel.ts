/**
 * The project form's state: every field as the person sees it (text), how it is
 * checked (as the server will), how it becomes the request, how a mission or a
 * file's reading becomes the form, and how a second file merges into it.
 * Nothing here fills a value that nobody gave: an unknown field stays empty.
 */
import type {
  DatePrecision,
  IntakeDTO,
  IntakeFieldDTO,
  ProjectDateIn,
  ProjectIn,
  ProjectLifecycleIn,
  ProjectPayloadIn,
} from '../../lib/api/experience.types'
import type { MissionDetail, PublishedDate } from '../../lib/api/adapters'

export interface DateField {
  /** YYYY-MM-DD; for a month, quarter or year, the first day of it. */
  date: string
  precision: Exclude<DatePrecision, 'second' | 'minute'>
}

export interface PayloadRow {
  key: string
  name: string
  acronym: string
  organisation: string
  types: string[]
  purpose: string
}

export interface ProjectFormState {
  name: string
  provider: string
  lander: string
  vehicleName: string
  taskOrder: string
  status: 'planned' | 'in_transit' | 'operating' | 'completed'
  targetMode: 'site' | 'coords'
  siteId: string
  targetName: string
  lat: string
  lon: string
  launch: DateField
  landing: DateField
  endOfMission: DateField
  plannedDays: string
  vehicleId: string
  padId: string
  transfer: '' | 'direct' | 'phasing_loops' | 'low_energy' | 'unknown'
  bands: string
  relays: string[]
  mass: string
  returns: '' | 'none' | 'sample_capsule' | 'crew'
  /** The radio figures, as typed. An empty one is unknown and is never sent. */
  eirp: string
  eirpTol: string
  gt: string
  frequency: string
  dataRates: string
  ebn0: string
  margin: string
  payloads: PayloadRow[]
  notes: string
  /** Lifecycle values the form has no field for; kept as they came so a save does not drop them. */
  keep: Partial<ProjectLifecycleIn>
  intakeId: number | null
}

const noDate = (): DateField => ({ date: '', precision: 'day' })

export function emptyForm(): ProjectFormState {
  return {
    name: '',
    provider: '',
    lander: '',
    vehicleName: '',
    taskOrder: '',
    status: 'planned',
    targetMode: 'site',
    siteId: '',
    targetName: '',
    lat: '',
    lon: '',
    launch: noDate(),
    landing: noDate(),
    endOfMission: noDate(),
    plannedDays: '',
    vehicleId: '',
    padId: '',
    transfer: '',
    bands: '',
    relays: [],
    mass: '',
    returns: '',
    eirp: '',
    eirpTol: '',
    gt: '',
    frequency: '',
    dataRates: '',
    ebn0: '',
    margin: '',
    payloads: [],
    notes: '',
    keep: {},
    intakeId: null,
  }
}

let rowKey = 1
export const newPayload = (p: Partial<PayloadRow> = {}): PayloadRow => ({
  key: `row-${rowKey++}`,
  name: '',
  acronym: '',
  organisation: '',
  types: [],
  purpose: '',
  ...p,
})

// ---------------------------------------------------------------------------
// Groups: the unit a file fills, a later file may not overwrite, and a source is shown for
// ---------------------------------------------------------------------------

export type GroupKey =
  | 'name'
  | 'provider'
  | 'lander'
  | 'vehicleName'
  | 'taskOrder'
  | 'status'
  | 'target'
  | 'launch'
  | 'landing'
  | 'endOfMission'
  | 'plannedDays'
  | 'vehicleId'
  | 'padId'
  | 'transfer'
  | 'bands'
  | 'relays'
  | 'mass'
  | 'returns'
  | 'radio'
  | 'payloads'
  | 'notes'

type Slice = (keyof ProjectFormState)[]

export const GROUPS: Record<GroupKey, { fields: Slice; paths: string[]; label: string }> = {
  name: { fields: ['name'], paths: ['name'], label: 'Mission name' },
  provider: { fields: ['provider'], paths: ['provider'], label: 'Provider' },
  lander: { fields: ['lander'], paths: ['lander'], label: 'Lander' },
  vehicleName: { fields: ['vehicleName'], paths: ['vehicle_name'], label: 'Spacecraft name' },
  taskOrder: { fields: ['taskOrder'], paths: ['task_order'], label: 'Task order' },
  status: { fields: ['status'], paths: ['status'], label: 'Status' },
  target: {
    fields: ['targetMode', 'siteId', 'targetName', 'lat', 'lon'],
    paths: ['target', 'target.site_id', 'target.name', 'target.lat_deg', 'target.lon_deg'],
    label: 'Landing spot',
  },
  launch: { fields: ['launch'], paths: ['launch', 'launch.date'], label: 'Launch date' },
  landing: { fields: ['landing'], paths: ['landing', 'landing.date'], label: 'Landing date' },
  endOfMission: { fields: ['endOfMission'], paths: ['end_of_mission', 'end_of_mission.date'], label: 'End of mission' },
  plannedDays: { fields: ['plannedDays'], paths: ['planned_surface_days'], label: 'Days on the surface' },
  vehicleId: { fields: ['vehicleId'], paths: ['lifecycle.vehicle_id'], label: 'Launch vehicle' },
  padId: { fields: ['padId'], paths: ['lifecycle.pad_id'], label: 'Launch pad' },
  transfer: { fields: ['transfer'], paths: ['lifecycle.transfer_type'], label: 'Transfer type' },
  bands: { fields: ['bands'], paths: ['lifecycle.bands'], label: 'Radio bands' },
  relays: { fields: ['relays'], paths: ['lifecycle.relays'], label: 'Relays' },
  mass: { fields: ['mass'], paths: ['lifecycle.mass_kg'], label: 'Mass' },
  returns: { fields: ['returns'], paths: ['lifecycle.returns'], label: 'What returns' },
  radio: {
    fields: ['eirp', 'eirpTol', 'gt', 'frequency', 'dataRates', 'ebn0', 'margin'],
    paths: [
      'lifecycle.eirp_dbw',
      'lifecycle.eirp_tol_db',
      'lifecycle.gt_dbk',
      'lifecycle.frequency_mhz',
      'lifecycle.data_rates_kbps',
      'lifecycle.required_ebn0_db',
      'lifecycle.required_margin_db',
    ],
    label: 'Radio figures',
  },
  payloads: { fields: ['payloads'], paths: ['payloads'], label: 'Payloads' },
  notes: { fields: ['notes'], paths: ['notes'], label: 'Notes' },
}

export const GROUP_KEYS = Object.keys(GROUPS) as GroupKey[]

const sliceOf = (f: ProjectFormState, g: GroupKey) => GROUPS[g].fields.map((k) => f[k])

/** A group is empty when it still holds what an empty form holds (the status "planned" counts as empty). */
export function groupEmpty(f: ProjectFormState, g: GroupKey): boolean {
  if (g === 'payloads') return f.payloads.every((p) => !p.name && !p.acronym && !p.organisation && !p.purpose && !p.types.length)
  return JSON.stringify(sliceOf(f, g)) === JSON.stringify(sliceOf(emptyForm(), g))
}

function sameGroup(a: ProjectFormState, b: ProjectFormState, g: GroupKey): boolean {
  if (g === 'payloads') {
    const strip = (f: ProjectFormState) => f.payloads.map(({ key: _k, ...r }) => r)
    return JSON.stringify(strip(a)) === JSON.stringify(strip(b))
  }
  return JSON.stringify(sliceOf(a, g)) === JSON.stringify(sliceOf(b, g))
}

function copyGroup(into: ProjectFormState, from: ProjectFormState, g: GroupKey) {
  const w = into as unknown as Record<string, unknown>
  for (const k of GROUPS[g].fields) w[k] = from[k]
}

// ---------------------------------------------------------------------------
// A file's reading → the form, and merging files
// ---------------------------------------------------------------------------

const dateIn = (d: ProjectDateIn | null | undefined): DateField => {
  if (!d?.date) return noDate()
  const precision = d.precision === 'second' || d.precision === 'minute' ? 'day' : d.precision
  return { date: d.date.slice(0, 10), precision }
}

const numWords = (n: number | null | undefined) => (n === null || n === undefined ? '' : String(n))

/** The seven radio figures a saved or read project states, as the form's text. */
export type RadioFigures = Pick<
  ProjectLifecycleIn,
  'eirp_dbw' | 'eirp_tol_db' | 'gt_dbk' | 'frequency_mhz' | 'data_rates_kbps' | 'required_ebn0_db' | 'required_margin_db'
>

export function radioToForm(r: RadioFigures | null | undefined): Pick<ProjectFormState, 'eirp' | 'eirpTol' | 'gt' | 'frequency' | 'dataRates' | 'ebn0' | 'margin'> {
  return {
    eirp: numWords(r?.eirp_dbw),
    eirpTol: numWords(r?.eirp_tol_db),
    gt: numWords(r?.gt_dbk),
    frequency: numWords(r?.frequency_mhz),
    dataRates: (r?.data_rates_kbps ?? []).join(', '),
    ebn0: numWords(r?.required_ebn0_db),
    margin: numWords(r?.required_margin_db),
  }
}

/** The lifecycle values the form has fields for, and the rest (`keep`), from a request-shaped lifecycle. */
function lifecycleToForm(lc: ProjectLifecycleIn | null | undefined) {
  const l = lc ?? {}
  const keep: Partial<ProjectLifecycleIn> = {}
  const set = (k: keyof ProjectLifecycleIn, v: unknown) => {
    if (
      v !== undefined &&
      v !== null &&
      !(Array.isArray(v) && v.length === 0) &&
      !(typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length === 0)
    )
      (keep as Record<string, unknown>)[k] = v
  }
  set('vehicle_name', l.vehicle_name)
  set('pad_name', l.pad_name)
  set('flight_days', l.flight_days)
  set('lunar_orbit_days', l.lunar_orbit_days)
  set('sun_el_min_deg', l.sun_el_min_deg)
  set('sun_el_max_deg', l.sun_el_max_deg)
  set('ground_stations', l.ground_stations)
  set('rovers', l.rovers)
  set('field_sources', l.field_sources)
  return {
    fields: {
      vehicleId: l.vehicle_id ?? '',
      padId: l.pad_id ?? '',
      transfer: l.transfer_type ?? ('' as const),
      bands: (l.bands ?? []).join(', '),
      relays: [...(l.relays ?? [])],
      mass: numWords(l.mass_kg),
      returns: l.returns ?? ('' as const),
      ...radioToForm(l),
    },
    keep,
  }
}

const TRANSFERS = ['direct', 'phasing_loops', 'low_energy', 'unknown'] as const
const RETURNS = ['none', 'sample_capsule', 'crew'] as const
/** [min, max, min is excluded], as ProjectLifecycleIn states them. */
const RANGES: Record<string, [number, number, boolean]> = {
  flight_days: [0, 1000, true],
  lunar_orbit_days: [0, 1000, false],
  sun_el_min_deg: [-5, 90, false],
  sun_el_max_deg: [-5, 90, false],
  mass_kg: [0, 1e6, true],
  eirp_dbw: [-20, 100, false],
  eirp_tol_db: [0, 30, false],
  gt_dbk: [-60, 80, false],
  frequency_mhz: [0, 300000, true],
  required_ebn0_db: [-10, 40, false],
  required_margin_db: [0, 30, false],
}

type Loose = Record<string, unknown>
const loose = (v: unknown): Loose => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Loose) : {})

/**
 * A stored mission's lifecycle block (the shape `lifecycle_of` writes) as the request's
 * lifecycle, so an edit sends back what was saved. A value the request cannot express
 * (a number out of range, a word it does not know, a list too long) is left out.
 */
export function lifecycleFromStored(stored: unknown): ProjectLifecycleIn {
  const s = loose(stored)
  const transfer = loose(s.transfer)
  const descent = loose(s.descent)
  const comms = loose(s.comms)
  const craft = loose(s.spacecraft)
  const out: Loose = {}
  const number = (k: string, v: unknown) => {
    const r = RANGES[k]
    if (typeof v !== 'number' || !Number.isFinite(v) || v < r[0] || v > r[1] || (r[2] && v === r[0])) return
    out[k] = v
  }
  const ids = (k: string, v: unknown, max: number) => {
    if (!Array.isArray(v)) return
    const list = v.filter((x): x is string => typeof x === 'string' && x.length > 0 && x.length <= 64)
    if (list.length) out[k] = list.slice(0, max)
  }
  const id = (k: string, v: unknown) => {
    if (typeof v === 'string' && v.trim() && v.length <= 64) out[k] = v
  }
  const word = (k: string, v: unknown, max: number) => {
    if (typeof v === 'string' && v.trim() && v.length <= max) out[k] = v
  }
  id('vehicle_id', s.vehicle_id)
  word('vehicle_name', s.vehicle_name, 160)
  id('pad_id', s.pad_id)
  word('pad_name', s.pad_name, 160)
  if ((TRANSFERS as readonly unknown[]).includes(transfer.type)) out.transfer_type = transfer.type
  number('flight_days', transfer.flight_days)
  number('lunar_orbit_days', transfer.lunar_orbit_days)
  number('sun_el_min_deg', descent.sun_el_min_deg)
  number('sun_el_max_deg', descent.sun_el_max_deg)
  ids('bands', comms.bands, 8)
  ids('ground_stations', comms.ground_stations, 40)
  ids('relays', comms.relays, 12)
  number('mass_kg', craft.mass_kg)
  if (Array.isArray(s.rovers)) {
    const rovers = s.rovers
      .map((item) => loose(item))
      .filter((r) => typeof r.name === 'string' && r.name.trim().length > 0 && r.name.length <= 200)
      .slice(0, 20)
      .map((r) => ({
        ...(typeof r.id === 'string' && r.id.trim() && r.id.length <= 128 ? { id: r.id } : {}),
        name: r.name as string,
        organisation: typeof r.organisation === 'string' && r.organisation.length <= 200 ? r.organisation : null,
        ...(typeof r.source_url === 'string' && r.source_url.length <= 500 ? { source_url: r.source_url } : {}),
      }))
    if (rovers.length) out.rovers = rovers
  }
  if ((RETURNS as readonly unknown[]).includes(s.returns)) out.returns = s.returns
  if (s.field_sources && typeof s.field_sources === 'object' && !Array.isArray(s.field_sources)) {
    const entries = Object.entries(s.field_sources as Loose)
      .filter(([k, v]) => k.length > 0 && k.length <= 64 && typeof v === 'string' && v.length <= 500)
      .slice(0, 40)
    if (entries.length) out.field_sources = Object.fromEntries(entries)
  }
  for (const k of ['eirp_dbw', 'eirp_tol_db', 'gt_dbk', 'frequency_mhz', 'required_ebn0_db', 'required_margin_db']) number(k, comms[k])
  if (Array.isArray(comms.data_rates_kbps)) {
    const rates = comms.data_rates_kbps.filter((r: unknown): r is number => typeof r === 'number' && Number.isFinite(r) && r > 0 && r <= 1e7)
    if (rates.length) out.data_rates_kbps = rates.slice(0, 20)
  }
  return out as ProjectLifecycleIn
}

/** The draft as form state. Only what the file said; the rest stays empty. */
export function formFromDraft(d: ProjectIn): ProjectFormState {
  const f = emptyForm()
  const lc = d.lifecycle ?? {}
  f.name = d.name ?? ''
  f.provider = d.provider ?? ''
  f.lander = d.lander ?? ''
  f.vehicleName = d.vehicle_name ?? ''
  f.taskOrder = d.task_order ?? ''
  f.status = d.status ?? 'planned'
  if (d.target) {
    if (d.target.site_id) {
      f.targetMode = 'site'
      f.siteId = d.target.site_id
    } else if (d.target.lat_deg !== null && d.target.lat_deg !== undefined) {
      f.targetMode = 'coords'
    }
    f.targetName = d.target.name ?? ''
    f.lat = numWords(d.target.lat_deg)
    f.lon = numWords(d.target.lon_deg)
  }
  f.launch = dateIn(d.launch)
  f.landing = dateIn(d.landing)
  f.endOfMission = dateIn(d.end_of_mission)
  f.plannedDays = numWords(d.planned_surface_days)
  const l = lifecycleToForm(lc)
  Object.assign(f, l.fields)
  f.payloads = (d.payloads ?? []).map((p) =>
    newPayload({
      name: p.name,
      acronym: p.acronym ?? '',
      organisation: p.organisation ?? '',
      types: p.instrument_types ?? [],
      purpose: p.purpose ?? '',
    }),
  )
  f.notes = (d.notes ?? []).join('\n')
  f.keep = l.keep
  f.intakeId = null
  return f
}

/** Where each filled group's value came from (the file and what it said). */
export type Provenance = Partial<Record<GroupKey, { filename: string; field: IntakeFieldDTO }>>

/** The best of the reader's notes for a group: a stated one first, then an inferred one. */
function fieldFor(g: GroupKey, fields: IntakeDTO['fields']): IntakeFieldDTO | null {
  const found = GROUPS[g].paths.map((p) => fields[p]).filter((x): x is IntakeFieldDTO => Boolean(x) && x.confidence !== 'not_found')
  return found.find((x) => x.confidence === 'stated') ?? found[0] ?? null
}

export interface MergeResult {
  form: ProjectFormState
  provenance: Provenance
  /** Groups the form already had a different value for; not changed. */
  conflicts: GroupKey[]
  filled: GroupKey[]
  /** The file's form, for applying the conflicts if the person accepts. */
  incoming: ProjectFormState
}

/**
 * A file's reading into the form. A group that is still empty is filled; one
 * that already has a different value is left alone and listed as a conflict
 * (unless `overwrite`). A group the file said nothing about is never touched.
 */
export function mergeIntake(
  current: ProjectFormState,
  currentProvenance: Provenance,
  intake: IntakeDTO,
  overwrite = false,
): MergeResult {
  const incoming = formFromDraft(intake.draft)
  const form: ProjectFormState = { ...current, payloads: current.payloads.map((p) => ({ ...p })), keep: { ...current.keep } }
  const provenance: Provenance = { ...currentProvenance }
  const conflicts: GroupKey[] = []
  const filled: GroupKey[] = []
  for (const g of GROUP_KEYS) {
    if (groupEmpty(incoming, g)) continue
    if (groupEmpty(form, g) || sameGroup(form, incoming, g) || overwrite) {
      const changed = !sameGroup(form, incoming, g)
      if (changed) filled.push(g)
      copyGroup(form, incoming, g)
      const field = fieldFor(g, intake.fields)
      if (field && (changed || !provenance[g])) provenance[g] = { filename: intake.filename, field }
    } else {
      conflicts.push(g)
    }
  }
  // What the form has no field for comes along only where the form has none.
  for (const [k, v] of Object.entries(incoming.keep)) {
    const kk = k as keyof ProjectLifecycleIn
    if (v !== undefined && v !== null && (form.keep[kk] === undefined || form.keep[kk] === null || overwrite)) {
      ;(form.keep as Record<string, unknown>)[k] = v
    }
  }
  form.intakeId = intake.intake_id
  return { form, provenance, conflicts, filled, incoming }
}

/** The counts the reading's summary gives: found, and looked for. */
export function intakeCounts(intake: IntakeDTO): { found: number; lookedFor: number } {
  const all = Object.values(intake.fields)
  return { found: all.filter((f) => f.confidence !== 'not_found').length, lookedFor: all.length }
}

// ---------------------------------------------------------------------------
// A saved mission → the form (Edit)
// ---------------------------------------------------------------------------

const pubIn = (d: PublishedDate | null): DateField => {
  if (!d) return noDate()
  const p = d.precision
  return { date: d.iso.slice(0, 10), precision: p === 'month' || p === 'quarter' || p === 'year' ? p : 'day' }
}

/**
 * A project's mission record as the form. The record's fields only; nothing is guessed.
 * `lifecycle` is the stored lifecycle as the request states it (`lifecycleFromStored`);
 * the mission adapter does not carry it.
 */
export function formFromMission(m: MissionDetail, lifecycle?: ProjectLifecycleIn | null): ProjectFormState {
  const f = emptyForm()
  const l = lifecycleToForm(lifecycle)
  Object.assign(f, l.fields)
  f.keep = l.keep
  f.name = m.name
  f.provider = m.provider ?? ''
  f.lander = m.lander ?? ''
  f.vehicleName = m.vehicleName ?? ''
  f.taskOrder = m.taskOrder ?? ''
  f.status = (['planned', 'in_transit', 'operating', 'completed'] as const).find((s) => s === m.status) ?? 'planned'
  if (m.siteId) {
    f.targetMode = 'site'
    f.siteId = m.siteId
  } else if (m.target) {
    f.targetMode = 'coords'
  }
  if (m.target) {
    f.targetName = m.target.name
    f.lat = String(m.target.latDeg)
    f.lon = String(m.target.lonDeg)
  }
  f.launch = pubIn(m.launch)
  f.landing = pubIn(m.landing)
  f.endOfMission = pubIn(m.endOfMission)
  f.plannedDays = numWords(m.plannedSurfaceDays)
  f.payloads = m.payloads.map((p) =>
    newPayload({
      name: p.name,
      acronym: p.acronym ?? '',
      organisation: p.organisation ?? '',
      types: p.instrumentTypes,
      purpose: p.purpose,
    }),
  )
  f.notes = m.notes.join('\n')
  return f
}

// ---------------------------------------------------------------------------
// Checking, as the server will
// ---------------------------------------------------------------------------

export type Errors = Partial<Record<string, string>>

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/

export function validDate(s: string): boolean {
  if (!DATE_RE.test(s)) return false
  const t = Date.parse(`${s}T00:00:00Z`)
  return !Number.isNaN(t) && new Date(t).toISOString().slice(0, 10) === s
}

const isNumber = (s: string) => s.trim() !== '' && Number.isFinite(Number(s))

/** Longitude as the server keeps it: degrees east, 0 to 360 (−180 to 180 is accepted). */
export function normaliseLon(lon: number): number {
  return ((lon % 360) + 360) % 360
}

/** Field problems by form key. Empty when the form can be sent. */
export function validate(f: ProjectFormState): Errors {
  const e: Errors = {}
  if (!f.name.trim()) e.name = 'Give the mission a name. It is the only thing the form needs.'
  const dateErr = (k: 'launch' | 'landing' | 'endOfMission', what: string) => {
    const d = f[k].date
    if (d && !validDate(d)) e[k] = `${what} is not a date. Write it as year-month-day, such as 2027-10-14.`
  }
  dateErr('launch', 'The launch date')
  dateErr('landing', 'The landing date')
  dateErr('endOfMission', 'The end-of-mission date')
  const positive = (k: 'plannedDays' | 'mass', what: string) => {
    const v = f[k].trim()
    if (v && !(isNumber(v) && Number(v) > 0)) e[k] = `${what} must be a number above zero, or left empty.`
  }
  positive('plannedDays', 'Days on the surface')
  positive('mass', 'Mass')
  if (f.targetMode === 'coords') {
    const hasLat = f.lat.trim() !== ''
    const hasLon = f.lon.trim() !== ''
    if (hasLat || hasLon) {
      if (!hasLat || !isNumber(f.lat) || Number(f.lat) < -90 || Number(f.lat) > 90) e.lat = 'Latitude is a number from −90 to 90 (south is negative).'
      if (!hasLon || !isNumber(f.lon) || Number(f.lon) < -180 || Number(f.lon) > 360) e.lon = 'Longitude is a number of degrees east, from 0 to 360 (−180 to 180 also works).'
    }
  }
  const radio = (k: 'eirp' | 'eirpTol' | 'gt' | 'frequency' | 'ebn0' | 'margin', what: string, min: number, max: number, unit: string) => {
    const v = f[k].trim()
    if (v && !(isNumber(v) && Number(v) >= min && Number(v) <= max)) e[k] = `${what} is a number from ${min} to ${max} ${unit}, or leave it empty.`
  }
  radio('eirp', 'The EIRP', -20, 100, 'dBW')
  radio('eirpTol', 'The EIRP tolerance', 0, 30, 'dB')
  radio('gt', 'The G/T', -60, 80, 'dB/K')
  radio('ebn0', 'The required Eb/N0', -10, 40, 'dB')
  radio('margin', 'The required margin', 0, 30, 'dB')
  const fq = f.frequency.trim()
  if (fq && !(isNumber(fq) && Number(fq) > 0 && Number(fq) <= 300000)) e.frequency = 'The frequency is a number of megahertz above 0 and at most 300000, or leave it empty.'
  const rates = dataRatesOf(f.dataRates)
  if (rates.some((r) => !(Number.isFinite(r) && r > 0 && r <= 1e7)))
    e.dataRates = 'Give the data rates as numbers above 0 and at most 10000000, such as 2, 64, 256.'
  else if (rates.length > 20) e.dataRates = 'Give at most 20 data rates.'
  f.payloads.forEach((p, i) => {
    const used = p.acronym || p.organisation || p.purpose || p.types.length
    if (used && !p.name.trim()) e[`payload-${i}`] = 'Name this payload, or remove the row.'
  })
  return e
}

// ---------------------------------------------------------------------------
// The form → the request
// ---------------------------------------------------------------------------

const text = (s: string) => (s.trim() ? s.trim() : null)
const num = (s: string) => (s.trim() ? Number(s) : null)
/** A typed list of rates ("2, 64,256") as numbers; a word that is no number stays NaN so validation can name it. */
export const dataRatesOf = (s: string): number[] =>
  s
    .split(/[,;\s]+/)
    .filter(Boolean)
    .map((x) => Number(x))
const dateOut = (d: DateField): ProjectDateIn | null => (d.date ? { date: d.date, precision: d.precision } : null)

export function toRequest(f: ProjectFormState): ProjectIn {
  const lifecycle: ProjectLifecycleIn = {
    ...f.keep,
    vehicle_id: text(f.vehicleId),
    pad_id: text(f.padId),
    transfer_type: f.transfer || null,
    bands: f.bands
      .split(/[,;\n]/)
      .map((b) => b.trim())
      .filter(Boolean),
    relays: f.relays,
    mass_kg: num(f.mass),
    returns: f.returns || null,
    // Radio figures: a figure left empty is left out, never sent as 0.
    ...(num(f.eirp) !== null && { eirp_dbw: num(f.eirp) }),
    ...(num(f.eirpTol) !== null && { eirp_tol_db: num(f.eirpTol) }),
    ...(num(f.gt) !== null && { gt_dbk: num(f.gt) }),
    ...(num(f.frequency) !== null && { frequency_mhz: num(f.frequency) }),
    ...(dataRatesOf(f.dataRates).length > 0 && { data_rates_kbps: dataRatesOf(f.dataRates) }),
    ...(num(f.ebn0) !== null && { required_ebn0_db: num(f.ebn0) }),
    ...(num(f.margin) !== null && { required_margin_db: num(f.margin) }),
  }
  const hasLifecycle = Object.values(lifecycle).some((v) => (Array.isArray(v) ? v.length > 0 : v !== null && v !== undefined))
  let target: ProjectIn['target'] = null
  if (f.targetMode === 'site' && f.siteId) target = { site_id: f.siteId }
  else if (f.targetMode === 'coords' && f.lat.trim() && f.lon.trim())
    target = { name: text(f.targetName), lat_deg: Number(f.lat), lon_deg: normaliseLon(Number(f.lon)) }
  const payloads: ProjectPayloadIn[] = f.payloads
    .filter((p) => p.name.trim())
    .map((p) => ({
      name: p.name.trim(),
      acronym: text(p.acronym),
      organisation: text(p.organisation),
      instrument_types: p.types,
      purpose: text(p.purpose),
    }))
  return {
    name: f.name.trim(),
    provider: text(f.provider),
    lander: text(f.lander),
    vehicle_name: text(f.vehicleName),
    task_order: text(f.taskOrder),
    status: f.status,
    target,
    launch: dateOut(f.launch),
    landing: dateOut(f.landing),
    end_of_mission: dateOut(f.endOfMission),
    planned_surface_days: num(f.plannedDays),
    lifecycle: hasLifecycle ? lifecycle : null,
    payloads,
    notes: f.notes
      .split('\n')
      .map((n) => n.trim())
      .filter(Boolean),
    intake_id: f.intakeId,
  }
}

/** Which form key a server field path belongs to ("landing.date" → "landing"). */
export function keyForServerPath(path: string): string {
  const head = path.split('.')[0]
  const map: Record<string, string> = {
    name: 'name',
    provider: 'provider',
    lander: 'lander',
    vehicle_name: 'vehicleName',
    task_order: 'taskOrder',
    status: 'status',
    launch: 'launch',
    landing: 'landing',
    end_of_mission: 'endOfMission',
    planned_surface_days: 'plannedDays',
  }
  if (map[head]) return map[head]
  if (head === 'target') {
    const leaf = path.split('.')[1]
    return leaf === 'lat_deg' ? 'lat' : leaf === 'lon_deg' ? 'lon' : leaf === 'site_id' ? 'siteId' : 'targetName'
  }
  if (head === 'lifecycle') {
    const leaf = path.split('.')[1]
    const lc: Record<string, string> = {
      vehicle_id: 'vehicleId',
      pad_id: 'padId',
      transfer_type: 'transfer',
      bands: 'bands',
      relays: 'relays',
      mass_kg: 'mass',
      returns: 'returns',
      eirp_dbw: 'eirp',
      eirp_tol_db: 'eirpTol',
      gt_dbk: 'gt',
      frequency_mhz: 'frequency',
      data_rates_kbps: 'dataRates',
      required_ebn0_db: 'ebn0',
      required_margin_db: 'margin',
    }
    return lc[leaf] ?? 'lifecycle'
  }
  if (head === 'payloads') return `payload-${path.split('.')[1] ?? '0'}`
  return path
}

/** True when the form holds anything a person (or a file) put there. */
export function isBlank(f: ProjectFormState): boolean {
  return GROUP_KEYS.every((g) => groupEmpty(f, g))
}
