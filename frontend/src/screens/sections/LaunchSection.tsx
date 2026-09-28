import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../../lib/api/client'
import type { MissionDetail } from '../../lib/api/adapters'
import type {
  AuditEntryDTO,
  EnteredLimitDTO,
  LaunchCalendarDTO,
  LaunchWeatherDTO,
  LifecycleMetaDTO,
  OfficialForecastDTO,
  OpportunityDTO,
  QuantityDTO,
  RuleRowDTO,
} from '../../lib/api/lifecycle'
import { useEnteredLimits, useHistory, useLifecycleWrite, useSection, useSectionStatus } from '../../lib/api/lifecycleQueries'
import { dateTimeWords, dateWords } from '../../lib/format'
import { ageWords, formatValue, hostWords, quantityText } from '../../lib/lifecycle/quantity'
import { NumberRow, QuantityTile } from '../../components/lifecycle/QuantityTile'
import { Answer, ChartPanel, HowSure, Legend, Rows, SectionLayout, SectionStates, SourcesRow, StatePanel } from '../../components/lifecycle/Section'
import { LaunchCalendar, LaunchTable, opportunityName } from '../../components/lifecycle/LaunchCalendar'
import { WeatherRuleTable, rulesSummary } from '../../components/lifecycle/WeatherRules'
import { Field, FormSheet, HistoryList, Select, TextArea, TextInput, isHttpUrl } from '../../components/lifecycle/Forms'
import { Button, Disclosure } from '../../components/ui'
import { Icon } from '../../components/Icon'
import { UncertaintyNote } from '../../components/States'
import { SpaceWeatherRow } from '../../components/lifecycle/SpaceWeather'
import { useCanWrite } from './ReadySection'

const TERMS = ['launchTime', 'flightTime', 'sunAtLanding', 'sunlightAfterLanding']
const DAY_MS = 86_400_000
/** The longest span the service searches at once (422 beyond it). */
const MAX_DAYS = 180

/**
 * Launch (design-lifecycle.md §4): when and from where it can launch, and
 * for the opportunity chosen, the landing it gives and the weather rules.
 */
export function LaunchSection({ mission: m }: { mission: MissionDetail }) {
  const [params, setParams] = useSearchParams()
  const from = params.get('from') ?? undefined
  const to = params.get('to') ?? undefined
  const view = useSection<LaunchCalendarDTO>('launch', m.id, (signal) => api.launch(m.id, { from, to }, signal), [from ?? null, to ?? null])
  const status = useSectionStatus(m.id, 'launch')
  return (
    <SectionLayout question="When and from where can it launch?">
      <SectionStates view={view} terms={TERMS} status={status}>
        {({ data, meta }) =>
          data.none_reason ? (
            <>
              <StatePanel
                icon="ring"
                title="No launch to show yet"
                detail={data.none_reason}
                stillWorks="Landing, Contact and the other steps do not depend on the launch and work as usual."
              />
              <Rows>
                <SourcesRow meta={meta} />
              </Rows>
            </>
          ) : data.opportunities.length ? (
            <LaunchAnswer cal={data} meta={meta} missionId={m.id} />
          ) : (
            <>
              <StatePanel
                icon="ring"
                title="No launch opportunity in these dates"
                detail={`None of the days searched meets the landing rule: ${data.landing_rule.note}`}
                stillWorks="Try other dates below. The other steps are unaffected."
              />
              <Rows>
                <DatesRow
                  from={from}
                  to={to}
                  datesNote={data.dates_note}
                  onApply={(f, t) => setParams({ ...(f ? { from: f } : {}), ...(t ? { to: t } : {}) })}
                />
                <SourcesRow meta={meta} />
              </Rows>
            </>
          )
        }
      </SectionStates>
    </SectionLayout>
  )
}

/** The opportunity a page opens on: the one nearest the published launch time, else the first. */
function firstChoice(cal: LaunchCalendarDTO): OpportunityDTO {
  const sorted = [...cal.opportunities].sort((a, b) => (a.t0.value ?? 0) - (b.t0.value ?? 0))
  const pub = cal.published_t0?.value
  if (pub == null) return sorted[0]
  return sorted.reduce((best, o) => (Math.abs((o.t0.value ?? 0) - pub) < Math.abs((best.t0.value ?? 0) - pub) ? o : best), sorted[0])
}

