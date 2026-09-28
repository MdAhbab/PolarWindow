import type { QuantityDTO, RadiationDTO } from '../../lib/api/lifecycle'
import { formatValue, hostWords, quantityText } from '../../lib/lifecycle/quantity'
import { dateTimeWords } from '../../lib/format'
import { Disclosure } from '../ui'

/**
 * A screening figure as a table cell: the value with its ×/÷ factor or ±, or
 * "none counted" for a lower bound of zero (the climb out is not in NASA's
 * reconstruction, so the belts are not counted at all).
 */
export function screeningFigure(q: QuantityDTO): string {
  if (q.value === null) return q.missing_reason ?? 'Not worked out'
  if (q.value === 0 && q.open) return 'none counted'
  return quantityText(q)
}

/** A past event's figure in the table, its unit in the column head. */
function eventFigure(q: QuantityDTO): string {
  return q.value === null ? (q.missing_reason ?? 'Not given') : formatValue(q.value)
}

/** The row's opening sentence: the belts, then cosmic rays on the way and at the landing spot. */
export function radiationSentence(r: RadiationDTO): string {
  const b = r.belt_hours
  const belts =
    b.value === null
      ? 'The time in the radiation belts is not worked out'
      : b.value === 0
        ? b.open
          ? 'No time in the radiation belts is counted (the climb out is not in NASA’s reconstruction)'
          : 'It does not pass through the radiation belts'
        : `${b.open ? 'At least ' : ''}${quantityText({ ...b, open: false })} in the radiation belts over ${r.belt_passes} pass${r.belt_passes === 1 ? '' : 'es'}`
  const surface = r.surface ? ` and ${quantityText(r.surface.gcr_dose_mgy_day)} at the landing spot` : ''
  return `${belts}. Cosmic rays give ${quantityText(r.gcr_dose_mgy_day)} on the way${surface}, before any shielding.`
}

/** The measures of the screening, each with how it was worked out. */
function measures(r: RadiationDTO): { label: string; figure: string; how: string | null }[] {
  const rows = [
    {
      label: 'Time in the radiation belts',
      figure: `${screeningFigure(r.belt_hours)}${r.belt_hours.value ? `, ${r.belt_passes} pass${r.belt_passes === 1 ? '' : 'es'}` : ''}`,
      how: r.belt_hours.source,
    },
    { label: 'Electrons above 1 MeV, whole trip', figure: screeningFigure(r.electron_fluence_gt1mev), how: r.electron_fluence_gt1mev.source },
    { label: 'Protons above 10 MeV in the belts, whole trip', figure: screeningFigure(r.fluence_gt10mev), how: r.fluence_gt10mev.source },
    { label: 'Cosmic-ray dose on the way', figure: screeningFigure(r.gcr_dose_mgy_day), how: r.gcr_dose_mgy_day.source },
  ]
  if (r.surface) {
    const sky = r.surface.open_sky.value
    rows.push({
      label: 'Cosmic-ray dose at the landing spot',
      figure: `${screeningFigure(r.surface.gcr_dose_mgy_day)}${sky !== null ? ` (${Math.round(sky * 100)}% of the sky open)` : ''}`,
      how: [r.surface.gcr_dose_mgy_day.source, r.surface.open_sky.no_margin_reason].filter(Boolean).join(' '),
    })
  }
  return rows
}

/**
 * Radiation on the way (Trip): a screening estimate, never a design figure.
 * The sentence first, then the numbers as a table, the Sun's particle events
 * during the trip, three past large events for comparison, and how each was
 * worked out. Where to confirm is said once.
 */
