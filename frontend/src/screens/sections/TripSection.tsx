import { api } from '../../lib/api/client'
import { API_BASE } from '../../lib/api/client'
import type { MissionDetail } from '../../lib/api/adapters'
import type { AssumptionDTO, LifecycleMetaDTO, QuantityDTO, TripDTO } from '../../lib/api/lifecycle'
import { useSection, useSectionStatus } from '../../lib/api/lifecycleQueries'
import { formatValue, quantityText } from '../../lib/lifecycle/quantity'
import { dateTimeWords } from '../../lib/format'
import { NumberRow, QuantityTile } from '../../components/lifecycle/QuantityTile'
import {
  Answer,
  ChartPanel,
  HowSure,
  Legend,
  Rows,
  SectionLayout,
  SectionStates,
  SourcesRow,
  StatePanel,
} from '../../components/lifecycle/Section'
import { TripLegendItems, TripStrip, TripTable, tripSpan, tripStretches } from '../../components/lifecycle/TripStrip'
import { UncertaintyNote } from '../../components/States'
import { Disclosure } from '../../components/ui'
import { RadiationRow } from '../../components/lifecycle/Radiation'

const TERMS = ['tripSunlight', 'tripHeard', 'tripShadow', 'tripUnheard']
const HOUR = 3_600_000
/** The formats `GET /missions/{id}/trip/export` serves (SPICE SPK is not served). */
const TRIP_EXPORTS = [
  ['oem', 'CCSDS orbit file (OEM)'],
  ['csv', 'Spreadsheet (CSV)'],
] as const

/**
 * Trip (design-lifecycle.md §4): the way from Earth to the Moon, with the
 * sunlight, the shadow and the contact along it.
 */
export function TripSection({ mission: m }: { mission: MissionDetail }) {
  const view = useSection<TripDTO>('trip', m.id, (signal) => api.trip(m.id, signal))
  const status = useSectionStatus(m.id, 'trip')
  return (
    <SectionLayout question="What does the lander go through on the way?">
      <SectionStates view={view} terms={TERMS} status={status}>
        {({ data: trip, meta }) =>
          trip.source === 'none' ? (
            <StatePanel
              icon="ring"
              title="No trip to show yet"
              detail={trip.none_reason ?? 'No trajectory is available for this mission.'}
              stillWorks="Landing, Contact and the other steps do not depend on the trip and work as usual."
            />
          ) : (
            <TripAnswer trip={trip} meta={meta} missionId={m.id} />
          )
        }
      </SectionStates>
    </SectionLayout>
  )
}

/** "the longest time … is X", or "at least X" when the dates cut it short. */
function longest(q: QuantityDTO): string {
  return q.open ? `at least ${quantityText({ ...q, open: false })}` : quantityText(q)
}

/**
 * The answer's second sentence, with no zero-hour stretches in it. With gaps in
 * the data (`coveredH` given), it is said of the hours the data covers only.
 */
export function shadowAndContact(n: TripDTO['numbers'], coveredH?: number): string {
  const neverDark = n.longest_shadow_h.value === 0
  const alwaysHeard = n.longest_unheard_h.value === 0
  const dark = neverDark ? 'It is never in shadow' : `The longest time in shadow is ${longest(n.longest_shadow_h)}`
  const heard = alwaysHeard
    ? 'a ground station can hear it the whole time'
    : `the longest time without contact is ${longest(n.longest_unheard_h)}`
  const said = `${dark}${neverDark && !alwaysHeard ? ';' : ', and'} ${heard}.`
  if (coveredH == null) return said
  return `In the ${formatValue(coveredH)} hours NASA’s reconstruction covers, ${said[0].toLowerCase()}${said.slice(1)}`
}

