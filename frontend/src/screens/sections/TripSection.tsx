import { api } from '../../lib/api/client'
import { API_BASE } from '../../lib/api/client'
import type { MissionDetail } from '../../lib/api/adapters'
import type { TripDTO } from '../../lib/api/lifecycle'
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
import { TripLegendItems, TripStrip, TripTable, tripStretches } from '../../components/lifecycle/TripStrip'
import { Disclosure } from '../../components/ui'

const TERMS = ['tripSunlight', 'tripHeard', 'tripShadow', 'tripUnheard']
const HOUR = 3_600_000

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

function TripAnswer({ trip, meta, missionId }: { trip: TripDTO; meta: Parameters<typeof Answer>[0]['meta'] & object; missionId: string }) {
  const t0 = Date.parse(trip.start)
  const t1 = Date.parse(trip.end)
  const hours = (t1 - t0) / HOUR
  const stretches = tripStretches(trip)
  const n = trip.numbers
  return (
    <>
      <Answer meta={meta}>
        The trip takes {formatValue(hours / 24)} days ({trip.source === 'flown' ? 'as flown' : 'as designed'}). It is in
        shadow for {quantityText(n.longest_shadow_h)} at most at a time, and out of contact for{' '}
        {quantityText(n.longest_unheard_h)} at most.
      </Answer>
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
        {trip.radiation && (
          <Disclosure title="Radiation on the way" meta="screening only">
            <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-body sm:grid-cols-[max-content_1fr]">
              <dt className="text-ink-3">Time in the radiation belts</dt>
              <dd className="text-ink">{quantityText(trip.radiation.belt_hours)}</dd>
              <dt className="text-ink-3">Protons above 10 MeV, all trip</dt>
              <dd className="text-ink">{quantityText(trip.radiation.fluence_gt10mev)}</dd>
              <dt className="text-ink-3">Dose from cosmic rays</dt>
              <dd className="text-ink">{quantityText(trip.radiation.gcr_dose_mgy_day)}</dd>
            </dl>
            <p className="text-small leading-5 text-ink-2">{trip.radiation.screening_note}</p>
            {trip.radiation.confirm_in.length > 0 && (
              <p className="text-small leading-5 text-ink-2">
                Confirm in {trip.radiation.confirm_in.join(', ')} before relying on it.
              </p>
            )}
          </Disclosure>
        )}
        <Disclosure title="Burns" meta={`${trip.burns.length}`}>
          <ol className="flex flex-col gap-2">
            {trip.burns.map((b, i) => (
              <li key={b.t} className="flex flex-wrap items-baseline gap-x-3 text-body">
                <span className="font-mono text-caption text-ink-3">{i + 1}</span>
                <span className="font-semibold text-ink">{b.name}</span>
                <span className="text-ink-2">{dateTimeWords(Date.parse(b.t))}</span>
                <span className="font-mono text-small text-ink">{quantityText(b.dv_m_s)}</span>
              </li>
            ))}
          </ol>
        </Disclosure>
        <Disclosure title="Where the Moon’s pull wins" meta={`${formatValue(trip.moon_pull.equal_pull_km)} km from the Moon`}>
          <p className="text-body leading-6 text-ink-2">
            Closer than {formatValue(trip.moon_pull.equal_pull_km)} km to the Moon, the Moon pulls harder than Earth.
            {trip.moon_pull.t_equal_pull && ` This trip crossed that point ${dateTimeWords(Date.parse(trip.moon_pull.t_equal_pull))}.`}{' '}
            The Moon’s own sphere of influence, used to plan the trip, reaches {formatValue(trip.moon_pull.sphere_of_influence_km)} km.
          </p>
        </Disclosure>
        <Disclosure title="Download the trip" meta="OEM, SPICE, spreadsheet">
          <p className="text-small leading-5 text-ink-2">The trajectory in the formats flight software and analysts use.</p>
          <ul className="flex flex-wrap gap-3">
            {(
              [
                ['oem', 'CCSDS orbit file (OEM)'],
                ['spk', 'SPICE kernel (SPK)'],
                ['csv', 'Spreadsheet (CSV)'],
              ] as const
            ).map(([f, label]) => (
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
        <HowSure meta={meta} />
        <SourcesRow meta={meta} />
      </Rows>
    </>
  )
}
