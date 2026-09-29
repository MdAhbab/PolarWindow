import { useState } from 'react'
import { api } from '../../lib/api/client'
import type { MissionDetail } from '../../lib/api/adapters'
import type { CapsuleModelCheckDTO, LifecycleMetaDTO, QuantityDTO, ReturnDTO, SeaLimitsDTO, SectionStatusDTO, ZoneDTO } from '../../lib/api/lifecycle'
import { useHistory, useLifecycleWrite, useSection, useSectionStatus } from '../../lib/api/lifecycleQueries'
import { ageWords, formatValue, hostWords, quantityText } from '../../lib/lifecycle/quantity'
import { dateTimeWords } from '../../lib/format'
import { NumberRow, QuantityTile } from '../../components/lifecycle/QuantityTile'
import { Answer, ChartPanel, HowSure, Rows, SectionLayout, SectionStates, SourcesRow, StatePanel } from '../../components/lifecycle/Section'
import { LimitBars, LimitTable, overBy, type LimitRow } from '../../components/lifecycle/LimitBars'
import { STATE_WORDS } from '../../components/lifecycle/JourneyBar'
import { Field, FormSheet, HistoryList, TextInput } from '../../components/lifecycle/Forms'
import { Button, Disclosure } from '../../components/ui'
import { Icon } from '../../components/Icon'
import { useCanWrite } from './ReadySection'

const TERMS = ['boosterWaves', 'boosterWind', 'capsuleWaves', 'capsuleWind']

type Booster = NonNullable<ReturnDTO['booster']>

/** The booster landing zone's row, when its position is not published. */
const NO_ZONE: Record<Booster['landing'], string> = {
  droneship: 'droneship, position not published',
  land: 'position not published',
  expended: 'not recovered',
  unknown: 'not published yet',
}

/** "near 28.5°N 80.5°W, ±12 km"; the ± only when the zone's size is published. */
export function zoneWords(z: ZoneDTO): string {
  const ns = z.lat_deg < 0 ? 'S' : 'N'
  const ew = z.lon_deg < 0 ? 'W' : 'E'
  const at = `near ${Math.abs(z.lat_deg).toFixed(1)}°${ns} ${Math.abs(z.lon_deg).toFixed(1)}°${ew}`
  return z.pm_km != null ? `${at}, ±${formatValue(z.pm_km)} km` : at
}

const entered = (q: QuantityDTO | null | undefined): q is QuantityDTO => q?.value != null

/**
 * The sea at the booster's zone in one sentence: the forecast against the
 * team's limit, or why there is none (one reason when every measure shares it).
 */
export function seaWords(b: Booster): string {
  if (b.landing === 'expended') return ''
  const measures: [string, QuantityDTO | null, QuantityDTO][] = [
    ...(b.landing !== 'land' ? [['Waves there are', b.wave_height_m, b.limits.wave_height_m] as [string, QuantityDTO | null, QuantityDTO]] : []),
    ['Wind there is', b.wind_m_s, b.limits.wind_m_s],
  ]
  const known = measures.filter(([, v]) => entered(v))
  if (known.length) {
    return known
      .map(([lead, v, lim]) => `${lead} forecast at ${quantityText(v)}${entered(lim) ? ` against the team’s limit of ${quantityText(lim)}` : ''}.`)
      .join(' ')
  }
  const reasons = [...new Set(measures.map(([, v]) => v?.missing_reason).filter((r): r is string => Boolean(r)))]
  if (reasons.length === 1) return reasons[0]
  return 'Neither the sea nor the wind at the zone is forecast yet; each number below says why.'
}

/**
 * Return (design-lifecycle.md §4): where the booster and any capsule come
 * down, and the sea there beside the team's own limits.
 */
export function ReturnSection({ mission: m }: { mission: MissionDetail }) {
  const view = useSection<ReturnDTO>('return', m.id, (signal) => api.returnSection(m.id, signal))
  const status = useSectionStatus(m.id, 'return')
  return (
    <SectionLayout question="Where do the booster and any capsule come down, and what is the sea like there?">
      <SectionStates view={view} terms={TERMS} status={status}>
        {({ data, meta }) => <ReturnAnswer ret={data} meta={meta} missionId={m.id} status={status} />}
      </SectionStates>
    </SectionLayout>
  )
}

