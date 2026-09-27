import { useState } from 'react'
import { api } from '../../lib/api/client'
import type { MissionDetail } from '../../lib/api/adapters'
import type { LifecycleMetaDTO, ReturnDTO, ZoneDTO } from '../../lib/api/lifecycle'
import { useHistory, useLifecycleWrite, useSection, useSectionStatus } from '../../lib/api/lifecycleQueries'
import { ageWords, formatValue, quantityText } from '../../lib/lifecycle/quantity'
import { NumberRow, QuantityTile } from '../../components/lifecycle/QuantityTile'
import { Answer, ChartPanel, HowSure, Rows, SectionLayout, SectionStates, SourcesRow, StatePanel } from '../../components/lifecycle/Section'
import { LimitBars, LimitTable, overBy, type LimitRow } from '../../components/lifecycle/LimitBars'
import { Field, FormSheet, HistoryList, TextInput } from '../../components/lifecycle/Forms'
import { Button, Disclosure } from '../../components/ui'
import { Icon } from '../../components/Icon'
import { useCanWrite } from './ReadySection'

const TERMS = ['boosterWaves', 'boosterWind', 'capsuleWaves', 'capsuleWind']

const LANDING_WORDS: Record<NonNullable<ReturnDTO['booster']>['landing'], string> = {
  droneship: 'lands on a droneship',
  land: 'lands back on land',
  expended: 'is not recovered',
  unknown: 'comes down where its operator has not published',
}

function zoneWords(z: ZoneDTO): string {
  const ns = z.lat_deg < 0 ? 'S' : 'N'
  const ew = z.lon_deg < 0 ? 'W' : 'E'
  return `near ${Math.abs(z.lat_deg).toFixed(1)}°${ns} ${Math.abs(z.lon_deg).toFixed(1)}°${ew}, ±${formatValue(z.pm_km)} km`
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
        {({ data, meta }) => <ReturnAnswer ret={data} meta={meta} missionId={m.id} />}
      </SectionStates>
    </SectionLayout>
  )
}