/** A flown mission's calendar is its one launch, worked out again or as published. */
function isFlown(cal: LaunchCalendarDTO): boolean {
  return cal.opportunities.length > 0 && cal.opportunities.every((x) => x.basis !== 'designed')
}

/** The landing rule's Sun-height band in words, or that none is entered yet. */
function sunBandWords(rule: LaunchCalendarDTO['landing_rule']): string {
  const lo = rule.sun_elevation_min_deg
  const hi = rule.sun_elevation_max_deg
  if (lo.value !== null && hi.value !== null) return `The landing rule asks for ${quantityText(lo)} to ${quantityText(hi)}`
  if (lo.value !== null) return `The landing rule asks for at least ${quantityText(lo)}`
  if (hi.value !== null) return `The landing rule asks for at most ${quantityText(hi)}`
  return 'No Sun-height band entered; any landing with the Sun up and rising counts'
}

function LaunchAnswer({ cal, meta, missionId }: { cal: LaunchCalendarDTO; meta: LifecycleMetaDTO; missionId: string }) {
  const [params, setParams] = useSearchParams()
  const [chosen, setChosen] = useState<string | null>(null)
  const o = cal.opportunities.find((x) => x.id === chosen) ?? firstChoice(cal)
  const flown = isFlown(cal)
  const sorted = [...cal.opportunities].sort((a, b) => (a.t0.value ?? 0) - (b.t0.value ?? 0))
  const now = Date.now()
  const next = sorted.find((x) => (x.t0.value ?? 0) * 1000 > now)
  const pads = [...new Set(cal.opportunities.map((x) => x.pad_name))]
  const fromMs = cal.start ? Date.parse(cal.start) : (sorted[0].t0.value ?? 0) * 1000
  const toMs = cal.end ? Date.parse(cal.end) : (sorted[sorted.length - 1].t0.value ?? 0) * 1000
  // The weather endpoint answers at once for any opportunity, a flown one too:
  // the rules and the team's limits stand even where no forecast reaches.
  const weather = useSection<LaunchWeatherDTO>('launch-weather', missionId, (signal) => api.launchWeather(missionId, o.id, signal), [o.id])
  const wx = weather.status === 'answer' ? weather.section : null

  return (
    <>
      <Answer meta={meta}>
        {flown ? (
          <>
            It launched on {quantityText(o.t0)} from {o.pad_name},{' '}
            {o.basis === 'reconstructed' ? 'as worked out again from NASA’s reconstruction of the flight' : 'as published'}.
            {o.basis === 'reconstructed' && cal.published_t0?.value != null && (
              <> The published liftoff is {quantityText(cal.published_t0)}.</>
            )}
          </>
        ) : (
          <>
            {cal.opportunities.length} launch opportunit{cal.opportunities.length === 1 ? 'y' : 'ies'} from {pads.join(' and ')} between{' '}
            {dateWords(fromMs)} and {dateWords(toMs)}.
            {next && <> The next is {dateTimeWords((next.t0.value ?? 0) * 1000)} from {next.pad_name}.</>}
            {cal.published_t0?.value != null && <> The mission’s published launch time is {quantityText(cal.published_t0)}.</>}
          </>
        )}
      </Answer>
      <div className="-mt-2 flex flex-col gap-3">
        <p className="text-small text-ink-2" aria-live="polite">
          Numbers for the {flown ? 'launch' : 'opportunity'} on <span className="font-semibold text-ink">{opportunityName(o)}</span>
        </p>
        <NumberRow>
          <QuantityTile term="launchTime" q={o.t0} />
          <QuantityTile term="flightTime" q={o.transfer.flight_days} note={o.transfer.type === 'phasing_loops' ? 'With loops around Earth first' : 'Direct to the Moon'} />
          <QuantityTile term="sunAtLanding" q={o.landing.sun_elevation_deg} tone="sun" icon="sun" note={sunBandWords(cal.landing_rule)} />
          <QuantityTile term="sunlightAfterLanding" q={o.landing.sunlight_after_h} tone="sun" note={o.landing.earth_up ? 'Earth in view at landing' : 'Earth not in view at landing'} />
        </NumberRow>
        {o.note && <UncertaintyNote>{o.note}</UncertaintyNote>}
      </div>
      <ChartPanel
        title={flown ? 'The launch (time in UTC)' : 'Launch opportunities by day (times in UTC)'}
        guide="launch-calendar"
        chart={<LaunchCalendar opportunities={cal.opportunities} selected={o.id} onSelect={setChosen} />}
        legend={
          <>
            <Legend
              items={[
                ...(flown
                  ? []
                  : [
                      { swatch: <span className="h-4 w-8 rounded-control border border-line-strong bg-panel" />, label: 'An opportunity: choose one to see its numbers' },
                      { swatch: <span className="h-4 w-8 rounded-control bg-ink" />, label: 'Chosen' },
                    ]),
                { swatch: <span className="hatch-uncertain h-3 w-5" />, label: 'How far the time could be off' },
              ]}
            />
            <p className="text-caption leading-caption text-ink-3">
              {flown ? 'The landing rule it is checked against: ' : 'Each opportunity is worked back from a landing that meets the landing rule. '}
              {cal.landing_rule.note}
            </p>
          </>
        }
        table={<LaunchTable opportunities={cal.opportunities} />}
      />
      <Rows>
        <FlightRow o={o} flown={flown} />
        <Disclosure
          title={flown ? 'Weather rules for this launch' : 'Weather rules for this opportunity'}
          meta={
            wx
              ? `${rulesSummary(wx.data.rules)}${o.weather === 'none' ? '; no forecast for this date' : o.weather === 'climatology' ? ', past years only' : ''}`
              : weather.status === 'error'
                ? 'not available'
                : 'loading'
          }
        >
          {wx ? (
            <WeatherBody wx={wx.data} meta={wx.meta} note={o.weather_note} />
          ) : weather.status === 'error' ? (
            <p className="text-body text-ink-2">The weather could not be loaded: {(weather.error as Error).message}</p>
          ) : weather.status === 'working' ? (
            <p className="text-body text-ink-2">{weather.job.message}</p>
          ) : (
            <p className="text-small text-ink-3">Loading the weather…</p>
          )}
        </Disclosure>
        <OfficialRow wx={wx?.data ?? null} missionId={missionId} />
        <LimitsRow rules={wx?.data.rules ?? []} vehicleId={wx?.data.vehicle_id ?? cal.vehicle_id ?? o.vehicle_id} />
        <Disclosure title="Other launches from this range that day" meta={wx?.data.range_conflicts.length ? String(wx.data.range_conflicts.length) : undefined}>
          {wx?.data.range_conflicts.length ? (
            <ul className="flex flex-col gap-1.5">
              {wx.data.range_conflicts.map((c) => (
                <li key={c.name + c.t0} className="text-body text-ink">
                  {c.name} <span className="text-ink-2">· {dateTimeWords(Date.parse(c.t0))} · {c.pad}</span>
                </li>
              ))}
            </ul>
          ) : (
            !wx && <p className="text-body text-ink-2">Shown with the weather for this opportunity.</p>
          )}
          {wx?.data.range_note && <p className="text-small leading-5 text-ink-2">{wx.data.range_note}</p>}
        </Disclosure>
        <SpaceWeatherRow />
        {/* A flown mission's launch is the one it flew: there are no dates to change. */}
        {!flown && (
          <DatesRow
            from={params.get('from') ?? undefined}
            to={params.get('to') ?? undefined}
            datesNote={cal.dates_note}
            onApply={(f, t) => setParams({ ...(f ? { from: f } : {}), ...(t ? { to: t } : {}) })}
          />
        )}
        <HowSure meta={meta} />
        <SourcesRow meta={meta} />
      </Rows>
    </>
  )
}

