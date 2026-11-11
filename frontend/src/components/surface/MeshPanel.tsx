import { useId, useMemo, useState, type ReactNode } from 'react'
import { useMesh } from '../../lib/api/surface'
import { LIVE_SERVICE } from '../../lib/api/home'
import type {
  MeshHelperDTO,
  MeshNodeInDTO,
  MeshRadioInDTO,
  MeshGuardInDTO,
  MeshRequestDTO,
  MeshResponseDTO,
  QuantityDTO,
} from '../../lib/api/surface.types'
import { TextInput } from '../lifecycle/Forms'
import { ProblemPanel } from '../States'
import { Button, Disclosure } from '../ui'
import { MeshMap, type MeshMapNode } from './MeshMap'
import { num, utcWords } from './helpers'
import { ProvTag, QuantityCell, SavedCopyNote } from './parts'

/**
 * The preset: a lander and two rovers, the same figures as the saved request
 * for Connecting Ridge. Every one is assumed; none is published or measured.
 */
interface NodeDefaults {
  name: string
  east_m?: number
  north_m?: number
  antenna_height_m: number
  battery_capacity_wh: number
  initial_soc_fraction: number
  own_traffic_bps: number
  may_help: boolean
  earth_uplink_bps?: number
  earth_uplink_power_w?: number
}

const ROVER: NodeDefaults = {
  name: 'Rover',
  antenna_height_m: 1.5,
  battery_capacity_wh: 2000,
  initial_soc_fraction: 1,
  own_traffic_bps: 20000,
  may_help: true,
  earth_uplink_bps: 100000,
  earth_uplink_power_w: 20,
}

const PRESET_NODES: { id: string; d: NodeDefaults }[] = [
  { id: 'lander', d: { ...ROVER, name: 'Lander', east_m: 0, north_m: 0, antenna_height_m: 4 } },
  { id: 'r1', d: { ...ROVER, name: 'Rover 1', east_m: 0, north_m: 300 } },
  { id: 'r2', d: { ...ROVER, name: 'Rover 2', east_m: 202.6389541653453, north_m: -221.21811466237364 } },
]

export const MESH_STEP_S = 3600
export const MESH_LOSS_S = 900
export const MAX_NODES = 6

const RADIO_DEFAULT: MeshRadioInDTO = {
  frequency_hz: 900000000,
  tx_power_w: 2,
  forwarding_tx_power_w: 2,
  tx_efficiency: 0.3,
  antenna_gain_dbi: 2,
  bandwidth_hz: 5000000,
  noise_figure_db: 5,
  snr_threshold_db: 3,
  eps_r: 2.7,
  polarisation: 'vertical',
}

const GUARD_DEFAULT: MeshGuardInDTO = {
  soc_cutoff_fraction: 0.65,
  quota_share_per_lunar_day: 0.05,
  max_forwarding_power_w: 5,
  buffer_bytes: 50000000,
}

interface SettingDef {
  group: 'radio' | 'guard'
  key: string
  label: string
  unit: string
  /** Sent value = typed value times this (MHz to Hz, % to a fraction, MB to bytes). */
  scale: number
  def: number
}