function ReturnAnswer({ ret, meta, missionId, status }: { ret: ReturnDTO; meta: LifecycleMetaDTO; missionId: string; status?: SectionStatusDTO }) {
  const b = ret.booster
  const c = ret.capsule
  const capsule = Boolean(c?.applicable)
  const fetched = meta.sources.map((s) => (s.fetched_at ? Date.parse(s.fetched_at) : NaN)).filter((n) => !Number.isNaN(n))
  const age = fetched.length ? `as of ${ageWords(Math.min(...fetched))}` : undefined

  // No booster to speak of: a cancelled delivery, or a launch vehicle not published yet.
  if (!b && !capsule) {
    const w = status && status.state !== 'available' && status.state !== 'computing' ? STATE_WORDS[status.state] : null
    return (
      <>
        <StatePanel
          icon={w?.icon ?? (c ? 'ring' : 'dash')}
          title={w?.words ?? (c ? 'No data yet' : 'Nothing to recover')}
          detail={
            status?.summary ??
            (c
              ? `The launch vehicle is not published yet, so where its booster comes down is not known. ${c.reason ?? ''}`.trim()
              : 'Nothing launches on this mission, so nothing comes back.')
          }
          stillWorks="Every other step is unaffected."
        />
        <Rows>
          <SourcesRow meta={meta} />
        </Rows>
      </>
    )
  }

  const recovered = b && b.landing !== 'expended'
  const rows: LimitRow[] = [
    ...(recovered && b.landing !== 'land'
      ? [{ id: 'b-waves', label: 'Waves at the booster landing zone', value: b.wave_height_m, limit: b.limits.wave_height_m }]
      : []),
    ...(recovered ? [{ id: 'b-wind', label: 'Wind at the booster landing zone', value: b.wind_m_s, limit: b.limits.wind_m_s }] : []),
    ...(capsule && c
      ? [
          { id: 'c-waves', label: 'Waves at the splashdown zone', value: c.wave_height_m, limit: c.limits.wave_height_m },
          { id: 'c-wind', label: 'Wind at the splashdown zone', value: c.wind_m_s, limit: c.limits.wind_m_s },
        ]
      : []),
  ]
  const row = (id: string) => rows.find((r) => r.id === id)
  const over = rows.filter((r) => overBy(r) !== null)
  // Bars only when there is something to draw: a forecast or a limit the team entered.
  const drawn = rows.some((r) => entered(r.value) || entered(r.limit))
  const limitNote = (r: LimitRow | undefined) =>
    !entered(r?.limit) ? 'No limit entered by the team' : overBy(r!) !== null ? `Over the team’s limit of ${quantityText(r!.limit)}` : `Team’s limit ${quantityText(r!.limit)}`
  const tile = (term: string, id: string, q: QuantityDTO | null | undefined, fallback: string) => {
    const r = row(id)
    return (
      <QuantityTile
        term={term}
        q={q ?? missing(fallback)}
        tone={r && overBy(r) !== null ? 'alert' : 'neutral'}
        note={r ? limitNote(r) : undefined}
        age={entered(q) ? age : undefined}
      />
    )
  }

  return (
    <>
      <Answer meta={meta}>
        {b ? `${b.note} ${seaWords(b)}`.trim() : 'Where the booster comes down is not known.'}{' '}
        {capsule ? (c?.zone ? `A capsule splashes down ${zoneWords(c.zone)}.` : 'A capsule returns; its splashdown zone is not known yet.') : (c?.reason ?? 'No capsule returns on this mission.')}
      </Answer>
      <NumberRow>
        {recovered ? (
          <>
            {b.landing === 'land' ? <QuantityTile term="boosterWaves" q={missing('On land: no waves to forecast.')} /> : tile('boosterWaves', 'b-waves', b.wave_height_m, 'No sea forecast for the zone')}
            {tile('boosterWind', 'b-wind', b.wind_m_s, 'No wind forecast for the zone')}
          </>
        ) : (
          <>
            <QuantityTile term="boosterWaves" q={missing(b ? 'The booster is not recovered.' : 'Where the booster comes down is not known.')} />
            <QuantityTile term="boosterWind" q={missing(b ? 'The booster is not recovered.' : 'Where the booster comes down is not known.')} />
          </>
        )}
        {capsule && c && (
          <>
            {tile('capsuleWaves', 'c-waves', c.wave_height_m, 'No sea forecast for the zone')}
            {tile('capsuleWind', 'c-wind', c.wind_m_s, 'No wind forecast for the zone')}
          </>
        )}
      </NumberRow>
      {drawn && (
        <ChartPanel
          title={over.length ? `Against the team’s limits: ${over.length} over` : 'Against the team’s limits'}
          chart={<LimitBars rows={rows} />}
          legend={
            <ul className="flex flex-wrap gap-x-5 gap-y-2 text-caption text-ink-2">
              <li className="flex items-center gap-2">
                <span aria-hidden="true" className="h-3 w-5 bg-terrain-high" />
                Forecast
              </li>
              <li className="flex items-center gap-2">
                <span aria-hidden="true" className="hatch-uncertain h-3 w-5" />
                How far it could be off
              </li>
              <li className="flex items-center gap-2">
                <span aria-hidden="true" className="h-4 w-[3px] bg-ink" />
                The team’s limit
              </li>
              <li className="flex items-center gap-2">
                <span aria-hidden="true" className="hatch-alert h-3 w-5" />
                Over the limit
              </li>
            </ul>
          }
          table={<LimitTable rows={rows} />}
        />
      )}
      <Rows>
        {b && (
          <Disclosure title="Booster landing zone" meta={b.zone && b.landing !== 'unknown' ? zoneWords(b.zone) : NO_ZONE[b.landing]}>
            <p className="text-body leading-6 text-ink-2">
              {b.note}{' '}
              {/* Not published yet: the zone is where the sea is read (as the note says), not a published zone. */}
              {b.zone
                ? b.landing === 'unknown'
                  ? `The sea is read ${zoneWords(b.zone)}.`
                  : `The zone is ${zoneWords(b.zone)}${b.zone.pm_km == null ? '; its size is not published' : ''}.`
                : ''}{' '}
              {b.hazard_area_seen === true
                ? 'A published hazard area at sea matches this zone.'
                : b.hazard_area_seen === false
                  ? 'No published hazard area at sea matches this zone yet.'
                  : ''}
            </p>
          </Disclosure>
        )}
        <Disclosure title="Splashdown zone" meta={capsule ? (c?.zone ? zoneWords(c.zone) : 'not known yet') : 'does not apply'}>
          <p className="text-body leading-6 text-ink-2">
            {capsule
              ? `${c?.zone ? `Splashdown ${zoneWords(c.zone)}.` : 'The zone is not known yet.'}${
                  c?.daylight === true ? ' In daylight at splashdown.' : c?.daylight === false ? ' In darkness at splashdown.' : ''
                }${c?.model_check ? '' : ' The capsule model has not been checked against a real landing here.'}`
              : (c?.reason ?? 'No capsule returns on this mission.')}
          </p>
        </Disclosure>
        {c?.model_check && <CapsuleCheckRow check={c.model_check} />}
        {(recovered || capsule) && <LimitsRow ret={ret} missionId={missionId} />}
        <HowSure meta={meta} />
        <SourcesRow meta={meta} />
      </Rows>
    </>
  )
}