const BASIS_WORDS: Record<OpportunityDTO['basis'], string> = {
  reconstructed: 'worked out again from NASA’s reconstruction',
  designed: 'designed here from the pad and the landing',
  published: 'as published',
}

/** A number, or why there is none; an assumed one also says what it assumes. */
function QuantityLine({ q }: { q: QuantityDTO }) {
  if (q.value === null && (q.lo === null || q.hi === null)) return <>{q.missing_reason ?? 'Not available'}</>
  return (
    <>
      {quantityText(q)}
      {q.provenance === 'assumed' && q.source && <span className="block text-small text-ink-2">Assumed: {q.source}</span>}
    </>
  )
}

/** How this launch reaches the Moon: the climb, the coast, leaving Earth, the flight and the landing. */
function FlightRow({ o, flown }: { o: OpportunityDTO; flown: boolean }) {
  const land = o.landing.time
  const stretch = o.basis === 'designed' && land.lo !== null && land.hi !== null
  const landing = { ...land, lo: null, hi: null }
  return (
    <Disclosure title={flown ? 'The flight as launched' : 'The flight for this opportunity'} meta={BASIS_WORDS[o.basis]}>
      <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-body sm:grid-cols-[max-content_1fr]">
        <dt className="text-ink-3">Launch time</dt>
        <dd className="text-ink">{quantityText(o.t0)}</dd>
        <dt className="text-ink-3">Direction of the climb (compass heading)</dt>
        <dd className="text-ink">
          <QuantityLine q={o.azimuth_deg} />
        </dd>
        <dt className="text-ink-3">Coasting in Earth orbit before leaving for the Moon</dt>
        <dd className="text-ink">
          <QuantityLine q={o.coast_min} />
        </dd>
        <dt className="text-ink-3">Speed added to leave Earth for the Moon</dt>
        <dd className="text-ink">
          <QuantityLine q={o.dv_tli_m_s} />
        </dd>
        <dt className="text-ink-3">Flight time to the Moon</dt>
        <dd className="text-ink">
          <QuantityLine q={o.transfer.flight_days} />
        </dd>
        <dt className="text-ink-3">Time in orbit around the Moon before landing</dt>
        <dd className="text-ink">
          <QuantityLine q={o.transfer.orbit_wait_days} />
        </dd>
        <dt className="text-ink-3">Landing</dt>
        <dd className="text-ink">
          {land.value === null ? (land.missing_reason ?? 'Not available') : quantityText(landing)}
          {land.provenance === 'published' && <span className="text-ink-2"> (published)</span>}
          {stretch && (
            <span className="block text-small text-ink-2">
              The landing rule allows a landing from {dateTimeWords((land.lo as number) * 1000)} to {dateTimeWords((land.hi as number) * 1000)}.
            </span>
          )}
        </dd>
        <dt className="text-ink-3">Earth in view at landing</dt>
        <dd className="text-ink">{o.landing.earth_up ? 'Yes' : 'No'}</dd>
      </dl>
    </Disclosure>
  )
}