export function RadiationRow({ r, note }: { r: RadiationDTO | null; note: string | null | undefined }) {
  if (!r) {
    return (
      <Disclosure title="Radiation on the way" meta="not worked out">
        <p className="text-body leading-6 text-ink-2">{note ?? 'No radiation screening is worked out for this trip.'}</p>
      </Disclosure>
    )
  }
  const rows = measures(r)
  // The screening note may already name where to confirm; say it only once.
  const unnamed = r.confirm_in.filter((c) => !r.screening_note.includes(c.split(' ')[0]))
  const cell = 'px-3 py-2 text-small text-ink-2 align-top'
  const num = `${cell} text-right font-mono tnum whitespace-nowrap text-ink`
  const head = 'px-3 py-2.5 text-tag font-semibold tracking-caps-md text-ink-3 uppercase align-bottom'
  return (
    <Disclosure title="Radiation on the way" meta="screening only">
      <p className="text-body leading-6 text-ink">{radiationSentence(r)}</p>
      <p className="text-small leading-5 text-ink-2">
        {r.screening_note}
        {unnamed.length > 0 && ` Confirm in ${unnamed.join(', ')} before relying on it.`}
      </p>
      <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-body sm:grid-cols-[max-content_1fr]">
        {rows.map((m) => (
          <div key={m.label} className="contents">
            <dt className="text-ink-3">{m.label}</dt>
            <dd className="text-ink">{m.figure}</dd>
          </div>
        ))}
      </dl>
      {!r.surface && r.surface_note && <p className="text-small leading-5 text-ink-2">{r.surface_note}</p>}
      <div className="flex flex-col gap-1.5">
        <h4 className="text-small font-semibold text-ink">Solar particle events during the trip</h4>
        <p className="text-small leading-5 text-ink-2">{r.sep_note}</p>
        {r.sep_events.length > 0 && (
          <ul className="flex flex-col gap-1">
            {r.sep_events.map((e) => (
              <li key={e.t} className="text-small text-ink">
                {dateTimeWords(Date.parse(e.t))} ·{' '}
                <a href={e.link} target="_blank" rel="noreferrer">
                  NASA DONKI record
                </a>
              </li>
            ))}
          </ul>
        )}
      </div>
      {r.scenarios.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <h4 className="text-small font-semibold text-ink">Past large events, for comparison</h4>
          <p className="text-small leading-5 text-ink-2">What each gave near Earth, outside its magnetic field, over the event.</p>
          <table className="w-full border-collapse border border-line text-left">
              <caption className="sr-only">Protons above 10 and above 30 MeV per square centimetre in each past event.</caption>
              <thead>
                <tr className="bg-inset">
                  <th scope="col" className={head}>Event</th>
                  <th scope="col" className={`${head} text-right`}>Protons above 10 MeV, per cm²</th>
                  <th scope="col" className={`${head} text-right`}>Above 30 MeV, per cm²</th>
                </tr>
              </thead>
              <tbody>
                {r.scenarios.map((s) => (
                  <tr key={s.id} className="border-t border-line">
                    <th scope="row" className={`${cell} font-normal`}>
                      <span className="block font-semibold text-ink">{s.name}</span>
                      <a href={s.source_url} target="_blank" rel="noreferrer">
                        the measurements ({hostWords(s.source_url)})
                      </a>
                    </th>
                    <td className={num}>{eventFigure(s.fluence_gt10mev)}</td>
                    <td className={num}>{eventFigure(s.fluence_gt30mev)}</td>
                  </tr>
                ))}
              </tbody>
          </table>
        </div>
      )}
      <details className="group flex flex-col gap-2">
        <summary className="cursor-pointer text-small font-semibold text-ink">How each was worked out</summary>
        <dl className="mt-2 flex flex-col gap-2 text-small leading-5">
          {[
            ...rows.filter((m) => m.how).map((m) => ({ label: m.label, how: m.how as string })),
            ...r.scenarios.map((s) => ({ label: s.name, how: s.fluence_gt10mev.no_margin_reason ?? '' })).filter((s) => s.how),
          ].map((m) => (
            <div key={m.label}>
              <dt className="font-semibold text-ink-2">{m.label}</dt>
              <dd className="text-ink-2">{m.how}</dd>
            </div>
          ))}
        </dl>
      </details>
    </Disclosure>
  )
}
