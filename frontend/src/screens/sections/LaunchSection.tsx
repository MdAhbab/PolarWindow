import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../lib/api/client'
import type { MissionDetail } from '../../lib/api/adapters'
import type { LaunchCalendarDTO, LaunchWeatherDTO, LifecycleMetaDTO, OpportunityDTO, RuleRowDTO } from '../../lib/api/lifecycle'
import { useHistory, useLifecycleWrite, useSection } from '../../lib/api/lifecycleQueries'
import { dateTimeWords, dateWords } from '../../lib/format'
import { ageWords, hostWords, quantityText } from '../../lib/lifecycle/quantity'
import { NumberRow, QuantityTile } from '../../components/lifecycle/QuantityTile'
import { Answer, ChartPanel, HowSure, Legend, Rows, SectionLayout, SectionStates, SourcesRow, StatePanel } from '../../components/lifecycle/Section'
import { LaunchCalendar, LaunchTable, opportunityName } from '../../components/lifecycle/LaunchCalendar'
import { WeatherRuleTable, rulesSummary } from '../../components/lifecycle/WeatherRules'
import { Field, FormSheet, HistoryList, TextArea, TextInput, isHttpUrl } from '../../components/lifecycle/Forms'
import { Button, Disclosure } from '../../components/ui'
import { Icon } from '../../components/Icon'
import { useCanWrite } from './ReadySection'

const TERMS = ['launchTime', 'flightTime', 'sunAtLanding', 'sunlightAfterLanding']

/**
 * Launch (design-lifecycle.md §4): when and from where it can launch, and
 * for the opportunity chosen, the landing it gives and the weather rules.
 */