/** "380 hours from now", "16 days from now", or that the launch is past. */
function leadWords(h: number): string {
  if (h < 0) return 'in the past'
  if (h < 48) return `${Math.round(h)} hours from now`
  return `${formatValue(h / 24)} days from now`
}

function WeatherBody({ wx, meta, note }: { wx: LaunchWeatherDTO; meta: LifecycleMetaDTO; note: string }) {
  const fetched = meta.sources.map((s) => (s.fetched_at ? Date.parse(s.fetched_at) : NaN)).filter((n) => !Number.isNaN(n))
  const oldest = fetched.length ? Math.min(...fetched) : null
  return (
    <>
      {note && <p className="text-body leading-6 text-ink">{note}</p>}
      <p className="text-small leading-5 text-ink-2">
        For a launch at {dateTimeWords(Date.parse(wx.t0))}, {leadWords(wx.lead_time_h)}. {wx.note}
        {oldest !== null && wx.lead_time_h >= 0 && ` The oldest forecast here was fetched ${ageWords(oldest)}.`} Nothing is
        added up; the launch team decides.
      </p>
      <WeatherRuleTable rules={wx.rules} />
    </>
  )
}

/** The later-entered of two forecasts (the one a save answered with, and the one the weather answer carries). */
export function newestForecast(a: OfficialForecastDTO | null, b: OfficialForecastDTO | null): OfficialForecastDTO | null {
  if (!a || !b) return a ?? b
  return Date.parse(b.entered_at) > Date.parse(a.entered_at) ? b : a
}