function TripAnswer({ trip, meta, missionId }: { trip: TripDTO; meta: LifecycleMetaDTO; missionId: string }) {
  const { t0, t1 } = tripSpan(trip)
  const hours = (t1 - t0) / HOUR
  const stretches = tripStretches(trip)
  const gaps = stretches.some((r) => r.kind === 'nodata')
  const coveredH = hours - stretches.filter((r) => r.kind === 'nodata').reduce((h, r) => h + (r.end - r.start) / HOUR, 0)
  const n = trip.numbers
  return (
    <>
      <Answer meta={meta}>
        The trip takes {formatValue(hours / 24)} days ({trip.source === 'flown' ? 'as flown' : 'as designed'}). {shadowAndContact(n, gaps ? coveredH : undefined)}
      </Answer>
      {/* Only when the data has gaps does the note change what the numbers mean. */}
      {gaps && trip.coverage_note && <UncertaintyNote className="-mt-3">{trip.coverage_note}</UncertaintyNote>}
      <NumberRow>
        <QuantityTile term="tripSunlight" q={n.sunlight_h} tone="sun" icon="sun" scale={hours} />
        <QuantityTile term="tripHeard" q={n.heard_h} tone="earth" icon="earth" scale={hours} />
        <QuantityTile term="tripShadow" q={n.longest_shadow_h} scale={hours} />
        <QuantityTile term="tripUnheard" q={n.longest_unheard_h} scale={hours} />
      </NumberRow>
      <ChartPanel
        title="The trip, day by day"
        chart={<TripStrip trip={trip} stretches={stretches} />}
        legend={<Legend items={TripLegendItems(trip)} />}
        table={<TripTable trip={trip} stretches={stretches} />}
      />
      <Rows>
        <RadiationRow r={trip.radiation} note={trip.radiation_note} />
        <Disclosure title="Burns" meta={trip.burns.length ? `${trip.burns.length}` : 'none listed'}>
          {trip.burns.length === 0 ? (
            <p className="text-body leading-6 text-ink-2">{trip.burns_note ?? 'No burns are listed for this trip.'}</p>
          ) : (
            <>
              <ol className="flex flex-col gap-2.5">
                {trip.burns.map((b, i) => (
                  <li key={b.t} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-body">
                    <span className="font-mono text-caption text-ink-3">{i + 1}</span>
                    <span className="font-semibold text-ink">{b.name}</span>
                    <span className="text-ink-2">{dateTimeWords(Date.parse(b.t))}</span>
                    <span className="font-mono text-small text-ink">{quantityText(b.dv_m_s)}</span>
                    {b.dv_m_s.pm === null && b.dv_m_s.no_margin_reason && (
                      <span className="basis-full text-caption leading-caption text-ink-3">{b.dv_m_s.no_margin_reason}</span>
                    )}
                  </li>
                ))}
              </ol>
              {trip.burns_note && <p className="text-small leading-5 text-ink-2">{trip.burns_note}</p>}
            </>
          )}
        </Disclosure>
        <CorrectionsRow c={trip.corrections} note={trip.corrections_note} />
        {trip.moon_pull && <MoonPullRow pull={trip.moon_pull} />}
        {/* Only a flown trip can be exported; a designed one answers 409 no-export. */}
        {trip.source === 'flown' && <TripDownloads trip={trip} missionId={missionId} />}
        <HowSure meta={meta} />
        <SourcesRow meta={meta} />
      </Rows>
    </>
  )
}

/**
 * The flown trajectory as a file: one block per stretch NASA's reconstruction
 * covers, nothing filled in across the gaps between them.
 */