const SETTINGS: SettingDef[] = [
  { group: 'radio', key: 'frequency_hz', label: 'Frequency', unit: 'MHz', scale: 1e6, def: RADIO_DEFAULT.frequency_hz },
  { group: 'radio', key: 'tx_power_w', label: 'Transmit power for its own traffic', unit: 'W', scale: 1, def: RADIO_DEFAULT.tx_power_w },
  { group: 'radio', key: 'forwarding_tx_power_w', label: 'Transmit power when helping', unit: 'W', scale: 1, def: RADIO_DEFAULT.forwarding_tx_power_w },
  { group: 'radio', key: 'tx_efficiency', label: 'Transmitter efficiency', unit: '%', scale: 0.01, def: RADIO_DEFAULT.tx_efficiency },
  { group: 'radio', key: 'antenna_gain_dbi', label: 'Antenna gain, each end', unit: 'dBi', scale: 1, def: RADIO_DEFAULT.antenna_gain_dbi },
  { group: 'radio', key: 'bandwidth_hz', label: 'Bandwidth', unit: 'MHz', scale: 1e6, def: RADIO_DEFAULT.bandwidth_hz },
  { group: 'radio', key: 'noise_figure_db', label: 'Receiver noise figure', unit: 'dB', scale: 1, def: RADIO_DEFAULT.noise_figure_db },
  { group: 'radio', key: 'snr_threshold_db', label: 'Link closes at or above', unit: 'dB SNR', scale: 1, def: RADIO_DEFAULT.snr_threshold_db },
  { group: 'radio', key: 'eps_r', label: 'Ground permittivity', unit: 'relative', scale: 1, def: RADIO_DEFAULT.eps_r },
  { group: 'guard', key: 'soc_cutoff_fraction', label: 'A helper stops below this charge', unit: '%', scale: 0.01, def: GUARD_DEFAULT.soc_cutoff_fraction },
  {
    group: 'guard',
    key: 'quota_share_per_lunar_day',
    label: 'Share of its battery a helper may spend per lunar day',
    unit: '%',
    scale: 0.01,
    def: GUARD_DEFAULT.quota_share_per_lunar_day,
  },
  { group: 'guard', key: 'max_forwarding_power_w', label: 'Most power a helper may use to forward', unit: 'W', scale: 1, def: GUARD_DEFAULT.max_forwarding_power_w },
  { group: 'guard', key: 'buffer_bytes', label: 'Buffer for data waiting to be passed on', unit: 'MB', scale: 1e6, def: GUARD_DEFAULT.buffer_bytes },
]

type Vals = Record<string, string>
export interface MeshRow {
  key: number
  id: string
  d: NodeDefaults
}

const rowKey = (r: MeshRow, f: string) => `n${r.key}.${f}`
const shownDefault = (v: number | undefined, scale: number, digits = 2): string =>
  v === undefined ? '' : String(Number((v / scale).toFixed(digits)))

type Parsed = { value: number | undefined; error?: string }

/** One figure: the preset figure until touched, then what was typed (times its unit's scale). */
function parseFigure(vals: Vals, key: string, def: number | undefined, scale: number, optional = false): Parsed {
  if (!(key in vals)) return { value: def }
  const t = vals[key].trim()
  if (t === '') return optional ? { value: undefined } : { value: undefined, error: 'Type a number.' }
  const n = Number(t)
  return Number.isFinite(n) ? { value: n * scale } : { value: undefined, error: 'Type a number.' }
}

export const initialMeshRows = (): MeshRow[] => PRESET_NODES.map((p, i) => ({ key: i, id: p.id, d: p.d }))