/**
 * The same entered forecast, as two answers carry it: a save answers with the
 * time it was sent, the weather answer with the time it was stored, a moment apart.
 */
export function sameForecast(a: OfficialForecastDTO, b: OfficialForecastDTO): boolean {
  return (
    a.probability_pct === b.probability_pct &&
    a.pdf_url === b.pdf_url &&
    a.entered_by === b.entered_by &&
    Math.abs(Date.parse(a.entered_at) - Date.parse(b.entered_at)) < 5_000
  )
}

/** The forecast to show: the newest of those at hand, leaving out any taken back. */
export function shownForecast(
  candidates: (OfficialForecastDTO | null | undefined)[],
  takenBack: OfficialForecastDTO[],
): OfficialForecastDTO | null {
  return candidates.reduce<OfficialForecastDTO | null>(
    (best, f) => (!f || takenBack.some((t) => sameForecast(t, f)) ? best : newestForecast(best, f)),
    null,
  )
}

/** A forecast's history entry in words: what was entered, or what was taken back. */
export function forecastChangeWords(e: AuditEntryDTO): string {
  const words = (f: unknown) => {
    const x = f as { probability_pct?: number; concerns?: string[] } | null
    return x && typeof x.probability_pct === 'number'
      ? `${x.probability_pct}%${x.concerns?.length ? ` (${x.concerns.join(', ').toLowerCase()})` : ''}`
      : 'none'
  }
  if (e.action === 'delete') return `Took back ${words(e.before)}; shown now: ${words(e.after)}`
  return `Entered ${words(e.after)}${e.before ? `; before it: ${words(e.before)}` : ''}`
}

/**
 * The official launch forecast, entered by the project manager with its PDF
 * (ADR-14: attributed, never scraped). Quoted as issued; nothing is added.
 * The one shown can be taken back; the one entered before it is shown again.
 */
