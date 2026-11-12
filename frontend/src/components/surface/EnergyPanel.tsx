import { useId, useMemo, useState } from 'react'
import { useEnergy } from '../../lib/api/surface'
import { LIVE_SERVICE } from '../../lib/api/home'
import type {
  ArrayGeometry,
  EchoedFigureDTO,
  EnergyRequestDTO,
  EnergyResponseDTO,
  LanderField,
  LanderInDTO,
  LanderNumberField,
} from '../../lib/api/surface.types'
import { TextInput } from '../lifecycle/Forms'
import { ProblemPanel } from '../States'
import { Button, Disclosure } from '../ui'
import { EnergyCharts } from './EnergyCharts'
import { num, unitWord, utcWords } from './helpers'
import { ProvTag, QuantityCell, SavedCopyNote } from './parts'

/** The two examples in `data/catalogues/lander_examples.json`; every figure in both is assumed. */
export const LANDER_EXAMPLES = [
  { id: 'nova-c-class-assumed-body-panels', name: 'Nova-C-class, panels on its six sides' },
  { id: 'nova-c-class-assumed', name: 'Nova-C-class, one panel on the top deck' },
] as const

const GEOMETRY_WORDS: Record<ArrayGeometry, string> = {
  vertical_faces: 'Panels on the side faces',
  top_deck_flat: 'One flat panel on the top deck',
  sun_tracking: 'A panel that tracks the Sun',
}

interface FieldDef {
  key: LanderNumberField
  label: string
  unit: string
  /** Shown only for panels on the side faces. */
  facesOnly?: boolean
}

const GROUPS: { title: string; fields: FieldDef[] }[] = [
  {
    title: 'Array',
    fields: [
      { key: 'array_area_m2', label: 'Panel area (one face, if on the sides)', unit: 'm²' },
      { key: 'face_count', label: 'Side faces', unit: 'count', facesOnly: true },
      { key: 'face_azimuth_offset_deg', label: 'Bearing of the first face', unit: '°', facesOnly: true },
      { key: 'cell_efficiency', label: 'Cell efficiency', unit: '0–1' },
      { key: 'dust_loss_fraction', label: 'Dust loss', unit: '0–1' },
    ],
  },
  {
    title: 'Battery and loads',
    fields: [
      { key: 'battery_capacity_wh', label: 'Battery capacity', unit: 'Wh' },
      { key: 'initial_soc_fraction', label: 'Charge at the start', unit: '0–1' },
      { key: 'avionics_w', label: 'Avionics', unit: 'W' },
      { key: 'payload_w', label: 'Payload', unit: 'W' },
      { key: 'load_dissipation_fraction', label: 'Share of load that heats the lander body (bus)', unit: '0–1' },
      { key: 'heater_power_w', label: 'Heater power', unit: 'W' },
      { key: 'heater_setpoint_c', label: 'Heater comes on below', unit: '°C' },
    ],
  },
  {
    title: 'Thermal',
    fields: [
      { key: 'initial_bus_temp_c', label: 'Inside the lander (bus) at the start', unit: '°C' },
      { key: 'operational_min_c', label: 'Operational minimum', unit: '°C' },
      { key: 'survival_min_c', label: 'Survival minimum', unit: '°C' },
      { key: 'heat_capacity_j_per_k', label: 'Heat capacity', unit: 'J/K' },
      { key: 'bus_absorptivity', label: 'Lander body (bus) absorptivity', unit: '0–1' },
      { key: 'bus_emissivity', label: 'Lander body (bus) emissivity', unit: '0–1' },
      { key: 'bus_side_area_m2', label: 'Lander body (bus) side area (Sun low)', unit: 'm²' },
      { key: 'bus_top_area_m2', label: 'Lander body (bus) top area (Sun high)', unit: 'm²' },
      { key: 'base_area_m2', label: 'Base area', unit: 'm²' },
      { key: 'radiator_area_m2', label: 'Radiator area', unit: 'm²' },
      { key: 'radiator_emissivity', label: 'Radiator emissivity', unit: '0–1' },
      { key: 'view_factor', label: 'View factor to the ground', unit: '0–1' },
      { key: 'regolith_emissivity', label: 'Ground emissivity', unit: '0–1' },
      { key: 'regolith_absorptivity', label: 'Ground absorptivity', unit: '0–1' },
    ],
  },
]

const ALL_FIELDS = GROUPS.flatMap((g) => g.fields)
const LABEL: Record<string, string> = Object.fromEntries([
  ['array_geometry', 'Panel layout'],
  ...ALL_FIELDS.map((f) => [f.key, f.label]),
])

type Entered = Partial<Record<LanderField, string>>