function TripDownloads({ trip, missionId }: { trip: TripDTO; missionId: string }) {
  const blocks = trip.covered?.length ?? 0
  return (
    <Disclosure title="Download the trip" meta="orbit file, spreadsheet">
      <p className="text-small leading-5 text-ink-2">
        The flown trajectory from NASA’s reconstruction, every 10 minutes, centred on Earth (EME2000 frame, km and km/s).
        {blocks > 1
          ? ` The reconstruction covers the trip in ${blocks} separate stretches, so the file has ${blocks} blocks; nothing is filled in across the gaps.`
          : ''}
      </p>
      <ul className="flex flex-wrap gap-3">
        {TRIP_EXPORTS.map(([f, label]) => (
          <li key={f}>
            <a
              className="inline-flex h-12 items-center rounded-control border border-line-strong px-4 text-body font-semibold text-ink no-underline hover:bg-inset"
              href={`${API_BASE}/missions/${encodeURIComponent(missionId)}/trip/export?format=${f}`}
              download
            >
              {label}
            </a>
          </li>
        ))}
      </ul>
    </Disclosure>
  )
}

/** "18.1 m/s": the figure alone, for a value whose spread is said in words beside it. */
function figure(q: QuantityDTO): string {
  return q.value === null ? quantityText(q) : `${formatValue(q.value)} ${q.unit}`
}

/** "16.5–19.9 m/s", when the quantity carries a range beside its value. */
function spread(q: QuantityDTO): string | null {
  return q.lo === null || q.hi === null ? null : `${formatValue(q.lo)}–${formatValue(q.hi)} ${q.unit}`
}

/**
 * The heading over the errors a budget rests on, in plain words, read from each
 * one's `basis` and `source` as served: how many the launch vehicle's guide
 * publishes and how many are assumed; and, when the served sources of the
 * published speed errors say the guide's row for a transfer orbit to
 * geosynchronous orbit stands in for a launch to the Moon, that they are worked
 * out from it. A saved copy from before `basis` was served has none and reads
 * as assumed.
 */
export function errorsHeading(list: Pick<AssumptionDTO, 'what' | 'basis' | 'source'>[]): { mix: string; speed: string | null } {
  const n = list.length
  const published = list.filter((a) => a.basis === 'published').length
  const rest = n - published
  const mix =
    published === 0
      ? 'Every error here is assumed'
      : rest === 0
        ? 'Every error here is published in the launch vehicle’s guide'
        : `${published} of the ${n} errors here ${published === 1 ? 'is' : 'are'} published in the launch vehicle’s guide; the other ${rest} ${rest === 1 ? 'is' : 'are'} assumed`
  const speeds = list.filter((a) => a.basis === 'published' && /speed/i.test(a.what) && /geosynchronous/i.test(a.source ?? ''))
  const noLunarRow = speeds.some((a) => /no row for a launch to the Moon/i.test(a.source ?? ''))
  return {
    mix,
    speed: speeds.length
      ? `The speed errors on leaving Earth are worked out from the guide’s published accuracy for a transfer orbit to geosynchronous orbit${noLunarRow ? ', since it has no row for a launch to the Moon' : ''}.`
      : null,
  }
}

/**
 * How much the corrections on the way could need under assumed errors: a
 * budget over many runs, never a prediction (the service's `label` says so
 * first). Each size says its sample ("in 99 of 100 runs", of how many).
 */