/** The request the form describes, and the problems with it, by field key. Untouched figures are sent exactly as preset. */
export function meshRequestFrom(
  rows: MeshRow[],
  vals: Vals,
  startIso: string | null,
  endIso: string | null,
): { body: MeshRequestDTO; errors: Record<string, string> } {
  const errors: Record<string, string> = {}
  const take = (p: Parsed, key: string): number => {
    if (p.error) errors[key] = p.error
    else if (p.value === undefined) errors[key] = 'Type a number.'
    return p.value ?? 0
  }
  const nodes: MeshNodeInDTO[] = rows.map((r) => {
    const f = (name: string, def: number | undefined, scale = 1, optional = false) => parseFigure(vals, rowKey(r, name), def, scale, optional)
    const nm = (rowKey(r, 'name') in vals ? vals[rowKey(r, 'name')] : r.d.name).trim()
    const bps = f('uplink_kbps', r.d.earth_uplink_bps, 1000, true)
    const watts = f('uplink_w', r.d.earth_uplink_power_w, 1, true)
    if (bps.error) errors[rowKey(r, 'uplink_kbps')] = bps.error
    if (watts.error) errors[rowKey(r, 'uplink_w')] = watts.error
    if (!bps.error && !watts.error && (bps.value === undefined) !== (watts.value === undefined)) {
      errors[rowKey(r, bps.value === undefined ? 'uplink_kbps' : 'uplink_w')] = 'Give both the rate and the power, or leave both empty.'
    }
    const helps = rowKey(r, 'may_help') in vals ? vals[rowKey(r, 'may_help')] === 'true' : r.d.may_help
    return {
      id: r.id,
      ...(nm ? { name: nm } : {}),
      position: {
        east_m: take(f('east_m', r.d.east_m), rowKey(r, 'east_m')),
        north_m: take(f('north_m', r.d.north_m), rowKey(r, 'north_m')),
      },
      antenna_height_m: take(f('antenna_height_m', r.d.antenna_height_m), rowKey(r, 'antenna_height_m')),
      battery_capacity_wh: take(f('battery_capacity_wh', r.d.battery_capacity_wh), rowKey(r, 'battery_capacity_wh')),
      initial_soc_fraction: take(f('initial_soc_fraction', r.d.initial_soc_fraction, 0.01), rowKey(r, 'initial_soc_fraction')),
      own_traffic_bps: take(f('own_traffic_bps', r.d.own_traffic_bps, 1000), rowKey(r, 'own_traffic_bps')),
      may_help: helps,
      ...(bps.value !== undefined && watts.value !== undefined ? { earth_uplink_bps: bps.value, earth_uplink_power_w: watts.value } : {}),
    }
  })
  const setting = (k: string) => {
    const def = SETTINGS.find((s) => s.key === k)!
    return take(parseFigure(vals, `s.${k}`, def.def, def.scale), `s.${k}`)
  }
  const radio: MeshRadioInDTO = {
    frequency_hz: setting('frequency_hz'),
    tx_power_w: setting('tx_power_w'),
    forwarding_tx_power_w: setting('forwarding_tx_power_w'),
    tx_efficiency: setting('tx_efficiency'),
    antenna_gain_dbi: setting('antenna_gain_dbi'),
    bandwidth_hz: setting('bandwidth_hz'),
    noise_figure_db: setting('noise_figure_db'),
    snr_threshold_db: setting('snr_threshold_db'),
    eps_r: setting('eps_r'),
    polarisation: (vals['s.polarisation'] ?? RADIO_DEFAULT.polarisation) as MeshRadioInDTO['polarisation'],
  }
  const guard: MeshGuardInDTO = {
    soc_cutoff_fraction: setting('soc_cutoff_fraction'),
    quota_share_per_lunar_day: setting('quota_share_per_lunar_day'),
    max_forwarding_power_w: setting('max_forwarding_power_w'),
    buffer_bytes: setting('buffer_bytes'),
  }
  const loss = take(parseFigure(vals, 's.loss_min', MESH_LOSS_S, 60), 's.loss_min')
  return {
    body: { start: startIso, end: endIso, step_s: MESH_STEP_S, loss_threshold_s: loss, radio, guard, nodes },
    errors,
  }
}

/** Preset until touched ("assumed"), then the person's own ("entered"); nothing for a box deliberately emptied. */
function provOf(vals: Vals, key: string, hasDefault = true): 'assumed' | 'entered' | null {
  if (key in vals) return vals[key].trim() !== '' ? 'entered' : null
  return hasDefault ? 'assumed' : null
}

/**
 * Rovers relaying for each other: a lander and up to five rovers on a site,
 * and how long each goes without a path to Earth, alone and with the others
 * passing its data on. Starts from an assumed preset; typing over a figure
 * makes it the person's own. Nothing is asked for until "Work it out".
 */