/** Parse what was typed: numbers for every figure but the layout; the errors by field. */
export function landerFromEntered(entered: Entered): { lander: LanderInDTO; errors: Partial<Record<LanderField, string>> } {
  const lander: LanderInDTO = {}
  const errors: Partial<Record<LanderField, string>> = {}
  for (const [k, raw] of Object.entries(entered) as [LanderField, string][]) {
    const v = raw.trim()
    if (v === '') continue
    if (k === 'array_geometry') {
      lander.array_geometry = v as ArrayGeometry
      continue
    }
    const n = Number(v)
    if (!Number.isFinite(n)) errors[k] = 'Type a number'
    else lander[k] = n
  }
  return { lander, errors }
}

/**
 * Power and temperature through the dates for a lander the person describes
 * (ADR-21). Starts from an assumed example; every figure typed over it becomes
 * the person's own and is sent as entered. Nothing is asked for until "Work it
 * out"; the figures the service used come back with their provenance and fill
 * the form.
 */
export function EnergyPanel({
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
  const [exampleId, setExampleId] = useState<string>(LANDER_EXAMPLES[0].id)
  const [entered, setEntered] = useState<Entered>({})
  const [asked, setAsked] = useState<EnergyRequestDTO | null>(null)
  const q = useEnergy(siteId, asked)
  const id = useId()

  const { lander, errors } = useMemo(() => landerFromEntered(entered), [entered])
  const body: EnergyRequestDTO = {
    start: startIso,
    end: endIso,
    lander,
    ...(exampleId ? { lander_example_id: exampleId } : {}),
  }
  const changed = asked !== null && JSON.stringify(asked) !== JSON.stringify(body)
  const nEntered = Object.values(entered).filter((v) => v && v.trim() !== '').length
  const hasErrors = Object.keys(errors).length > 0

  // The figures the service echoed, while they still describe the example chosen now.
  const echo = q.data && (asked?.lander_example_id ?? '') === exampleId ? q.data.inputs : undefined
  const shown = (k: LanderField): string => {
    if (entered[k] !== undefined) return entered[k] as string
    const e = echo?.[k]
    return e && e.value !== null && e.value !== undefined ? String(e.value) : ''
  }
  const provOf = (k: LanderField) => (entered[k] && entered[k]!.trim() !== '' ? 'entered' : (echo?.[k]?.provenance ?? (exampleId ? 'assumed' : null)))
  const geometry = (shown('array_geometry') || null) as ArrayGeometry | null

  const set = (k: LanderField, v: string) =>
    setEntered((e) => {
      const next = { ...e }
      if (v.trim() === '') delete next[k]
      else next[k] = v
      return next
    })

  if (!LIVE_SERVICE) return <SavedCopyNote what="power and temperature" />

  return (
    <div className="flex min-w-0 flex-col gap-5">
      <div className="flex flex-col gap-3">
        <label htmlFor={`${id}-ex`} className="text-caption leading-caption font-semibold text-ink-2">
          Start from
        </label>
        <select
          id={`${id}-ex`}
          value={exampleId}
          onChange={(e) => setExampleId(e.target.value)}
          className="h-12 w-full max-w-md min-w-0 rounded-control border border-field bg-panel px-3.5 text-body text-ink focus:border-focus"
        >
          {LANDER_EXAMPLES.map((x) => (
            <option key={x.id} value={x.id}>
              Example lander: {x.name}
            </option>
          ))}
          <option value="">No example: I will type every figure</option>
        </select>
        {exampleId ? (
          <p className="pw-scenario rounded-md px-3 py-2 text-small leading-5 text-ink">
            {nEntered === 0 ? (
              <>
                <strong className="font-semibold">Example lander: every figure is assumed.</strong> None is published; each was derived from the
                lander&apos;s size, and the reason shows beside it after the first run. Type over any figure to use your own.
              </>
            ) : (
              <>
                <strong className="font-semibold">
                  Example lander with {nEntered} of your figure{nEntered === 1 ? '' : 's'}.
                </strong>{' '}
                The rest are still assumed. Clear a box to go back to the example&apos;s figure.
              </>
            )}
          </p>
        ) : (
          <p className="text-small leading-5 text-ink-2">Every figure is needed; the service names any that is missing.</p>
        )}
        {exampleId && !echo && (
          <p className="text-caption leading-caption text-ink-3">The example&apos;s own figures fill these boxes once it has been worked out.</p>
        )}
      </div>

      <div className="flex flex-col gap-5">
        {GROUPS.map((g) => (
          <fieldset key={g.title} className="flex min-w-0 flex-col gap-3 border-t border-line pt-3">
            <legend className="pw-eyebrow float-left mb-1 w-full">{g.title}</legend>
            <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3 lg:grid-cols-4">
              {g.title === 'Array' && (
                <div className="col-span-2 flex min-w-0 flex-col gap-1 sm:col-span-1">
                  <label htmlFor={`${id}-geo`} className="text-caption leading-caption text-ink-2">
                    Panel layout
                  </label>
                  <select
                    id={`${id}-geo`}
                    value={entered.array_geometry ?? ''}
                    onChange={(e) => set('array_geometry', e.target.value)}
                    aria-describedby={`${id}-geo-p`}
                    className={`h-11 w-full min-w-0 rounded-control border border-field bg-panel px-3 text-small text-ink focus:border-focus ${provOf('array_geometry') === 'assumed' ? 'pw-scenario' : ''}`}
                  >
                    <option value="">
                      {exampleId ? `As the example${echo?.array_geometry ? `: ${GEOMETRY_WORDS[echo.array_geometry.value as ArrayGeometry] ?? echo.array_geometry.value}` : ''}` : 'Choose'}
                    </option>
                    {(Object.keys(GEOMETRY_WORDS) as ArrayGeometry[]).map((k) => (
                      <option key={k} value={k}>
                        {GEOMETRY_WORDS[k]}
                      </option>
                    ))}
                  </select>
                  <span id={`${id}-geo-p`}>
                    {provOf('array_geometry') && (
                      <ProvTag
                        p={provOf('array_geometry')!}
                        detail={echo?.array_geometry?.source && provOf('array_geometry') !== 'entered' ? echo.array_geometry.source : undefined}
                        className={echo?.array_geometry?.source && provOf('array_geometry') !== 'entered' ? 'cursor-help' : ''}
                      />
                    )}
                  </span>
                </div>
              )}
              {g.fields
                .filter((f) => !f.facesOnly || geometry === null || geometry === 'vertical_faces')
                .map((f) => {
                  const fid = `${id}-${f.key}`
                  const p = provOf(f.key)
                  const err = errors[f.key]
                  const why = echo?.[f.key]?.source
                  return (
                    <div key={f.key} className="flex min-w-0 flex-col gap-1">
                      <label htmlFor={fid} className="flex min-h-9 items-end justify-between gap-2 text-caption leading-4 text-ink-2">
                        <span>{f.label}</span>
                        <span className="shrink-0 font-mono text-ink-3">{f.unit}</span>
                      </label>
                      <TextInput
                        id={fid}
                        inputMode="decimal"
                        autoComplete="off"
                        value={shown(f.key)}
                        placeholder={exampleId ? 'example' : 'needed'}
                        aria-invalid={err ? true : undefined}
                        aria-describedby={`${fid}-p`}
                        onChange={(e) => set(f.key, e.target.value)}
                        className={`h-11 px-3 font-mono tabular-nums ${p === 'assumed' ? 'pw-scenario' : ''}`}
                      />
                      <span id={`${fid}-p`} className="flex flex-wrap items-center gap-x-2 text-caption leading-4">
                        {p && <ProvTag p={p} detail={why && p !== 'entered' ? why : undefined} className={why && p !== 'entered' ? 'cursor-help' : ''} />}
                        {why && p !== 'entered' && <span className="sr-only">{why}</span>}
                        {err && <span className="font-semibold text-alert">{err}</span>}
                      </span>
                    </div>
                  )
                })}
            </div>
          </fieldset>
        ))}
      </div>

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

      {q.isError && <ProblemPanel error={q.error} fallbackTitle="Power and temperature could not be worked out" />}
      {q.data && (
        <EnergyResult data={q.data} stale={changed} />
      )}
    </div>
  )
}

/** What came back: the key quantities, the three charts, the ground basis and what is not modelled. */
export function EnergyResult({ data, stale = false }: { data: EnergyResponseDTO; stale?: boolean }) {
  const figure = (k: LanderField) => {
    const v = data.inputs[k]?.value
    return typeof v === 'number' ? v : null
  }
  const k = data.key
  const when = (iso: string | null | undefined) => (iso ? `${utcWords(Date.parse(iso), true)} UTC` : undefined)
  const g = data.ground
  const model = data.model as Record<string, unknown>
  return (
    <section aria-label="Power and temperature, worked out" className={`flex min-w-0 flex-col gap-5 ${stale ? 'opacity-60' : ''}`}>
      {stale && (
        <p role="status" className="text-small leading-5 font-semibold text-ink">
          The figures have changed since this was worked out. Press Work it out again to update it.
        </p>
      )}
      <dl className="grid grid-cols-1 gap-x-5 gap-y-4 min-[420px]:grid-cols-2 lg:grid-cols-3">
        <QuantityCell label="Energy generated" q={k.energy_generated} digits={1} />
        <QuantityCell label="Lowest battery charge" q={k.lowest_soc} digits={0} />
        <QuantityCell label="Battery empties, hours after the start" q={k.battery_empty_at} digits={1} note={when(k.battery_empty_at.value_utc)} />
        <QuantityCell label="Coldest inside the lander (bus)" q={k.lowest_bus_temperature} digits={0} />
        <QuantityCell label="Hours below the operational minimum" q={k.hours_below_operational} digits={1} />
        <QuantityCell
          label="Below the survival minimum, hours after the start"
          q={k.survival_threshold_crossed_at}
          digits={1}
          note={when(k.survival_threshold_crossed_at.value_utc)}
        />
      </dl>

      <EnergyCharts data={data} operationalC={figure('operational_min_c')} survivalC={figure('survival_min_c')} capacityWh={figure('battery_capacity_wh')} />

      <div className="flex flex-col gap-1 border-t border-line pt-3">
        <h3 className="pw-eyebrow">Ground temperature basis</h3>
        {g.covered ? (
          <p className="text-small leading-5 text-ink-2">
            Diviner, {g.n_triangles ?? 'some'} triangles within {num(Number(g.radius_m ?? 0), 0)} m of the site
            {g.dark_ground_k && <>: dark ground {kRange(g.dark_ground_k)}</>}
            {g.lit_ground_cap_k && <>, sunlit ground at most {kRange(g.lit_ground_cap_k)}</>}. Their spread is the band on the charts: a single-node
            thermal balance between two steady-state ground bounds (Diviner annual average and annual maximum), which is a bounding range, not a
            weather forecast, and the solid curve is the midpoint of those two bounds, not a best estimate.{' '}
            {g.source && (
              <a href={g.source} target="_blank" rel="noreferrer" className="text-earth underline underline-offset-2">
                Diviner data
              </a>
            )}{' '}
            <ProvTag p="published" />
          </p>
        ) : (
          <p className="text-small leading-5 text-ink-2">
            Outside the product&apos;s coverage: cold end only (a steady-state bound, not a forecast).{g.reason ? ` ${g.reason}` : ''}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-2">
        <Disclosure title="The lander's figures and where each came from" meta={`${Object.keys(data.inputs).length} figures`}>
          <ul className="flex flex-col divide-y divide-line">
            {(Object.entries(data.inputs) as [LanderField, EchoedFigureDTO][]).map(([key, f]) => (
              <li key={key} className="flex flex-col gap-1 py-2.5">
                <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className="text-small text-ink">{LABEL[key] ?? key}</span>
                  <span className="font-mono text-small text-ink tabular-nums">
                    {typeof f.value === 'number' ? num(f.value) : key === 'array_geometry' ? (GEOMETRY_WORDS[f.value as ArrayGeometry] ?? f.value) : f.value}{' '}
                    {unitWord(f.unit)}
                  </span>
                  <ProvTag p={f.provenance} />
                </span>
                {f.source && <span className="text-caption leading-caption text-ink-3">{f.source}</span>}
                {typeof f.value === 'number' && f.no_margin_reason && (
                  <span className="text-caption leading-caption text-ink-3">No margin: {f.no_margin_reason}.</span>
                )}
              </li>
            ))}
          </ul>
        </Disclosure>
        <Disclosure title="What this does not model" meta={`${data.not_modelled.length} things`}>
          <ul className="flex list-disc flex-col gap-1.5 pl-5 text-small leading-5 text-ink-2">
            {data.not_modelled.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </Disclosure>
        <Disclosure title="How this was worked out">
          <ul className="flex flex-col gap-1.5 text-small leading-5 text-ink-2">
            {typeof model.solar_irradiance === 'string' && <li>Sunlight: {model.solar_irradiance}.</li>}
            {typeof model.lit === 'string' && <li>Lit means {model.lit}.</li>}
            {typeof model.runs === 'string' && <li>Runs: {model.runs}.</li>}
            <li>
              One point every {num(data.step_s / 60, 0)} minutes. Worked out {utcWords(Date.parse(data.meta.computed_at), true)} UTC, engine{' '}
              {data.meta.engine_version}.
            </li>
          </ul>
        </Disclosure>
      </div>
    </section>
  )
}

function kRange(r: { lo: number; hi: number | null }): string {
  return r.hi === null ? `from ${num(r.lo, 0)} K (warm end unknown)` : `${num(r.lo, 0)} to ${num(r.hi, 0)} K`
}
