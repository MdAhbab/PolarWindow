import { useId, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import type {
  AssumptionDTO,
  AssumptionFieldDTO,
  AssumptionFieldId,
  InterpretedDTO,
  ScenarioDTO,
  ScenarioGapsDTO,
  ScenarioSection,
} from '../../lib/api/experience.types'
import { useInterpret, useScenario, useScenarioGaps, useStartScenario } from '../../lib/api/scenarios'
import { useSnapshotActive } from '../../lib/api/snapshot'
import { Field, TextArea, TextInput, WriteProblem, useNamedWriter } from '../lifecycle/Forms'
import { Select } from '../Select'
import { StatePanel, UNDER_QUESTION } from '../lifecycle/Section'
import { ProblemPanel, Skeleton } from '../States'
import { Button, Disclosure, Panel } from '../ui'
import { AssumptionBasisNote, BasisTag } from './Basis'
import { OFFLINE_WORDS } from './ScenarioEntry'
import { useActiveScenario } from './store'
import { STEP_NAME, displayFor, isEmptyValue, withScenario, type FieldValue } from './words'

type Values = Partial<Record<AssumptionFieldId, AssumptionDTO | null>>

/**
 * The builder (`?scenario=new`): say what to assume in words, or set it in the
 * form; see how it was read; watch each value's basis; then work it out.
 * With `editFrom` it opens prefilled from an earlier scenario's assumptions.
 */
export function ScenarioBuilder({
  missionId,
  section,
  editFrom,
}: {
  missionId: string
  section: ScenarioSection
  editFrom?: string | null
}) {
  const offline = useSnapshotActive()
  const gaps = useScenarioGaps(missionId, !offline)
  const base = useScenario(editFrom ?? undefined)
  const loc = useLocation()
  const back = `${loc.pathname}${withScenario(loc.search, editFrom ?? null, { edit: null })}`

  if (offline) {
    return (
      <StatePanel
        icon="offline"
        title="Scenarios need the live service"
        detail={OFFLINE_WORDS}
        action={
          <Link to={`${loc.pathname}${withScenario(loc.search, null, { edit: null })}`} className="inline-flex min-h-11 items-center text-body font-semibold underline">
            Back to the record
          </Link>
        }
      />
    )
  }
  if (gaps.error) {
    return <ProblemPanel error={gaps.error} fallbackTitle="The scenario builder could not be loaded" onRetry={() => void gaps.refetch()} />
  }
  if (!gaps.data || (editFrom && base.isPending)) {
    return (
      <div className={`${UNDER_QUESTION} flex flex-col gap-3`} aria-busy="true">
        <span className="sr-only" role="status">
          Loading the scenario builder
        </span>
        <Skeleton className="h-28" />
        <Skeleton className="h-64" />
      </div>
    )
  }
  return <BuilderForm missionId={missionId} section={section} gaps={gaps.data} base={base.data ?? null} back={back} />
}

function initialValues(gaps: ScenarioGapsDTO, base: ScenarioDTO | null): Values {
  const out: Values = {}
  for (const f of gaps.fields) {
    out[f.field] = base ? (base.assumptions.find((a) => a.field === f.field) ?? f.default) : f.default
  }
  return out
}

function BuilderForm({
  missionId,
  section,
  gaps,
  base,
  back,
}: {
  missionId: string
  section: ScenarioSection
  gaps: ScenarioGapsDTO
  base: ScenarioDTO | null
  back: string
}) {
  const loc = useLocation()
  const navigate = useNavigate()
  const remember = useActiveScenario((s) => s.remember)
  const writer = useNamedWriter()
  const interpret = useInterpret(missionId)
  const start = useStartScenario(missionId)
  const [prompt, setPrompt] = useState(base?.prompt ?? '')
  const [name, setName] = useState('')
  const [values, setValues] = useState<Values>(() => initialValues(gaps, base))
  const [reading, setReading] = useState<InterpretedDTO | null>(null)
  const [problem, setProblem] = useState<unknown>(null)
  const promptId = useId()
  const readId = useId()
  const whyId = useId()

  const mine = gaps.fields.filter((f) => f.sections.includes(section))
  const others = gaps.fields.filter((f) => !f.sections.includes(section))
  const set = (f: AssumptionFieldDTO, v: FieldValue) => {
    setValues((cur) => ({
      ...cur,
      [f.field]: isEmptyValue(v)
        ? f.default
        : { field: f.field, label: f.label, value: v, display: displayFor(f, v), unit: f.unit, basis: 'you', source: null, note: null },
    }))
  }
  const reset = (f: AssumptionFieldDTO) => setValues((cur) => ({ ...cur, [f.field]: f.default }))

  const missing = mine.filter((f) => f.default === null && isEmptyValue(values[f.field]?.value))
  const youSet = gaps.fields.map((f) => values[f.field]).filter((a): a is AssumptionDTO => Boolean(a) && a!.basis === 'you')

  const read = async () => {
    if (!prompt.trim() || interpret.isPending) return
    setProblem(null)
    if (!(await writer.ensure())) return
    interpret.mutate(
      { prompt: prompt.trim(), section },
      {
        onSuccess: (r) => {
          setReading(r)
          setValues((cur) => {
            const next = { ...cur }
            for (const a of r.assumptions) if (gaps.fields.some((f) => f.field === a.field)) next[a.field] = a
            return next
          })
        },
        onError: (e) => setProblem(e),
      },
    )
  }

  const work = async () => {
    if (missing.length || start.isPending) return
    setProblem(null)
    if (!(await writer.ensure())) return
    start.mutate(
      {
        name: name.trim() || null,
        prompt: prompt.trim() || null,
        assumptions: youSet.map((a) => ({ field: a.field, value: a.value })),
      },
      {
        onSuccess: (dto) => {
          remember(missionId, dto.id)
          navigate(`${loc.pathname}${withScenario(loc.search, dto.id, { edit: null })}`)
        },
        onError: (e) => setProblem(e),
      },
    )
  }

  return (
    <div className={`${UNDER_QUESTION} flex flex-col gap-6`}>
      <ScenarioIntro name={base?.name ?? null} />

      <Panel className="flex flex-col gap-4 p-5 sm:p-6">
        <div className="flex flex-col gap-2">
          <label htmlFor={promptId} className="text-control font-semibold text-ink">
            Say what to assume
          </label>
          <p className="max-w-3xl text-small leading-5 text-ink-2">
            In your own words: a vehicle, a launch month, a landing spot, how many days on the surface. Or skip this and set the values below.
          </p>
          <TextArea
            id={promptId}
            value={prompt}
            placeholder="Launch on Falcon Heavy in March, 10 days on the surface"
            aria-describedby={reading ? readId : undefined}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault()
                void read()
              }
            }}
          />
        </div>
        {gaps.suggestions.length > 0 && (
          <ul className="flex flex-wrap gap-2" aria-label="Examples">
            {gaps.suggestions.map((s) => (
              <li key={s}>
                <button
                  type="button"
                  onClick={() => setPrompt(s)}
                  className="pw-press inline-flex min-h-11 items-center rounded-pill border border-line-strong bg-tray px-4 py-2 text-left text-small text-ink-2 hover:bg-inset hover:text-ink"
                >
                  {s}
                </button>
              </li>
            ))}
          </ul>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={() => void read()} disabled={!prompt.trim() || interpret.isPending}>
            {interpret.isPending ? 'Reading…' : 'Read it'}
          </Button>
          <span className="text-caption text-ink-3">Reading only fills in the form below. Nothing is worked out yet.</span>
        </div>
        <div id={readId} role="status" aria-live="polite">
          {reading && <ReadBack r={reading} />}
        </div>
      </Panel>

      <section aria-labelledby={`${promptId}-assume`} className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <h3 id={`${promptId}-assume`} className="pw-eyebrow">
            What this scenario assumes for {STEP_NAME[section]}
          </h3>
          <p className="max-w-3xl text-small leading-5 text-ink-2">
            Each value says where it comes from. Change one and it becomes yours; reset it to go back to what was resolved.
          </p>
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          {mine.map((f) => (
            <FieldRow key={f.field} f={f} current={values[f.field] ?? null} onChange={(v) => set(f, v)} onReset={() => reset(f)} />
          ))}
        </div>
        {others.length > 0 && (
          <Disclosure title="Assumptions for the other steps" meta={`${others.length} more`}>
            <div className="grid gap-4 lg:grid-cols-2">
              {others.map((f) => (
                <FieldRow key={f.field} f={f} current={values[f.field] ?? null} onChange={(v) => set(f, v)} onReset={() => reset(f)} />
              ))}
            </div>
          </Disclosure>
        )}
      </section>

      <Panel className="flex flex-col gap-4 p-5 sm:p-6">
        <Field label="Name this scenario (optional)" hint="Shown above the answer. Left empty, it is named from the assumptions.">
          {(p) => <TextInput {...p} value={name} onChange={(e) => setName(e.target.value)} maxLength={80} />}
        </Field>
        {writer.fields}
        {problem != null && <WriteProblem error={problem} />}
        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="primary"
            arrow
            room={['Work it out', 'Starting…']}
            onClick={() => void work()}
            disabled={missing.length > 0 || start.isPending || writer.offline}
            describedBy={missing.length ? whyId : undefined}
          >
            {start.isPending ? 'Starting…' : 'Work it out'}
          </Button>
          <Link to={back} className="inline-flex h-12 items-center rounded-pill px-4 text-control font-semibold text-ink-2 no-underline hover:bg-inset hover:text-ink">
            Cancel
          </Link>
        </div>
        {missing.length > 0 && (
          <p id={whyId} className="text-small leading-5 text-ink-2">
            Still needed for {STEP_NAME[section]}: {missing.map((f) => f.label.toLowerCase()).join(', ')}.
          </p>
        )}
        {reading?.matches_preset && (
          <p className="text-small leading-5 text-ink-2">This matches a ready-made scenario, so working it out opens it at once.</p>
        )}
      </Panel>
    </div>
  )
}