export function MeshPanel({
  siteId,
  siteName,
  startIso,
  endIso,
}: {
  siteId: string
  siteName: string
  startIso: string | null
  endIso: string | null
}) {
  const [rows, setRows] = useState<MeshRow[]>(initialMeshRows)
  const [vals, setVals] = useState<Vals>({})
  const [nextKey, setNextKey] = useState(PRESET_NODES.length)
  const [asked, setAsked] = useState<MeshRequestDTO | null>(null)
  const q = useMesh(siteId, asked)
  const id = useId()

  const { body, errors } = useMemo(() => meshRequestFrom(rows, vals, startIso, endIso), [rows, vals, startIso, endIso])
  const changed = asked !== null && JSON.stringify(asked) !== JSON.stringify(body)
  const hasErrors = Object.keys(errors).length > 0

  const set = (k: string, v: string) => setVals((o) => ({ ...o, [k]: v }))

  const addRow = () => {
    if (rows.length >= MAX_NODES) return
    const k = nextKey
    setNextKey(k + 1)
    setRows((rs) => [...rs, { key: k, id: `n${k + 1}`, d: { ...ROVER, name: `Rover ${rs.length}` } }])
  }
  const removeRow = (k: number) => setRows((rs) => (rs.length > 1 ? rs.filter((r) => r.key !== k) : rs))

  if (!LIVE_SERVICE) return <SavedCopyNote what="how rovers could relay for each other" />

  const nameShown = (r: MeshRow) => (rowKey(r, 'name') in vals ? vals[rowKey(r, 'name')] : r.d.name)

  const field = (
    key: string,
    label: string,
    unit: string,
    def: string,
    opts: { hasDefault?: boolean; placeholder?: string; hint?: string } = {},
  ) => {
    const fid = `${id}-${key}`
    const p = provOf(vals, key, opts.hasDefault ?? def !== '')
    const err = errors[key]
    return (
      <div key={key} className="flex min-w-0 flex-col gap-1">
        <label htmlFor={fid} className="flex min-h-9 items-end justify-between gap-2 text-caption leading-4 text-ink-2">
          <span>{label}</span>
          <span className="shrink-0 font-mono text-ink-3">{unit}</span>
        </label>
        <TextInput
          id={fid}
          inputMode="decimal"
          autoComplete="off"
          value={key in vals ? vals[key] : def}
          placeholder={opts.placeholder}
          aria-invalid={err ? true : undefined}
          aria-describedby={`${fid}-p`}
          onChange={(e) => set(key, e.target.value)}
          className={`h-11 px-3 font-mono tabular-nums ${p === 'assumed' ? 'pw-scenario' : ''}`}
        />
        <span id={`${fid}-p`} className="flex flex-wrap items-center gap-x-2 text-caption leading-4">
          {p && <ProvTag p={p} />}
          {opts.hint && !p && <span className="text-ink-3">{opts.hint}</span>}
          {err && <span className="font-semibold text-alert">{err}</span>}
        </span>
      </div>
    )
  }

  const settingField = (s: SettingDef) => field(`s.${s.key}`, s.label, s.unit, shownDefault(s.def, s.scale, 3))

  return (
    <div className="flex min-w-0 flex-col gap-5">
      <p className="pw-scenario rounded-md px-3 py-2 text-small leading-5 text-ink">
        <strong className="font-semibold">A lander and two rovers: every figure is assumed.</strong> None is published or measured. Type over any
        figure to use your own; it then reads as entered. Positions are metres east and north of the site point.
      </p>

      <div className="flex flex-col gap-5">
        {rows.map((r, i) => (
          <fieldset key={r.key} className="flex min-w-0 flex-col gap-3 border-t border-line pt-3">
            <legend className="pw-eyebrow float-left mb-1 w-full">Node {i + 1}</legend>
            <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3 lg:grid-cols-4">
              <div className="col-span-2 flex min-w-0 flex-col gap-1 sm:col-span-1">
                <label htmlFor={`${id}-${rowKey(r, 'name')}`} className="flex min-h-9 items-end text-caption leading-4 text-ink-2">
                  Name
                </label>
                <TextInput
                  id={`${id}-${rowKey(r, 'name')}`}
                  autoComplete="off"
                  value={nameShown(r)}
                  onChange={(e) => set(rowKey(r, 'name'), e.target.value)}
                  className="h-11 px-3"
                />
              </div>
              {field(rowKey(r, 'east_m'), 'East offset', 'm', shownDefault(r.d.east_m, 1, 1), { hasDefault: r.d.east_m !== undefined, placeholder: 'needed' })}
              {field(rowKey(r, 'north_m'), 'North offset', 'm', shownDefault(r.d.north_m, 1, 1), { hasDefault: r.d.north_m !== undefined, placeholder: 'needed' })}
              {field(rowKey(r, 'antenna_height_m'), 'Antenna height', 'm', shownDefault(r.d.antenna_height_m, 1))}
              {field(rowKey(r, 'battery_capacity_wh'), 'Battery', 'Wh', shownDefault(r.d.battery_capacity_wh, 1))}
              {field(rowKey(r, 'initial_soc_fraction'), 'Charge at the start', '%', shownDefault(r.d.initial_soc_fraction, 0.01))}
              {field(rowKey(r, 'own_traffic_bps'), 'Own traffic', 'kbps', shownDefault(r.d.own_traffic_bps, 1000))}
              {field(rowKey(r, 'uplink_kbps'), 'Earth uplink rate', 'kbps', shownDefault(r.d.earth_uplink_bps, 1000), {
                hasDefault: r.d.earth_uplink_bps !== undefined,
                placeholder: 'none',
                hint: 'empty: no direct Earth link',
              })}
              {field(rowKey(r, 'uplink_w'), 'Earth uplink power', 'W', shownDefault(r.d.earth_uplink_power_w, 1), {
                hasDefault: r.d.earth_uplink_power_w !== undefined,
                placeholder: 'none',
                hint: 'empty: no direct Earth link',
              })}
              <div className="col-span-2 flex min-w-0 flex-col justify-end gap-1 sm:col-span-1">
                <label
                  htmlFor={`${id}-${rowKey(r, 'may_help')}`}
                  className={`flex min-h-11 cursor-pointer items-center gap-3 rounded-control border border-field px-3 text-small text-ink ${provOf(vals, rowKey(r, 'may_help')) === 'assumed' ? 'pw-scenario' : ''}`}
                >
                  <input
                    id={`${id}-${rowKey(r, 'may_help')}`}
                    type="checkbox"
                    className="size-5 shrink-0"
                    checked={rowKey(r, 'may_help') in vals ? vals[rowKey(r, 'may_help')] === 'true' : r.d.may_help}
                    onChange={(e) => set(rowKey(r, 'may_help'), e.target.checked ? 'true' : 'false')}
                  />
                  May help others
                </label>
                <span className="flex items-center text-caption leading-4">
                  <ProvTag p={provOf(vals, rowKey(r, 'may_help'))!} />
                </span>
              </div>
            </div>
            <div>
              <Button variant="secondary" disabled={rows.length <= 1} onClick={() => removeRow(r.key)}>
                Remove {nameShown(r).trim() || `node ${i + 1}`}
              </Button>
            </div>
          </fieldset>
        ))}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <Button variant="secondary" disabled={rows.length >= MAX_NODES} onClick={addRow}>
            Add a rover
          </Button>
          <p className="text-caption leading-caption text-ink-3">
            {rows.length} of {MAX_NODES} nodes. A new rover starts with the rover figures above; give it a position.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-x-4 gap-y-3 border-t border-line pt-3 sm:max-w-md">
        {field('s.loss_min', 'Count a gap after', 'minutes', String(MESH_LOSS_S / 60))}
        <p className="text-caption leading-caption text-ink-3">
          A loss of the direct link longer than this wakes a node&apos;s radio. One point every {num(MESH_STEP_S / 60, 0)} minutes.
        </p>
      </div>

      <Disclosure title="Radio and helper rules" meta="every figure assumed">
        <div className="flex flex-col gap-5 pb-2">
          <p className="pw-scenario rounded-md px-3 py-2 text-small leading-5 text-ink">
            These are assumed, not published. Type over any to use your own.
          </p>
          <fieldset className="flex min-w-0 flex-col gap-3">
            <legend className="pw-eyebrow float-left mb-1 w-full">Radio</legend>
            <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3 lg:grid-cols-4">
              {SETTINGS.filter((s) => s.group === 'radio').map(settingField)}
              <div className="flex min-w-0 flex-col gap-1">
                <label htmlFor={`${id}-pol`} className="flex min-h-9 items-end text-caption leading-4 text-ink-2">
                  Polarisation
                </label>
                <select
                  id={`${id}-pol`}
                  value={vals['s.polarisation'] ?? RADIO_DEFAULT.polarisation}
                  onChange={(e) => set('s.polarisation', e.target.value)}
                  className={`h-11 w-full min-w-0 rounded-control border border-field bg-panel px-3 text-small text-ink focus:border-focus ${provOf(vals, 's.polarisation') === 'assumed' ? 'pw-scenario' : ''}`}
                >
                  <option value="vertical">Vertical</option>
                  <option value="horizontal">Horizontal</option>
                </select>
                <span className="text-caption leading-4">
                  <ProvTag p={provOf(vals, 's.polarisation')!} />
                </span>
              </div>
            </div>
          </fieldset>
          <fieldset className="flex min-w-0 flex-col gap-3 border-t border-line pt-3">
            <legend className="pw-eyebrow float-left mb-1 w-full">Helper rules</legend>
            <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3 lg:grid-cols-4">
              {SETTINGS.filter((s) => s.group === 'guard').map(settingField)}
            </div>
          </fieldset>
        </div>
      </Disclosure>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Button variant="primary" arrow disabled={hasErrors || q.isFetching || !startIso || !endIso} onClick={() => setAsked(body)}>
          {q.isFetching ? 'Working it out…' : 'Work it out'}
        </Button>
        <p className="text-caption leading-caption text-ink-3">
          {!startIso || !endIso
            ? 'Choose dates first.'
            : `At ${siteName}, ${utcWords(Date.parse(startIso), true)} to ${utcWords(Date.parse(endIso), true)} UTC.`}
          {hasErrors && ' Correct the figures marked first.'}
        </p>
      </div>

      {q.isError && <ProblemPanel error={q.error} fallbackTitle="The relay could not be worked out" />}
      {q.data && asked && <MeshResult data={q.data} request={asked} stale={changed} />}
    </div>
  )
}