function ReturnAnswer({ ret, meta, missionId }: { ret: ReturnDTO; meta: LifecycleMetaDTO; missionId: string }) {
  const b = ret.booster
  const c = ret.capsule
  const capsule = Boolean(c?.applicable)
  const fetched = meta.sources.map((s) => (s.fetched_at ? Date.parse(s.fetched_at) : NaN)).filter((n) => !Number.isNaN(n))
  const age = fetched.length ? `as of ${ageWords(Math.min(...fetched))}` : undefined

  if (!b && !capsule) {
    return (
      <>
        <StatePanel
          icon="dash"
          title="Nothing to recover"
          detail={c?.reason ?? 'The booster is not recovered and nothing returns to Earth on this mission.'}
          stillWorks="Every other step is unaffected."
        />
        <Rows>
          <SourcesRow meta={meta} />
        </Rows>
      </>
    )
  }

  const rows: LimitRow[] = [
    ...(b && b.landing !== 'expended'
      ? [
          { id: 'b-waves', label: 'Waves at the booster landing zone', value: b.wave_height_m, limit: b.limits.wave_height_m },
          { id: 'b-wind', label: 'Wind at the booster landing zone', value: b.wind_m_s, limit: b.limits.wind_m_s },
        ]
      : []),
    ...(capsule && c
      ? [
          { id: 'c-waves', label: 'Waves at the splashdown zone', value: c.wave_height_m, limit: null },
          { id: 'c-wind', label: 'Wind at the splashdown zone', value: c.wind_m_s, limit: null },
        ]
      : []),
  ]
  const over = rows.filter((r) => overBy(r) !== null)
  const limitNote = (v: typeof rows[number] | undefined) =>
    !v?.limit?.value ? 'No limit entered by the team' : overBy(v) !== null ? `Over the team’s limit of ${quantityText(v.limit)}` : `Team’s limit ${quantityText(v.limit)}`

  return (
    <>
      <Answer meta={meta}>
        {b ? (
          <>
            The booster {LANDING_WORDS[b.landing]}
            {b.zone ? ` ${zoneWords(b.zone)}` : ''}.
            {b.wave_height_m?.value != null && (
              <>
                {' '}
                Waves there are forecast at {quantityText(b.wave_height_m)}
                {b.limits.wave_height_m?.value != null ? ` against the team’s limit of ${quantityText(b.limits.wave_height_m)}` : ''}.
              </>
            )}
          </>
        ) : (
          'The booster’s landing is not known.'
        )}{' '}
        {capsule ? (c?.zone ? `A capsule splashes down ${zoneWords(c.zone)}.` : 'A capsule returns; its splashdown zone is not known yet.') : 'No capsule returns on this mission.'}
      </Answer>
      <NumberRow>
        {b && b.landing !== 'expended' ? (
          <>
            <QuantityTile term="boosterWaves" q={b.wave_height_m ?? missing('No sea forecast for the zone')} tone={overBy(rows[0]) !== null ? 'alert' : 'neutral'} note={limitNote(rows[0])} age={age} />
            <QuantityTile term="boosterWind" q={b.wind_m_s ?? missing('No wind forecast for the zone')} tone={overBy(rows[1]) !== null ? 'alert' : 'neutral'} note={limitNote(rows[1])} age={age} />
          </>
        ) : (
          <>
            <QuantityTile term="boosterWaves" q={missing('The booster is not recovered.')} />
            <QuantityTile term="boosterWind" q={missing('The booster is not recovered.')} />
          </>
        )}
        {capsule && c && (
          <>
            <QuantityTile term="capsuleWaves" q={c.wave_height_m ?? missing('No sea forecast for the zone')} age={age} />
            <QuantityTile term="capsuleWind" q={c.wind_m_s ?? missing('No wind forecast for the zone')} age={age} />
          </>
        )}
      </NumberRow>
      {rows.length > 0 && (
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
          <Disclosure title="Booster landing zone" meta={b.zone ? zoneWords(b.zone) : 'not published'}>
            <p className="text-body leading-6 text-ink-2">
              The booster {LANDING_WORDS[b.landing]}
              {b.zone ? `, ${zoneWords(b.zone)}` : ''}.{' '}
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
                }`
              : (c?.reason ?? 'No capsule returns on this mission.')}
          </p>
        </Disclosure>
        <LimitsRow ret={ret} missionId={missionId} />
        <HowSure meta={meta} />
        <SourcesRow meta={meta} />
      </Rows>
    </>
  )
}

function missing(reason: string) {
  return { value: null, unit: '', provenance: 'computed' as const, pm: null, lo: null, hi: null, factor: null, open: false, no_margin_reason: null, missing_reason: reason, source: null }
}

/** The team's sea limits: recovery operators do not publish theirs (ADR-14). */
function LimitsRow({ ret, missionId }: { ret: ReturnDTO; missionId: string }) {
  const canWrite = useCanWrite()
  const [open, setOpen] = useState(false)
  const history = useHistory('limits', open ? missionId : null)
  const write = useLifecycleWrite((b: Parameters<typeof api.returnLimits>[1]) => api.returnLimits(missionId, b))
  const lim = ret.booster?.limits
  const [waves, setWaves] = useState('')
  const [wind, setWind] = useState('')
  const [err, setErr] = useState<string | undefined>()
  const num = (s: string) => (s.trim() === '' ? null : Number(s))
  return (
    <Disclosure title="Team limits" meta={lim?.wave_height_m?.value != null || lim?.wind_m_s?.value != null ? `entered by ${lim?.wave_height_m?.source ?? lim?.wind_m_s?.source ?? 'the team'}` : 'none entered'}>
      <p className="text-body leading-6 text-ink-2">
        Recovery operators do not publish their sea limits, so the team enters its own. Waves:{' '}
        {lim?.wave_height_m ? quantityText(lim.wave_height_m) : 'none'}. Wind: {lim?.wind_m_s ? quantityText(lim.wind_m_s) : 'none'}.
      </p>
      {canWrite && (
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
        title="Team sea limits"
        intro="For the booster landing zone. Leave a field empty for no limit."
        saving={write.isPending}
        error={write.error}
        history={<HistoryList entries={history.data} pending={history.isPending} error={history.error} />}
        onSave={async () => {
          const w = num(waves)
          const v = num(wind)
          if ((w !== null && !(w > 0)) || (v !== null && !(v > 0))) {
            setErr('Limits are positive numbers.')
            return false
          }
          setErr(undefined)
          try {
            await write.mutateAsync({ booster: { wave_height_m: w, wind_m_s: v }, capsule: { wave_height_m: null, wind_m_s: null } })
            return true
          } catch {
            return false
          }
        }}
      >
        <Field label="Highest waves (metres)" error={err}>
          {(p) => <TextInput {...p} inputMode="decimal" value={waves} onChange={(e) => setWaves(e.target.value)} />}
        </Field>
        <Field label="Strongest wind (metres a second)">
          {(p) => <TextInput {...p} inputMode="decimal" value={wind} onChange={(e) => setWind(e.target.value)} />}
        </Field>
      </FormSheet>
    </Disclosure>
  )
}