export function CorrectionsRow({ c, note }: { c: TripDTO['corrections']; note: string | null }) {
  if (!c) {
    return (
      <Disclosure title="Corrections on the way" meta="no budget">
        <p className="text-body leading-6 text-ink-2">{note ?? 'No correction budget is worked out for this trip.'}</p>
      </Disclosure>
    )
  }
  const interval = spread(c.total_p99_m_s)
  const arrival = spread(c.arrival_altitude_km)
  const errors = errorsHeading(c.assumptions)
  const cell = 'px-3 py-2 text-small text-ink-2 align-top'
  const num = `${cell} text-right font-mono tnum whitespace-nowrap text-ink`
  const head = 'px-3 py-2.5 text-tag font-semibold tracking-caps-md text-ink-3 uppercase align-bottom'
  return (
    <Disclosure title="Corrections on the way" meta={`a budget: ${figure(c.total_p99_m_s)} in 99 of 100 runs`}>
      <p className="text-body leading-6 font-semibold text-ink">{c.label}</p>
      <p className="text-body leading-6 text-ink-2">
        In {formatValue(c.runs)} runs of the flight as planned with the errors below, the {c.burns.length} corrections
        together needed at most {figure(c.total_p95_m_s)} in 95 of 100 runs and at most {figure(c.total_p99_m_s)} in 99 of 100
        {interval ? ` (${interval}, allowing for the number of runs)` : ''}. Worked out linearly instead: {figure(c.linear_p99_m_s)} in 99 of
        100. {c.missed ? `${c.missed} of the runs did not pass close to the Moon; they are counted, not dropped.` : 'Every run passed close to the Moon.'}{' '}
        On arrival it passes {figure(c.arrival_altitude_km)} above the Moon in the middle run
        {arrival ? `, and ${arrival} in 98 of 100` : ''}.
      </p>
      <table className="w-full border-collapse border border-line text-left">
        <caption className="sr-only">Each correction, when it is made, and the speed it needs in 95 and in 99 of 100 runs.</caption>
        <thead>
          <tr className="bg-inset">
            <th scope="col" className={head}>Correction</th>
            <th scope="col" className={`${head} text-right`}>Enough in 95 of 100 runs</th>
            <th scope="col" className={`${head} text-right`}>Enough in 99 of 100 runs</th>
          </tr>
        </thead>
        <tbody>
          {c.burns.map((b) => (
            <tr key={b.t} className="border-t border-line">
              <th scope="row" className={`${cell} font-normal`}>
                <span className="block font-semibold text-ink">{b.name}</span>
                {dateTimeWords(Date.parse(b.t))}
              </th>
              <td className={num}>{figure(b.p95_m_s)}</td>
              <td className={num}>{figure(b.p99_m_s)}</td>
            </tr>
          ))}
          <tr className="border-t border-line-strong">
            <th scope="row" className={`${cell} font-semibold text-ink`}>
              All {c.burns.length} together
            </th>
            <td className={num}>{figure(c.total_p95_m_s)}</td>
            <td className={num}>{figure(c.total_p99_m_s)}</td>
          </tr>
        </tbody>
      </table>
      <p className="text-caption leading-caption text-ink-3">
        The total is taken run by run, not by adding up the sizes above.
      </p>
      <div className="flex flex-col gap-2">
        <h4 className="text-small font-semibold text-ink">
          {errors.mix}
          {errors.speed && <span className="mt-0.5 block font-normal text-ink-2">{errors.speed}</span>}
        </h4>
        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-small sm:grid-cols-[max-content_1fr] sm:gap-y-2">
          {c.assumptions.map((a) => (
            <div key={a.what} className="flex flex-col gap-0.5 sm:contents">
              <dt className="text-ink-3">{a.what}</dt>
              <dd className="text-ink">
                {a.value}
                <span className="text-ink-3"> · {a.basis === 'published' ? 'published' : 'assumed'}</span>
                {a.source && <span className="mt-0.5 block text-caption leading-caption text-ink-3">Source: {a.source}</span>}
              </dd>
            </div>
          ))}
        </dl>
      </div>
      <p className="text-small leading-5 text-ink-2">
        {c.plan_note} {c.flown_note}
      </p>
    </Disclosure>
  )
}

function MoonPullRow({ pull }: { pull: NonNullable<TripDTO['moon_pull']> }) {
  return (
    <Disclosure title="Where the Moon’s pull wins" meta={`${formatValue(pull.equal_pull_km)} km from the Moon`}>
      <p className="text-body leading-6 text-ink-2">
        Closer than {formatValue(pull.equal_pull_km)} km to the Moon, the Moon pulls harder than Earth.
        {pull.t_equal_pull && ` This trip crossed that point ${dateTimeWords(Date.parse(pull.t_equal_pull))}.`}{' '}
        The Moon’s own sphere of influence, used to plan the trip, reaches {formatValue(pull.sphere_of_influence_km)} km.
      </p>
    </Disclosure>
  )
}