const STATE_WORDS: Record<string, string> = {
  deep_sleep: 'Deep sleep',
  standby: 'Standby',
  active_relay: 'Active relay',
}
const RULE_WORDS: Record<string, string> = {
  night: 'at night',
  charge_below_cutoff: 'charge below the cut-off',
  energy_quota: 'energy quota used',
  power_cap: 'power cap',
}
const SIGHT_WORDS = { clear: 'Clear', uncertain: 'Uncertain', blocked: 'Blocked' } as const

/** A state-of-charge fraction shown as a percentage, margin and all. */
function asPercent(q: QuantityDTO): QuantityDTO {
  const k = (v: number | null | undefined) => (typeof v === 'number' ? v * 100 : v)
  return { ...q, unit: '%', value: k(q.value) as number, pm: k(q.pm), lo: k(q.lo), hi: k(q.hi) }
}

const startsNote = (iso: string | null | undefined): ReactNode =>
  iso ? <span className="font-mono text-micro text-ink-3">starts {utcWords(Date.parse(iso), true)} UTC</span> : undefined

/** What came back, in the order a person reads it: the stretches, the map, the links, the cost, what is not modelled. */
export function MeshResult({ data, request, stale = false }: { data: MeshResponseDTO; request: MeshRequestDTO; stale?: boolean }) {
  const nameOf = (nodeId: string) => data.nodes.find((n) => n.id === nodeId)?.name ?? nodeId
  const mapNodes: MeshMapNode[] = request.nodes.map((n) => ({
    id: n.id,
    name: n.name ?? n.id,
    east_m: n.position.east_m,
    north_m: n.position.north_m,
    earthLink: n.earth_uplink_bps !== undefined,
  }))
  const shortened = data.nodes.filter((n) => {
    const l = n.longest_without_path_to_earth
    return l.with_mesh.value !== null && l.direct_only.value !== null && l.direct_only.value - l.with_mesh.value > 1e-6
  }).length
  const basis = data.nodes[0]?.longest_without_path_to_earth.basis
  const horizonRes = (data.meta.resolution ?? {}) as { dem_product?: string; dem_resolution_m?: number; max_range_m?: number }
  const horizonUnc = (data.meta.uncertainty ?? {}) as { dem_vertical_error_m?: number }

  return (
    <section aria-label="Rovers relaying, worked out" className={`flex min-w-0 flex-col gap-6 ${stale ? 'opacity-60' : ''}`}>
      {stale && (
        <p role="status" className="text-small leading-5 font-semibold text-ink">
          The figures have changed since this was worked out. Press Work it out again to update it.
        </p>
      )}

      <div className="flex flex-col gap-3">
        <h3 className="pw-eyebrow">Longest stretch without a path to Earth</h3>
        {data.nodes.map((n) => {
          const l = n.longest_without_path_to_earth
          return (
            <div key={n.id} data-node-stretch={n.id} className="flex min-w-0 flex-col gap-2 border-t border-line pt-3">
              <h4 className="m-0 text-body font-semibold text-ink">{n.name}</h4>
              <dl className="grid grid-cols-1 gap-x-4 gap-y-3 min-[480px]:grid-cols-3">
                <QuantityCell label="Direct only" q={l.direct_only} digits={0} note={startsNote(l.direct_only_starts_utc)} />
                <QuantityCell label="With the mesh, on links certainly clear" q={l.with_mesh} digits={0} note={startsNote(l.with_mesh_starts_utc)} />
                <div className="min-w-0 border-l border-dashed border-line-strong pl-3 opacity-80">
                  <QuantityCell label="If uncertain links also hold" q={l.with_mesh_if_uncertain_links_hold} digits={0} note="A condition, not a result." />
                </div>
              </dl>
            </div>
          )
        })}
        <p className="text-small leading-5 text-ink-2">
          {shortened === 0
            ? "On links certainly clear, the mesh shortened no node's longest stretch without a path to Earth."
            : `On links certainly clear, the mesh shortened the longest stretch for ${shortened} of ${data.nodes.length} nodes.`}{' '}
          The elevation model&apos;s height error ({num(data.terrain.vertical_error_m, Number.isInteger(data.terrain.vertical_error_m) ? 0 : 1)} m) leaves most low links uncertain on real terrain, so the
          certain gain is often nil, and the third figure is what it would be if those links held. A link is marked uncertain when its path passes
          within the height error of a ridge, where the map cannot tell whether terrain blocks it; only certainly clear links carry traffic in the
          main run and in the helper figures below.
        </p>
        {basis && (
          <Disclosure title="What the third figure assumes">
            <p className="text-small leading-5 text-ink-2">{basis}</p>
          </Disclosure>
        )}
      </div>

      <div className="flex flex-col gap-2">
        <h3 className="pw-eyebrow">Plan view</h3>
        <MeshMap nodes={mapNodes} links={data.links} />
      </div>

      <div className="flex min-w-0 flex-col gap-2">
        <h3 className="pw-eyebrow">
          Links <ProvTag p="computed" />
        </h3>
        <div
          className="max-w-full overflow-x-auto rounded-md border border-line"
          tabIndex={0}
          role="region"
          aria-label="Links between the nodes, scrolls sideways"
        >
          <table className="w-full min-w-[34rem] border-collapse text-left text-small">
            <thead className="text-caption leading-4 text-ink-2">
              <tr className="border-b border-line">
                <th scope="col" className="px-3 py-2 font-semibold">
                  Pair
                </th>
                <th scope="col" className="px-3 py-2 font-semibold">
                  When (UTC)
                </th>
                <th scope="col" className="px-3 py-2 font-semibold">
                  Distance
                </th>
                <th scope="col" className="px-3 py-2 font-semibold">
                  Line of sight
                </th>
                <th scope="col" className="px-3 py-2 font-semibold">
                  Fresnel zone
                </th>
                <th scope="col" className="px-3 py-2 font-semibold">
                  Path loss
                </th>
                <th scope="col" className="px-3 py-2 font-semibold">
                  SNR
                </th>
                <th scope="col" className="px-3 py-2 font-semibold">
                  Usable
                </th>
              </tr>
            </thead>
            <tbody>
              {data.links.map((l) => (
                <tr key={`${l.a}-${l.b}-${l.start_s}`} className="border-b border-line last:border-b-0">
                  <th scope="row" className="px-3 py-2 font-normal whitespace-nowrap text-ink">
                    {nameOf(l.a)} to {nameOf(l.b)}
                  </th>
                  <td className="px-3 py-2 font-mono text-caption tabular-nums whitespace-nowrap">
                    {utcWords(Date.parse(l.start_utc), true)} to {utcWords(Date.parse(l.end_utc), true)}
                  </td>
                  <td className="px-3 py-2 font-mono tabular-nums">{num(l.distance_m, 0)} m</td>
                  <td className="px-3 py-2">{SIGHT_WORDS[l.terrain_sight]}</td>
                  <td className="px-3 py-2">{SIGHT_WORDS[l.terrain_fresnel]}</td>
                  <td className="px-3 py-2 font-mono tabular-nums">{num(l.path_loss_db, 1)} dB</td>
                  <td className="px-3 py-2 font-mono tabular-nums">{num(l.snr_db, 1)} dB</td>
                  <td className="px-3 py-2">{l.usable ? 'Yes' : 'No'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="flex flex-col gap-3">
        <h3 className="pw-eyebrow">What helping cost each helper</h3>
        <p className="text-caption leading-caption text-ink-3">
          A node enters active relay only during steps where it sends or forwards traffic over a certainly clear mesh link; while its direct link is
          down with no usable route, it stays in standby (0 W; idle listening power is not modelled).
        </p>
        {data.helpers.length === 0 && <p className="text-small leading-5 text-ink-2">No node was allowed to help others.</p>}
        {data.helpers.map((h) => (
          <HelperCost key={h.id} h={h} name={nameOf(h.id)} hours={data.nodes.find((n) => n.id === h.id)?.time_in_state_h} />
        ))}
      </div>

      <div className="flex flex-col gap-1 border-t border-line pt-3">
        <h3 className="pw-eyebrow">Terrain basis</h3>
        <p className="text-small leading-5 text-ink-2">
          Two elevation maps are used together: peer-to-peer links and off-site node skylines (to 20 km) use{' '}
          <span className="font-mono text-caption">{data.terrain.products.join(' + ')}</span> (posts every{' '}
          {num(data.terrain.post_m, Number.isInteger(data.terrain.post_m) ? 0 : 1)} m, height error{' '}
          {num(data.terrain.vertical_error_m, Number.isInteger(data.terrain.vertical_error_m) ? 0 : 1)} m), while the site point&apos;s own{' '}
          {num((horizonRes.max_range_m ?? 50000) / 1000, 0)} km skyline in the response metadata uses{' '}
          <span className="font-mono text-caption">{horizonRes.dem_product ?? 'LOLA_LDEM_80S_20M'}</span> (posts every{' '}
          {num(horizonRes.dem_resolution_m ?? 20, 0)} m, height error {num(horizonUnc.dem_vertical_error_m ?? 4, 0)} m).{' '}
          <ProvTag p="published" />
        </p>
      </div>

      <Disclosure title="What this does not model" meta={`${data.not_modelled.length} things`}>
        <ul className="flex list-disc flex-col gap-1.5 pl-5 text-small leading-5 text-ink-2">
          {data.not_modelled.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
      </Disclosure>
      <p className="font-mono text-micro text-ink-3">
        Worked out {utcWords(Date.parse(data.meta.computed_at), true)} UTC, engine {data.meta.engine_version}. One point every{' '}
        {num(data.step_s / 60, 0)} minutes.
      </p>
    </section>
  )
}

function HelperCost({ h, name, hours }: { h: MeshHelperDTO; name: string; hours: Record<string, number> | undefined }) {
  const refused = Object.entries(h.refused_hours_by_rule).filter(([, v]) => v > 0)
  return (
    <div data-helper={h.id} className="flex min-w-0 flex-col gap-3 border-t border-line pt-3">
      <h4 className="m-0 text-body font-semibold text-ink">{name}</h4>
      {hours && (
        <p className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-small text-ink-2">
          <span className="text-caption text-ink-3">Hours in each radio state</span>
          {Object.entries(hours).map(([state, v]) => (
            <span key={state}>
              {STATE_WORDS[state] ?? state.replace(/_/g, ' ')} <span className="font-mono text-ink tabular-nums">{num(v, 0)} h</span>
            </span>
          ))}
          <ProvTag p="computed" />
        </p>
      )}
      <dl className="grid grid-cols-1 gap-x-4 gap-y-3 min-[420px]:grid-cols-2 lg:grid-cols-3">
        <QuantityCell label="Energy spent forwarding" q={h.energy_spent_wh} digits={1} />
        <QuantityCell label="Forwarded" q={h.forwarded_mb} digits={1} />
        <QuantityCell label="Dropped" q={h.dropped_mb} digits={1} />
        <QuantityCell label="Lowest state of charge" q={asPercent(h.minimum_state_of_charge)} digits={0} />
      </dl>
      <p className="text-small leading-5 text-ink-2">
        {h.refusals.length === 0 ? 'Refusals: none.' : `Refusals: ${h.refusals.length}.`}
        {refused.length > 0 && (
          <>
            {' '}
            Hours it refused to forward:{' '}
            {refused.map(([rule, v], i) => (
              <span key={rule}>
                {i > 0 && ', '}
                {RULE_WORDS[rule] ?? rule.replace(/_/g, ' ')} <span className="font-mono tabular-nums">{num(v, 0)} h</span>
              </span>
            ))}
            .
          </>
        )}
      </p>
    </div>
  )
}