/** What a scenario is, said once at the top of the builder. */
function ScenarioIntro({ name }: { name: string | null }) {
  return (
    <div className="pw-scenario flex max-w-3xl flex-col gap-1.5 rounded-sheet border border-dashed border-ink-3 p-4">
      <p className="text-control font-semibold text-ink">{name ? `Editing: ${name}` : 'A scenario'}</p>
      <p className="text-small leading-5 text-ink-2">
        A scenario works a step out from assumed values instead of the mission’s record. It is always labelled as one, with each assumption
        and where it came from, and it is never written into the record.
      </p>
    </div>
  )
}

/** How the prompt was read, in plain words. */
function ReadBack({ r }: { r: InterpretedDTO }) {
  return (
    <div className="flex flex-col gap-2 border-l-2 border-line-strong pl-3">
      <p className="text-body leading-6 text-ink">
        <span className="font-semibold">Read as:</span> {r.interpreted_as}
      </p>
      <p className="text-small leading-5 text-ink-2">
        {r.method === 'rules'
          ? 'No AI model is set up on this server, so only names, dates and day counts were read from your words. Check the values below.'
          : 'Read by the AI model. It only turned your words into the values below; check them, and change any.'}
      </p>
      {r.unresolved.length > 0 && (
        <div className="flex flex-col gap-1">
          <p className="text-small font-semibold text-ink">Could not be turned into a value:</p>
          <ul className="list-disc pl-5 text-small leading-5 text-ink-2">
            {r.unresolved.map((u) => (
              <li key={u}>{u}</li>
            ))}
          </ul>
        </div>
      )}
      {r.matches_preset && <p className="text-small leading-5 text-ink-2">This matches a ready-made scenario and will open at once.</p>}
    </div>
  )
}