function OfficialRow({ wx, missionId }: { wx: LaunchWeatherDTO | null; missionId: string }) {
  const canWrite = useCanWrite()
  const [open, setOpen] = useState(false)
  const [takeBackOpen, setTakeBackOpen] = useState<OfficialForecastDTO | null>(null)
  const [takenBack, setTakenBack] = useState<OfficialForecastDTO[]>([])
  const history = useHistory('forecast', open || takeBackOpen ? missionId : null)
  const write = useLifecycleWrite((b: { probability_pct: number; concerns: string[]; pdf_url: string }) => api.officialForecast(missionId, b))
  const takeBack = useLifecycleWrite(() => api.takeBackForecast(missionId))
  // A save answers with the forecast as stored, a take-back with the one now shown: each is shown at
  // once, until the weather answer carries the same or a newer one.
  const official = shownForecast([wx?.official, write.data, takeBack.data?.official], takenBack)
  const [pct, setPct] = useState('')
  const [concerns, setConcerns] = useState('')
  const [pdf, setPdf] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})
  return (
    <Disclosure title="Official launch forecast" meta={official ? `${official.probability_pct}%, entered by ${official.entered_by}` : 'not entered'}>
      {official ? (
        <>
          <p className="text-body leading-6 text-ink">
            {official.probability_pct}% chance the weather breaks a launch rule, in the official forecast
            {official.concerns.length ? `; main concerns: ${official.concerns.join(', ').toLowerCase()}` : ''}.
          </p>
          <p className="text-caption text-ink-3">
            Entered by {official.entered_by}, {dateTimeWords(Date.parse(official.entered_at))} ·{' '}
            <a href={official.pdf_url} target="_blank" rel="noreferrer">
              the forecast as issued ({hostWords(official.pdf_url)})
            </a>
          </p>
        </>
      ) : (
        <p className="text-body text-ink-2">
          The launch weather officer’s forecast is entered here by the team, with a link to the PDF as issued.
        </p>
      )}
      <p aria-live="polite" className="text-small text-ink-2 empty:hidden">
        {takenBack.length > 0 && takeBack.isSuccess
          ? official
            ? 'Taken back. The forecast entered before it is shown again.'
            : 'Taken back. No other forecast is entered.'
          : ''}
      </p>
      {canWrite && (
        <div className="flex flex-wrap gap-3">
          <Button onClick={() => setOpen(true)}>
            <Icon name="pencil" size={15} />
            {official ? 'Enter a newer forecast' : 'Enter the official forecast'}
          </Button>
          {official && <Button variant="ghost" onClick={() => setTakeBackOpen(official)}>Take back this forecast</Button>}
        </div>
      )}
      <FormSheet
        open={takeBackOpen !== null}
        onClose={() => setTakeBackOpen(null)}
        title="Take back the official forecast"
        intro={
          takeBackOpen && (
            <>
              This takes back the {takeBackOpen.probability_pct}% forecast entered by {takeBackOpen.entered_by},{' '}
              {dateTimeWords(Date.parse(takeBackOpen.entered_at))}. The one entered before it, if any, is shown again. The change
              is kept in the history.
            </>
          )
        }
        saveLabel="Take back"
        savingLabel="Taking back…"
        saving={takeBack.isPending}
        error={takeBack.error}
        history={<HistoryList entries={history.data} pending={history.isPending} error={history.error} describe={forecastChangeWords} />}
        onSave={async () => {
          const target = takeBackOpen
          if (!target) return false
          try {
            await takeBack.mutateAsync(undefined)
            write.reset()
            setTakenBack((t) => [...t, target])
            setTakeBackOpen(null)
            return true
          } catch {
            return false
          }
        }}
      >
        {null}
      </FormSheet>
      <FormSheet
        open={open}
        onClose={() => setOpen(false)}
        title="Official launch forecast"
        intro="Copy the numbers as issued, and link the PDF. Nothing here is worked out by POLAR WINDOW."
        saving={write.isPending}
        error={write.error}
        history={<HistoryList entries={history.data} pending={history.isPending} error={history.error} describe={forecastChangeWords} />}
        onSave={async () => {
          const e: Record<string, string> = {}
          const n = Number(pct)
          if (!pct || !Number.isFinite(n) || n < 0 || n > 100) e.pct = 'A whole percent from 0 to 100.'
          if (!isHttpUrl(pdf)) e.pdf = 'The web address of the forecast PDF.'
          setErrors(e)
          if (Object.keys(e).length) return false
          try {
            await write.mutateAsync({
              probability_pct: Math.round(n),
              concerns: concerns.split(/[,;\n]/).map((c) => c.trim()).filter(Boolean),
              pdf_url: pdf,
            })
            takeBack.reset()
            return true
          } catch {
            return false
          }
        }}
      >
        <Field label="Chance the weather breaks a launch rule (%)" hint="As issued: the forecast’s “probability of violating weather constraints”." error={errors.pct}>
          {(p) => <TextInput {...p} inputMode="numeric" value={pct} onChange={(e) => setPct(e.target.value)} />}
        </Field>
        <Field label="Main concerns" hint="As the forecast words them, separated by commas.">
          {(p) => <TextArea {...p} value={concerns} onChange={(e) => setConcerns(e.target.value)} />}
        </Field>
        <Field label="Link to the forecast PDF" error={errors.pdf}>
          {(p) => <TextInput {...p} type="url" inputMode="url" placeholder="https://" value={pdf} onChange={(e) => setPdf(e.target.value)} />}
        </Field>
      </FormSheet>
    </Disclosure>
  )
}

/** One rule's fields in the team limits form. */
export interface LimitDraft {
  value: string
  unit: string
  note: string
}

/** A rule's starting fields: the limit as entered (with its note), else empty in the rule's first unit. */
export function limitDraft(r: RuleRowDTO, entered: EnteredLimitDTO | undefined): LimitDraft {
  if (entered) return { value: String(entered.value), unit: entered.unit, note: entered.note ?? '' }
  return { value: '', unit: r.units[0] ?? '', note: '' }
}

/**
 * The list a save sends. The service replaces the vehicle's whole list, so a
 * limit entered for a rule not in this form (another range's rule) is sent
 * again as it stands, note and all. A field left empty is no limit.
 */
