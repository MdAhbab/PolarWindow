import type { ContactBudgetDTO, LinkBudgetDTO, PassPointDTO, QuantityDTO, RateMarginDTO } from '../../lib/api/surface.types'
import { Disclosure } from '../ui'
import { num, quantityWords, utcWords } from './helpers'
import { ProvTag } from './parts'

/** "20 dBW (± 1)" with its provenance: a figure the budget ran on. */
function Figure({ label, q, digits }: { label: string; q: QuantityDTO; digits?: number }) {
  const w = quantityWords(q, digits)
  return (
    <div className="flex min-w-0 flex-col gap-0.5 border-t border-line pt-2.5">
      <dt className="text-caption leading-caption text-ink-2">{label}</dt>
      <dd className="flex flex-wrap items-baseline gap-x-1.5">
        <span className="font-mono text-body text-ink tabular-nums">{w.value}</span>
        <span className="text-small text-ink-2">{w.unit}</span>
      </dd>
      <dd className={`text-caption leading-caption ${w.marginIsReason ? 'text-ink-3' : 'font-mono text-ink-2 tabular-nums'}`}>{w.margin}</dd>
      <dd>
        <ProvTag p={w.provenance} />
      </dd>
    </div>
  )
}

/** A margin in dB with its sign, and its range, at one stated rate. */
export function marginWords(m: RateMarginDTO): string {
  const signed = (v: number) => `${v > 0 ? '+' : ''}${num(v, 1)}`
  const rate = `${num(m.rate_kbps.value ?? Number.NaN)} kbps`
  const v = m.margin_db.value
  if (v === null) return `${rate}: ${m.margin_db.missing_reason ?? 'no margin worked out'}`
  const lo = m.margin_db.lo
  const hi = m.margin_db.hi
  const range = typeof lo === 'number' && typeof hi === 'number' ? ` (range ${signed(lo)} to ${signed(hi)})` : ''
  return `${rate}: ${signed(v)} dB${range}`
}