/** Whether the plan's limit on the distance is met, from what the service serves (`passed`, `limit_km`), never from a number written here. */
export function capsuleLimitWords(k: Pick<CapsuleModelCheckDTO, 'passed' | 'limit_km' | 'distance_km'>): { met: boolean; short: string; long: string } {
  const km = (v: number) => `${formatValue(v)} km`
  const gap = formatValue(Math.abs(k.distance_km - k.limit_km))
  return k.passed
    ? { met: true, short: `the plan’s ${km(k.limit_km)} is met`, long: `The plan’s ${km(k.limit_km)} is met, with ${gap} km to spare.` }
    : { met: false, short: `the plan’s ${km(k.limit_km)} is not met`, long: `The plan’s ${km(k.limit_km)} is not met: ${gap} km over the limit.` }
}

/**
 * The capsule entry model against a real landing (OSIRIS-REx): the service's
 * own words first, whether the plan's limit is met, the air the modelled fall
 * went through, then the numbers they rest on, when it was checked and where
 * the entry state and the landing are from.
 */
export function CapsuleCheckRow({ check: k }: { check: CapsuleModelCheckDTO }) {
  const km = (v: number) => `${formatValue(v)} km`
  const [lo, hi] = k.distance_range_km
  const [long, wide] = k.ellipse_99_km
  const limit = capsuleLimitWords(k)
  const rows: [string, string][] = [
    ['The case', k.case],
    ['The air the modelled fall went through', k.atmosphere],
    ['From the real landing point', `${km(k.distance_km)}${lo != null && hi != null ? ` (${formatValue(lo)} to ${km(hi)} over the published drag range)` : ''}`],
    ['The limit', km(k.limit_km)],
    ['The mission’s own simulation', `${km(k.mission_team_km)} from it`],
    [
      'Its 99 % landing area',
      `${long != null && wide != null ? `${formatValue(long)} by ${km(wide)}; ` : ''}${k.measured_inside_ellipse ? 'holds the real landing point' : 'does not hold the real landing point'}`,
    ],
    ['Checked', dateTimeWords(Date.parse(k.checked_at))],
  ]
  return (
    <Disclosure title="The capsule model, checked against a real landing" meta={`${km(k.distance_km)} from it; ${limit.short}`}>
      <div className="flex flex-col gap-3">
        <p className="text-body leading-6 text-ink-2">{k.note}</p>
        {limit.met ? (
          <p className="text-small font-semibold text-ink">{limit.long}</p>
        ) : (
          <p className="flex items-start gap-2 text-small font-semibold text-alert">
            <Icon name="alert" size={15} strokeWidth={2.2} className="mt-0.5 shrink-0" />
            {limit.long}
          </p>
        )}
        <dl className="flex flex-col gap-2 text-small leading-5">
          {rows.map(([label, value]) => (
            <div key={label}>
              <dt className="font-semibold text-ink-2">{label}</dt>
              <dd className="text-ink-2">{value}</dd>
            </div>
          ))}
          {k.sources.length > 0 && (
            <div>
              <dt className="font-semibold text-ink-2">Where the entry state and the landing are from</dt>
              <dd className="text-ink-2">
                <ul className="flex flex-col gap-1">
                  {k.sources.map((s) =>
                    /^https?:\/\//.test(s) ? (
                      <li key={s}>
                        <a href={s} target="_blank" rel="noreferrer">
                          {hostWords(s)}: {s.split('/').pop()}
                        </a>
                      </li>
                    ) : (
                      <li key={s}>{s}</li>
                    ),
                  )}
                </ul>
              </dd>
            </div>
          )}
        </dl>
      </div>
    </Disclosure>
  )
}