export function limitsToSend(
  editable: RuleRowDTO[],
  drafts: Record<string, LimitDraft>,
  entered: EnteredLimitDTO[],
): { limits: { rule_id: string; value: number; unit: string; note: string | null }[]; errors: Record<string, string> } {
  const errors: Record<string, string> = {}
  const limits = []
  for (const r of editable) {
    const d = drafts[r.id]
    const typed = d.value.trim()
    if (!typed) continue
    const n = Number(typed)
    const unit = d.unit.trim()
    if (!Number.isFinite(n) || n <= 0) errors[r.id] = 'A number above zero.'
    else if (!unit) errors[`${r.id}-unit`] = 'The unit the limit is given in.'
    else limits.push({ rule_id: r.id, value: n, unit, note: d.note.trim() || null })
  }
  const shown = new Set(editable.map((r) => r.id))
  for (const e of entered) if (!shown.has(e.rule_id)) limits.push({ rule_id: e.rule_id, value: e.value, unit: e.unit, note: e.note })
  return { limits, errors }
}

/**
 * The team's own weather limits, for rules whose limit the vehicle maker does
 * not publish (ADR-14): each is shown as "a limit the team entered", with who
 * and its note. The form starts from the limits as entered (read back with
 * their notes); the service replaces the vehicle's whole list on each save.
 */