export function LaunchSection({ mission: m }: { mission: MissionDetail }) {
  const [params, setParams] = useSearchParams()
  const from = params.get('from') ?? undefined
  const to = params.get('to') ?? undefined
  const view = useSection<LaunchCalendarDTO>('launch', m.id, (signal) => api.launch(m.id, { from, to }, signal), [from ?? null, to ?? null])
  return (
    <SectionLayout question="When and from where can it launch?">
      <SectionStates view={view} terms={TERMS}>
        {({ data, meta }) =>
          data.opportunities.length ? (
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
                <DatesRow from={from} to={to} onApply={(f, t) => setParams({ ...(f ? { from: f } : {}), ...(t ? { to: t } : {}) })} />
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

function LaunchAnswer({ cal, meta, missionId }: { cal: LaunchCalendarDTO; meta: LifecycleMetaDTO; missionId: string }) {
  const [params, setParams] = useSearchParams()
  const [chosen, setChosen] = useState<string | null>(null)
  const o = cal.opportunities.find((x) => x.id === chosen) ?? firstChoice(cal)
  const sorted = [...cal.opportunities].sort((a, b) => (a.t0.value ?? 0) - (b.t0.value ?? 0))
  const first = sorted[0]
  const last = sorted[sorted.length - 1]
  const pads = [...new Set(cal.opportunities.map((x) => x.pad_name))]
  const weather = useSection<LaunchWeatherDTO>(
    'launch-weather',
    missionId,
    (signal) => api.launchWeather(missionId, o.id, signal),
    [o.id],
    o.weather !== 'none',
  )
  const wx = weather.status === 'answer' ? weather.section : null

  return (
    <>
      <Answer meta={meta}>
        {cal.opportunities.length} launch opportunit{cal.opportunities.length === 1 ? 'y' : 'ies'} from {pads.join(' and ')} between{' '}
        {dateWords((first.t0.value ?? 0) * 1000)} and {dateWords((last.t0.value ?? 0) * 1000)}.
        {cal.published_t0?.value != null && <> The mission’s published launch time is {quantityText(cal.published_t0)}.</>}
      </Answer>
      <div className="-mt-2 flex flex-col gap-3">
        <p className="text-small text-ink-2" aria-live="polite">
          Numbers for the opportunity on <span className="font-semibold text-ink">{opportunityName(o)}</span>
        </p>
        <NumberRow>
          <QuantityTile term="launchTime" q={o.t0} />
          <QuantityTile term="flightTime" q={o.transfer.flight_days} note={o.transfer.type === 'phasing_loops' ? 'with loops around Earth first' : 'direct to the Moon'} />
          <QuantityTile
            term="sunAtLanding"
            q={o.landing.sun_elevation_deg}
            tone="sun"
            icon="sun"
            note={`The landing rule asks for ${quantityText(cal.landing_rule.sun_elevation_min_deg)} to ${quantityText(cal.landing_rule.sun_elevation_max_deg)}`}
          />
          <QuantityTile term="sunlightAfterLanding" q={o.landing.sunlight_after_h} tone="sun" note={o.landing.earth_up ? 'Earth in view at landing' : 'Earth not in view at landing'} />
        </NumberRow>
      </div>
      <ChartPanel
        title="Launch opportunities by day (times in UTC)"
        guide="launch-calendar"
        chart={<LaunchCalendar opportunities={cal.opportunities} selected={o.id} onSelect={setChosen} />}
        legend={
          <>
            <Legend
              items={[
                { swatch: <span className="h-4 w-8 rounded-control border border-line-strong bg-panel" />, label: 'An opportunity: choose one to see its numbers' },
                { swatch: <span className="h-4 w-8 rounded-control bg-ink" />, label: 'Chosen' },
                { swatch: <span className="hatch-uncertain h-3 w-5" />, label: 'How far the time could be off' },
              ]}
            />
            <p className="text-caption leading-caption text-ink-3">
              Each opportunity is worked back from a landing that meets the landing rule. {cal.landing_rule.note}
            </p>
          </>
        }
        table={<LaunchTable opportunities={cal.opportunities} />}
      />
      <Rows>
        <Disclosure
          title="Weather rules for this opportunity"
          meta={
            o.weather === 'none'
              ? 'no weather for this date'
              : wx
                ? `${rulesSummary(wx.data.rules)}${o.weather === 'climatology' ? ', past years only' : ''}`
                : weather.status === 'error'
                  ? 'not available'
                  : 'loading'
          }
        >
          {o.weather === 'none' ? (
            <p className="text-body text-ink-2">This opportunity is too far ahead for a forecast, and no history is held for its pad.</p>
          ) : wx ? (
            <WeatherBody wx={wx.data} meta={wx.meta} />
          ) : weather.status === 'error' ? (
            <p className="text-body text-ink-2">The weather could not be loaded: {(weather.error as Error).message}</p>
          ) : weather.status === 'working' ? (
            <p className="text-body text-ink-2">{weather.job.message}</p>
          ) : (
            <p className="text-small text-ink-3">Loading the weather…</p>
          )}
        </Disclosure>
        <OfficialRow wx={wx?.data ?? null} missionId={missionId} />
        <LimitsRow rules={wx?.data.rules ?? []} vehicleId={cal.vehicle_id ?? o.vehicle_id} />
        <Disclosure title="Other launches from this range that day" meta={wx ? String(wx.data.range_conflicts.length) : undefined}>
          {wx?.data.range_conflicts.length ? (
            <ul className="flex flex-col gap-1.5">
              {wx.data.range_conflicts.map((c) => (
                <li key={c.name + c.t0} className="text-body text-ink">
                  {c.name} <span className="text-ink-2">· {dateTimeWords(Date.parse(c.t0))} · {c.pad}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-body text-ink-2">{wx ? 'None listed.' : 'Shown with the weather for this opportunity.'}</p>
          )}
        </Disclosure>
        {wx && <SpaceWeatherRow wx={wx.data} meta={wx.meta} />}
        <DatesRow
          from={params.get('from') ?? undefined}
          to={params.get('to') ?? undefined}
          onApply={(f, t) => setParams({ ...(f ? { from: f } : {}), ...(t ? { to: t } : {}) })}
        />
        <HowSure meta={meta} />
        <SourcesRow meta={meta} />
      </Rows>
    </>
  )
}

function WeatherBody({ wx, meta }: { wx: LaunchWeatherDTO; meta: LifecycleMetaDTO }) {
  const fetched = meta.sources.map((s) => (s.fetched_at ? Date.parse(s.fetched_at) : NaN)).filter((n) => !Number.isNaN(n))
  const oldest = fetched.length ? Math.min(...fetched) : null
  return (
    <>
      <p className="text-small leading-5 text-ink-2">
        For a launch at {dateTimeWords(Date.parse(wx.t0))}, {Math.round(wx.lead_time_h)} hours ahead of the forecasts.
        {oldest !== null && ` The oldest forecast here was fetched ${ageWords(oldest)}.`} Each system is shown on its own;
        nothing is added up, and the launch team decides.
      </p>
      <WeatherRuleTable rules={wx.rules} />
    </>
  )
}

function SpaceWeatherRow({ wx, meta }: { wx: LaunchWeatherDTO; meta: LifecycleMetaDTO }) {
  const sw = wx.space_weather_now
  const swpc = meta.sources.find((s) => /SWPC|space weather/i.test(s.name))
  return (
    <Disclosure title="Space weather now" meta={`Kp ${quantityText(sw.kp)}${sw.alerts.length ? `, ${sw.alerts.length} alerts` : ''}`}>
      <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-body sm:grid-cols-[max-content_1fr]">
        <dt className="text-ink-3">Geomagnetic activity (Kp)</dt>
        <dd className="text-ink">{quantityText(sw.kp)}</dd>
        <dt className="text-ink-3">Protons above 10 MeV</dt>
        <dd className="text-ink">{quantityText(sw.proton_10mev_pfu)}</dd>
        <dt className="text-ink-3">X-ray flares</dt>
        <dd className="text-ink">{sw.xray_class ?? 'Not reported'}</dd>
        <dt className="text-ink-3">Alerts</dt>
        <dd className="text-ink">{sw.alerts.length ? sw.alerts.join('; ') : 'None'}</dd>
      </dl>
      {swpc?.fetched_at && <p className="text-caption text-ink-3">As of {ageWords(Date.parse(swpc.fetched_at))}, from NOAA’s Space Weather Prediction Center.</p>}
    </Disclosure>
  )
}

/**
 * The official launch forecast, entered by the project manager with its PDF
 * (ADR-14: attributed, never scraped). Quoted as issued; nothing is added.
 */
function OfficialRow({ wx, missionId }: { wx: LaunchWeatherDTO | null; missionId: string }) {
  const canWrite = useCanWrite()
  const [open, setOpen] = useState(false)
  const official = wx?.official ?? null
  const history = useHistory('forecast', open ? missionId : null)
  const write = useLifecycleWrite((b: { probability_pct: number; concerns: string[]; pdf_url: string }) => api.officialForecast(missionId, b))
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
      {canWrite && (
        <div>
          <Button onClick={() => setOpen(true)} >
            <Icon name="pencil" size={15} />
            {official ? 'Enter a newer forecast' : 'Enter the official forecast'}
          </Button>
        </div>
      )}
      <FormSheet
        open={open}
        onClose={() => setOpen(false)}
        title="Official launch forecast"
        intro="Copy the numbers as issued, and link the PDF. Nothing here is worked out by POLAR WINDOW."
        saving={write.isPending}
        error={write.error}
        history={<HistoryList entries={history.data} pending={history.isPending} error={history.error} />}
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

/**
 * The team's own weather limits, for vehicles whose limits are not published
 * (ADR-14): each is shown as "a limit the team entered", with who and when.
 */
function LimitsRow({ rules, vehicleId }: { rules: RuleRowDTO[]; vehicleId: string | undefined }) {
  const canWrite = useCanWrite()
  const [open, setOpen] = useState(false)
  const history = useHistory('limits', open && vehicleId ? vehicleId : null)
  const editable = rules.filter((r) => r.class !== 'observation' && r.limit.value !== null)
  const [values, setValues] = useState<Record<string, string>>({})
  const write = useLifecycleWrite((b: Parameters<typeof api.vehicleLimits>[1]) => api.vehicleLimits(vehicleId as string, b))
  const entered = rules.filter((r) => r.limit.provenance === 'entered').length
  return (
    <Disclosure title="Team weather limits" meta={rules.length ? `${entered} entered by the team, ${rules.length - entered} published` : undefined}>
      {rules.length ? (
        <ul className="flex flex-col divide-y divide-line border-y border-line">
          {rules.map((r) => (
            <li key={r.id} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2.5">
              <span className="text-body text-ink">{r.text}</span>
              <span className="text-small text-ink-2">
                {quantityText(r.limit)} ·{' '}
                {r.limit.provenance === 'entered' ? `entered by ${r.limit.source ?? 'the team'}` : r.limit.provenance === 'published' ? 'published' : r.limit.provenance}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-body text-ink-2">The limits appear with the weather for this opportunity.</p>
      )}
      {canWrite && vehicleId && editable.length > 0 && (
        <div>
          <Button onClick={() => setOpen(true)}>
            <Icon name="pencil" size={15} />
            Enter the team’s limits
          </Button>
        </div>
      )}
      <FormSheet
        open={open}
        onClose={() => setOpen(false)}
        title="Team weather limits"
        intro="For a vehicle whose limits are not published. Leave a field empty to keep the limit as it is."
        saving={write.isPending}
        error={write.error}
        history={<HistoryList entries={history.data} pending={history.isPending} error={history.error} />}
        onSave={async () => {
          const limits = editable
            .filter((r) => values[r.id] !== undefined && values[r.id] !== '')
            .map((r) => ({ rule_id: r.id, value: Number(values[r.id]), unit: r.limit.unit, note: null }))
          if (!limits.length || limits.some((l) => !Number.isFinite(l.value))) return false
          try {
            await write.mutateAsync({ limits })
            return true
          } catch {
            return false
          }
        }}
      >
        {editable.map((r) => (
          <Field key={r.id} label={r.text} hint={`Now ${quantityText(r.limit)}.`}>
            {(p) => (
              <TextInput
                {...p}
                inputMode="decimal"
                value={values[r.id] ?? ''}
                onChange={(e) => setValues({ ...values, [r.id]: e.target.value })}
              />
            )}
          </Field>
        ))}
      </FormSheet>
    </Disclosure>
  )
}

function DatesRow({ from, to, onApply }: { from?: string; to?: string; onApply: (from?: string, to?: string) => void }) {
  const [f, setF] = useState(from ?? '')
  const [t, setT] = useState(to ?? '')
  return (
    <Disclosure title="Change the dates" meta={from || to ? `${from ?? '…'} to ${to ?? '…'}` : 'the dates the service chose'}>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault()
          onApply(f || undefined, t || undefined)
        }}
      >
        <Field label="From (UTC)">{(p) => <TextInput {...p} type="date" value={f} onChange={(e) => setF(e.target.value)} className="w-44" />}</Field>
        <Field label="To (UTC)">{(p) => <TextInput {...p} type="date" value={t} onChange={(e) => setT(e.target.value)} className="w-44" />}</Field>
        <Button type="submit">Show these dates</Button>
      </form>
    </Disclosure>
  )
}