function missing(reason: string): QuantityDTO {
  return { value: null, unit: '', provenance: 'computed', pm: null, lo: null, hi: null, factor: null, open: false, no_margin_reason: null, missing_reason: reason, source: null }
}

/** One part's entered limits in words: "waves 2.5 m, wind none entered". */
function limitsWords(l: SeaLimitsDTO | undefined, waves: boolean): string {
  if (!l) return ''
  const one = (what: string, q: QuantityDTO) => `${what} ${entered(q) ? quantityText(q) : 'none entered'}`
  return [waves ? one('waves', l.wave_height_m) : null, one('wind', l.wind_m_s)].filter(Boolean).join(', ')
}

const field = (q: QuantityDTO | undefined) => (entered(q) ? String(q.value) : '')

/**
 * The team's sea limits: launch providers do not publish theirs (ADR-14).
 * The PUT replaces both parts, so the form starts from what is entered and
 * sends a part it does not show as it stands.
 */
function LimitsRow({ ret, missionId }: { ret: ReturnDTO; missionId: string }) {
  const canWrite = useCanWrite()
  const [open, setOpen] = useState(false)
  const history = useHistory('limits', open ? `return:${missionId}` : null)
  const write = useLifecycleWrite((body: Parameters<typeof api.returnLimits>[1]) => api.returnLimits(missionId, body))
  const b = ret.booster && ret.booster.landing !== 'expended' ? ret.booster : null
  const c = ret.capsule?.applicable ? ret.capsule : null
  const bWaves = b?.landing !== 'land'
  const [vals, setVals] = useState({ bw: '', bv: '', cw: '', cv: '' })
  // The first field that is not a number above zero, and what is wrong with it.
  const [err, setErr] = useState<{ key: keyof typeof vals; msg: string } | undefined>()
  const all = [b?.limits.wave_height_m, b?.limits.wind_m_s, c?.limits.wave_height_m, c?.limits.wind_m_s]
  const who = [...new Set(all.filter(entered).map((q) => q.source ?? 'the team'))]
  const set = (k: keyof typeof vals) => (e: { target: { value: string } }) => setVals((v) => ({ ...v, [k]: e.target.value }))
  const num = (s: string) => (s.trim() === '' ? null : Number(s))
  const current = (q: QuantityDTO | undefined) => (entered(q) ? q.value : null)
  return (
    <Disclosure title="Team limits" meta={who.length ? `entered by ${who.join(', ')}` : 'none entered'}>
      <p className="text-body leading-6 text-ink-2">
        Launch providers do not publish their sea and wind limits for recovery, so the team enters the ones it is given.
        {b && ` Booster landing zone: ${limitsWords(b.limits, bWaves)}.`}
        {c && ` Splashdown zone: ${limitsWords(c.limits, true)}.`}
      </p>
      {canWrite && (
        <div>
          <Button
            onClick={() => {
              setVals({ bw: field(b?.limits.wave_height_m), bv: field(b?.limits.wind_m_s), cw: field(c?.limits.wave_height_m), cv: field(c?.limits.wind_m_s) })
              setErr(undefined)
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
        title="Team sea limits"
        intro="Leave a field empty for no limit."
        saving={write.isPending}
        error={write.error}
        history={<HistoryList entries={history.data} pending={history.isPending} error={history.error} />}
        onSave={async () => {
          const shown: (keyof typeof vals)[] = [...(b ? [...(bWaves ? (['bw'] as const) : []), 'bv' as const] : []), ...(c ? (['cw', 'cv'] as const) : [])]
          const bad = shown.find((k) => {
            const x = num(vals[k])
            return x !== null && !(x > 0)
          })
          if (bad) {
            setErr({ key: bad, msg: 'A limit is a number above zero, or empty for none.' })
            return false
          }
          setErr(undefined)
          const rb = ret.booster?.limits
          const rc = ret.capsule?.limits
          try {
            await write.mutateAsync({
              booster: {
                wave_height_m: b && bWaves ? num(vals.bw) : current(rb?.wave_height_m),
                wind_m_s: b ? num(vals.bv) : current(rb?.wind_m_s),
              },
              capsule: {
                wave_height_m: c ? num(vals.cw) : current(rc?.wave_height_m),
                wind_m_s: c ? num(vals.cv) : current(rc?.wind_m_s),
              },
            })
            return true
          } catch {
            return false
          }
        }}
      >
        {b && bWaves && (
          <Field label="Booster landing zone: highest waves (metres)" error={err?.key === 'bw' ? err.msg : undefined}>
            {(p) => <TextInput {...p} inputMode="decimal" value={vals.bw} onChange={set('bw')} />}
          </Field>
        )}
        {b && (
          <Field label="Booster landing zone: strongest wind (metres a second)" error={err?.key === 'bv' ? err.msg : undefined}>
            {(p) => <TextInput {...p} inputMode="decimal" value={vals.bv} onChange={set('bv')} />}
          </Field>
        )}
        {c && (
          <>
            <Field label="Splashdown zone: highest waves (metres)" error={err?.key === 'cw' ? err.msg : undefined}>
              {(p) => <TextInput {...p} inputMode="decimal" value={vals.cw} onChange={set('cw')} />}
            </Field>
            <Field label="Splashdown zone: strongest wind (metres a second)" error={err?.key === 'cv' ? err.msg : undefined}>
              {(p) => <TextInput {...p} inputMode="decimal" value={vals.cv} onChange={set('cv')} />}
            </Field>
          </>
        )}
      </FormSheet>
    </Disclosure>
  )
}