function LimitsRow({ rules, vehicleId }: { rules: RuleRowDTO[]; vehicleId: string | null | undefined }) {
  const canWrite = useCanWrite()
  const [open, setOpen] = useState(false)
  const history = useHistory('limits', open && vehicleId ? vehicleId : null)
  const stored = useEnteredLimits(vehicleId, open)
  const editable = rules.filter((r) => r.limit.provenance !== 'published')
  const [edits, setEdits] = useState<Record<string, Partial<LimitDraft>>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})
  const write = useLifecycleWrite((b: Parameters<typeof api.vehicleLimits>[1]) => api.vehicleLimits(vehicleId as string, b))
  const entered = rules.filter((r) => r.limit.provenance === 'entered' && r.limit.value !== null).length
  const notPublished = editable.length - entered
  const drafts: Record<string, LimitDraft> = Object.fromEntries(
    editable.map((r) => [r.id, { ...limitDraft(r, stored.data?.limits.find((e) => e.rule_id === r.id)), ...edits[r.id] }]),
  )
  const edit = (id: string, part: Partial<LimitDraft>) => setEdits({ ...edits, [id]: { ...edits[id], ...part } })
  return (
    <Disclosure
      title="Team weather limits"
      meta={rules.length ? `${entered} entered by the team${notPublished ? `, ${notPublished} not published` : ''}` : undefined}
    >
      {rules.length ? (
        <ul className="flex flex-col divide-y divide-line border-y border-line">
          {rules.map((r) => (
            <li key={r.id} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2.5">
              <span className="text-body text-ink">{r.text}</span>
              <span className="text-small text-ink-2">
                {r.limit.value === null
                  ? (r.limit.missing_reason ?? 'No limit given')
                  : `${quantityText(r.limit)} · ${
                      r.limit.provenance === 'entered' ? `entered by ${r.limit.source ?? 'the team'}` : r.limit.provenance === 'published' ? 'published' : r.limit.provenance
                    }`}
              </span>
              {r.limit_note && <span className="basis-full text-small leading-5 text-ink-2">Team’s note: {r.limit_note}</span>}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-body text-ink-2">The limits appear with the weather for this opportunity.</p>
      )}
      {canWrite && vehicleId && editable.length > 0 && (
        <div>
          <Button
            onClick={() => {
              setEdits({})
              setErrors({})
              setOpen(true)
            }}
          >
            <Icon name="pencil" size={15} />
            Enter the team’s limits
          </Button>
        </div>
      )}
      <FormSheet
        open={open}
        onClose={() => setOpen(false)}
        title="Team weather limits"
        intro="For the rules whose limit the vehicle maker does not publish. Each starts from the limit as entered; empty a field to remove that limit. A note says where a limit comes from."
        saving={write.isPending}
        error={write.error}
        history={<HistoryList entries={history.data} pending={history.isPending} error={history.error} />}
        onSave={async () => {
          // Without the list as stored, a save could drop a limit entered elsewhere.
          if (!stored.data) return false
          const { limits, errors: e } = limitsToSend(editable, drafts, stored.data.limits)
          if (!limits.length && !stored.data.limits.length) e[editable[0].id] = 'Enter a limit, or close the form.'
          setErrors(e)
          if (Object.keys(e).length) return false
          try {
            await write.mutateAsync({ limits })
            setEdits({})
            return true
          } catch {
            return false
          }
        }}
      >
        {stored.isPending ? (
          <p className="text-small text-ink-3">Reading the limits already entered…</p>
        ) : stored.error instanceof ApiError && stored.error.kind === 'vehicle-not-found' ? (
          <p className="text-small leading-5 text-ink-2">
            This launch vehicle is not in the service’s list, so no limits can be entered for it. {stored.error.stillWorks}
          </p>
        ) : stored.error ? (
          <p className="text-small font-semibold text-alert">
            The limits already entered could not be read, so saving now could lose them: {(stored.error as Error).message}
          </p>
        ) : (
          editable.map((r) => {
            const d = drafts[r.id]
            const was = stored.data?.limits.find((e) => e.rule_id === r.id)
            const units = d.unit && !r.units.includes(d.unit) ? [d.unit, ...r.units] : r.units
            return (
              <fieldset key={r.id} className="flex flex-col gap-3 border-t border-line pt-4">
                <legend className="text-small font-semibold text-ink">{r.text}</legend>
                <div className="flex flex-wrap items-start gap-3">
                  <Field
                    label="Limit"
                    hint={was ? `Entered by ${was.entered_by}, ${dateTimeWords(Date.parse(was.entered_at))}.` : 'Not entered yet.'}
                    error={errors[r.id]}
                  >
                    {(p) => (
                      <TextInput {...p} inputMode="decimal" className="w-40" value={d.value} onChange={(e) => edit(r.id, { value: e.target.value })} />
                    )}
                  </Field>
                  <Field label="Unit" hint={units.length ? undefined : 'None is published for this rule.'} error={errors[`${r.id}-unit`]}>
                    {(p) =>
                      units.length ? (
                        <Select {...p} value={d.unit} options={units.map((u) => ({ value: u, label: u }))} onChange={(e) => edit(r.id, { unit: e.target.value })} />
                      ) : (
                        <TextInput {...p} className="w-28" value={d.unit} onChange={(e) => edit(r.id, { unit: e.target.value })} />
                      )
                    }
                  </Field>
                </div>
                <Field label="Note (optional)">
                  {(p) => <TextInput {...p} value={d.note} onChange={(e) => edit(r.id, { note: e.target.value })} />}
                </Field>
              </fieldset>
            )
          })
        )}
      </FormSheet>
    </Disclosure>
  )
}

function DatesRow({
  from,
  to,
  datesNote,
  onApply,
}: {
  from?: string
  to?: string
  datesNote: string | null
  onApply: (from?: string, to?: string) => void
}) {
  const [f, setF] = useState(from ?? '')
  const [t, setT] = useState(to ?? '')
  const [error, setError] = useState<string | undefined>()
  return (
    <Disclosure
      title="Change the dates"
      meta={from || to ? `${from ?? '…'} to ${to ?? '…'}` : (datesNote?.replace(/\.$/, '').toLowerCase() ?? 'the dates the service chose')}
    >
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault()
          const days = f && t ? (Date.parse(t) - Date.parse(f)) / DAY_MS : null
          if (days !== null && days <= 0) return setError('The end comes after the start.')
          if (days !== null && days > MAX_DAYS) return setError(`At most ${MAX_DAYS} days at once.`)
          setError(undefined)
          onApply(f || undefined, t || undefined)
        }}
      >
        <Field label="From (UTC)" error={error}>
          {(p) => <TextInput {...p} type="date" value={f} onChange={(e) => setF(e.target.value)} className="w-44" />}
        </Field>
        <Field label="To (UTC)" hint={`Up to ${MAX_DAYS} days.`}>
          {(p) => <TextInput {...p} type="date" value={t} onChange={(e) => setT(e.target.value)} className="w-44" />}
        </Field>
        <Button type="submit">Show these dates</Button>
      </form>
    </Disclosure>
  )
}