function PointRow({ title, p }: { title: string; p: PassPointDTO }) {
  const rate = quantityWords(p.max_rate_kbps)
  const elev = p.elevation_deg.value
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <span className="text-caption leading-caption text-ink-2">
        {title}
        {elev !== null && <>, Earth station sees the lander at {num(elev, 1)}°</>}
      </span>
      <span className="flex flex-wrap items-baseline gap-x-2">
        <span className="font-mono text-body text-ink tabular-nums">
          up to {rate.value} {rate.unit}
        </span>
        <span className={`text-caption ${rate.marginIsReason ? 'text-ink-3' : 'font-mono text-ink-2 tabular-nums'}`}>{rate.margin}</span>
        <ProvTag p={rate.provenance} />
      </span>
      {p.margins.length > 0 && (
        <ul className="flex flex-col gap-0.5 font-mono text-caption leading-caption text-ink-2 tabular-nums">
          {p.margins.map((m, i) => (
            <li key={i}>Margin at {marginWords(m)}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** What the budget ran on, then each station's passes: the rate at the mask edge and at the peak, and the margin at every stated rate. */
function BudgetBody({ b, contact }: { b: LinkBudgetDTO; contact: ContactBudgetDTO }) {
  const name = (id: string) => contact.nodes.find((n) => n.id === id)?.name ?? id
  const isStation = (id: string) => contact.nodes.find((n) => n.id === id)?.kind === 'station'
  const budgeted = contact.links.filter((l) => l.passes && l.passes.length > 0 && (isStation(l.to) || isStation(l.from)))
  return (
    <>
      <p className="text-small leading-5 text-ink-2">{b.method}</p>
      <dl className="grid grid-cols-1 gap-x-5 gap-y-2 min-[420px]:grid-cols-2 lg:grid-cols-3">
        <div className="flex min-w-0 flex-col gap-0.5 border-t border-line pt-2.5">
          <dt className="text-caption leading-caption text-ink-2">Band</dt>
          <dd className="font-mono text-body text-ink">{b.band}</dd>
        </div>
        <Figure label="Frequency" q={b.frequency_mhz} />
        <Figure label="Lander EIRP" q={b.eirp_dbw} digits={1} />
        <Figure label="Required Eb/N0" q={b.required_ebn0_db} digits={1} />
        <Figure label="Margin kept over it" q={b.required_margin_db} digits={1} />
        <div className="flex min-w-0 flex-col gap-0.5 border-t border-line pt-2.5">
          <dt className="text-caption leading-caption text-ink-2">Stated data rates</dt>
          <dd className="font-mono text-body text-ink tabular-nums">
            {b.stated_rates_kbps.length ? b.stated_rates_kbps.map((r) => `${num(r.value ?? Number.NaN)} kbps`).join(', ') : 'none stated'}
          </dd>
          {b.stated_rates_kbps[0] && (
            <dd>
              <ProvTag p={b.stated_rates_kbps[0].provenance} />
            </dd>
          )}
        </div>
      </dl>

      <div className="flex flex-col gap-2">
        <h4 className="pw-eyebrow">Stations</h4>
        <ul className="flex flex-col divide-y divide-line border-y border-line">
          {b.stations.map((s) => {
            const g = quantityWords(s.gain_dbi, 1)
            const t = quantityWords(s.t_amw_k, 1)
            return (
              <li key={s.id} className="flex flex-col gap-1 py-2.5">
                <span className="text-body font-semibold text-ink">
                  {name(s.id)} <span className="font-normal text-ink-3">· {s.configuration}</span>
                </span>
                <span className="font-mono text-caption leading-caption text-ink-2 tabular-nums">
                  gain {g.value} {g.unit} ({g.margin}) · noise {t.value} {t.unit} ({t.margin})
                </span>
                <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-caption leading-caption text-ink-3">
                  <span>Handbook module {s.module}</span>
                  <ProvTag p={s.gain_dbi.provenance} />
                  {s.source_urls.map((u, i) => (
                    <a key={u} href={u} target="_blank" rel="noreferrer" className="text-earth underline underline-offset-2">
                      Source{s.source_urls.length > 1 ? ` ${i + 1}` : ''}
                    </a>
                  ))}
                </span>
              </li>
            )
          })}
        </ul>
        {b.stations_without_figures.length > 0 && (
          <p className="text-caption leading-caption text-ink-3">
            Left out, no published figures: {b.stations_without_figures.map(name).join(', ')}.
          </p>
        )}
      </div>

      {budgeted.map((l) => {
        const station = isStation(l.to) ? l.to : l.from
        return (
          <div key={`${l.from}-${l.to}`} className="flex flex-col gap-2">
            <h4 className="pw-eyebrow">Passes over {name(station)}</h4>
            <ol className="flex flex-col gap-3">
              {(l.passes ?? []).map((p, i) => {
                const st = l.stretches[i]
                return (
                  <li key={i} className="flex flex-col gap-2.5 rounded-md border border-line px-3 py-3">
                    <span className="text-small font-semibold text-ink">
                      Pass {i + 1}
                      {st && (
                        <span className="font-normal text-ink-2">
                          {' '}
                          · {st.open_start ? 'from before ' : ''}
                          {utcWords(Date.parse(st.start), true)} to {utcWords(Date.parse(st.end), true)}
                          {st.open_end ? ' or later' : ''} UTC
                        </span>
                      )}
                    </span>
                    <PointRow title="At the mask edge (the weaker end)" p={p.edge} />
                    <PointRow title="At the peak" p={p.peak} />
                  </li>
                )
              })}
            </ol>
          </div>
        )
      })}

      {b.not_modelled.length > 0 && (
        <div className="flex flex-col gap-1">
          <h4 className="pw-eyebrow">Not modelled</h4>
          <ul className="flex list-disc flex-col gap-1 pl-5 text-small leading-5 text-ink-2">
            {b.not_modelled.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </div>
      )}
    </>
  )
}

/**
 * The downlink budget on the Contact step (ADR-20). With no EIRP stated the
 * answer is line of sight only, and the service's note says so as it is.
 */
export function LinkBudgetRow({ contact }: { contact: ContactBudgetDTO }) {
  const b = contact.link_budget
  if (!b && !contact.link_budget_note) return null
  return (
    <Disclosure
      title="Downlink budget"
      meta={b ? `${b.band}, EIRP ${quantityWords(b.eirp_dbw, 1).value} dBW` : 'line of sight only'}
    >
      {contact.link_budget_note && <p className="text-body leading-6 text-ink-2">{contact.link_budget_note}</p>}
      {b ? (
        <BudgetBody b={b} contact={contact} />
      ) : (
        <p className="text-caption leading-caption text-ink-3">
          Stating the lander&apos;s EIRP in the project&apos;s radio figures turns the budget on: data rates and margins per pass appear here.
        </p>
      )}
    </Disclosure>
  )
}