/** One assumption: its control, its current value, and where that value came from. */
function FieldRow({
  f,
  current,
  onChange,
  onReset,
}: {
  f: AssumptionFieldDTO
  current: AssumptionDTO | null
  onChange: (v: FieldValue) => void
  onReset: () => void
}) {
  const hintId = useId()
  const value = current?.value ?? null
  const empty = isEmptyValue(value)
  return (
    <div className="flex min-w-0 flex-col gap-2 rounded-sheet border border-line bg-panel p-4" data-field={f.field}>
      {f.kind === 'multi_choice' ? (
        <fieldset className="flex flex-col gap-1.5">
          <legend className="text-small font-semibold text-ink">{f.label}</legend>
          <p id={hintId} className="text-caption leading-caption text-ink-3">
            {f.help}
          </p>
          <div className="flex flex-col">
            {(f.options ?? []).map((o) => {
              const picked = Array.isArray(value) && value.includes(o.value)
              return (
                <label key={o.value} className="flex min-h-11 cursor-pointer items-center gap-3 text-body text-ink">
                  <input
                    type="checkbox"
                    className="size-5 accent-[var(--color-ink)]"
                    checked={picked}
                    aria-describedby={hintId}
                    onChange={() => {
                      const cur = Array.isArray(value) ? value : []
                      onChange(picked ? cur.filter((x) => x !== o.value) : [...cur, o.value])
                    }}
                  />
                  <span>
                    {o.label}
                    {o.hint && <span className="block text-caption text-ink-3">{o.hint}</span>}
                  </span>
                </label>
              )
            })}
          </div>
        </fieldset>
      ) : (
        <Field label={f.label} hint={f.help}>
          {(p) =>
            f.kind === 'choice' ? (
              <Select
                {...p}
                value={typeof value === 'string' ? value : ''}
                placeholder="Not set"
                onChange={(v) => onChange(v)}
                options={(f.options ?? []).map((o) => ({ value: o.value, label: o.hint ? `${o.label} · ${o.hint}` : o.label }))}
              />
            ) : f.kind === 'date' ? (
              <TextInput
                {...p}
                type="date"
                value={typeof value === 'string' ? value.slice(0, 10) : ''}
                onChange={(e) => onChange(e.target.value)}
              />
            ) : (
              <div className="flex items-center gap-2">
                <TextInput
                  {...p}
                  type="number"
                  inputMode="decimal"
                  step="any"
                  min={f.min ?? undefined}
                  max={f.max ?? undefined}
                  value={typeof value === 'number' ? value : ''}
                  onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
                />
                {f.unit && <span className="shrink-0 text-small text-ink-2">{f.unit}</span>}
              </div>
            )
          }
        </Field>
      )}
      <div className="flex flex-col gap-1.5 border-t border-line pt-2" aria-live="polite">
        {current && !empty ? (
          <>
            <span className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
              <span className="text-small text-ink-3">Now</span>
              <span className="text-body font-semibold text-ink">{current.display}</span>
              <BasisTag basis={current.basis} />
            </span>
            <AssumptionBasisNote a={current} />
          </>
        ) : (
          <span className="text-small text-ink-2">Not set{f.default === null ? '. This one has to be given.' : '.'}</span>
        )}
        {current?.basis === 'you' && (
          <div>
            <button
              type="button"
              onClick={onReset}
              className="inline-flex min-h-11 items-center text-small font-semibold text-ink underline underline-offset-4"
            >
              {f.default ? `Reset to ${f.default.display}` : 'Clear'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
