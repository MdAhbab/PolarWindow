import type { LifecycleMetaDTO, QuantityDTO, SpaceWeatherDTO } from '../../lib/api/lifecycle'
import type { ApiError } from '../../lib/api/client'
import { useSpaceWeather } from '../../lib/api/lifecycleQueries'
import { ageWords, formatValue, quantityText } from '../../lib/lifecycle/quantity'
import { dateTimeWords } from '../../lib/format'
import { Disclosure } from '../ui'

type Now = SpaceWeatherDTO['now']

const NUMBERS: { key: Exclude<keyof Now, 'xray_class' | 'xray_missing_reason' | 'alerts' | 'alerts_missing_reason'>; label: string; words: string }[] = [
  { key: 'kp', label: 'Geomagnetic activity (Kp, 0 to 9)', words: 'Kp' },
  { key: 'proton_10mev_pfu', label: 'Protons above 10 MeV', words: 'protons above 10 MeV at' },
  { key: 'proton_100mev_pfu', label: 'Protons above 100 MeV', words: 'above 100 MeV at' },
  { key: 'solar_wind_km_s', label: 'Solar wind speed', words: 'solar wind at' },
  { key: 'bz_nt', label: 'Magnetic field from the Sun, north–south (Bz)', words: 'Bz' },
]

const shown = (q: QuantityDTO) => q.value !== null

function alertWords(now: Now): string {
  if (now.alerts_missing_reason) return 'SWPC’s alerts of the last 24 hours are not shown here'
  const n = now.alerts.length
  return n === 0 ? 'no alerts in the last 24 hours' : `${n} alert${n === 1 ? '' : 's'} in the last 24 hours`
}

/** The answer: the readings shown now in one line, or why none is. */
export function spaceWeatherSentence(sw: SpaceWeatherDTO, meta: Pick<LifecycleMetaDTO, 'computed_at' | 'stale'>): string {
  const parts = NUMBERS.filter((n) => n.key !== 'proton_100mev_pfu' && n.key !== 'bz_nt' && shown(sw.now[n.key])).map(
    (n) => `${n.words} ${quantityText(sw.now[n.key])}`,
  )
  if (sw.now.xray_class) parts.splice(Math.min(2, parts.length), 0, `X-ray flares class ${sw.now.xray_class}`)
  if (!parts.length) {
    const at = Date.parse(meta.computed_at)
    return meta.stale && !Number.isNaN(at)
      ? `No reading is recent enough to show: the newest is from ${dateTimeWords(at)}. Each says why below.`
      : 'No reading has been recorded yet. Each says why below.'
  }
  const line = parts.join(', ')
  return `Now: ${line.charAt(0).toUpperCase()}${line.slice(1)}; ${alertWords(sw.now)}.`
}

/** NOAA's three-day outlook in one sentence, its numbers as issued. */
export function outlookSentence(o: SpaceWeatherDTO['outlook']): string | null {
  if (o.missing_reason) return o.missing_reason
  const parts: string[] = []
  if (o.s1_or_greater_pct?.length) {
    const pct = o.s1_or_greater_pct.map((p) => `${formatValue(p)}%`)
    const listed = pct.length > 1 ? `${pct.slice(0, -1).join(', ')} and ${pct[pct.length - 1]}` : pct[0]
    parts.push(`a ${listed} chance of a radiation storm (S1 or greater)${pct.length > 1 ? ', day by day' : ''}`)
  }
  if (o.kp_max_expected !== null) parts.push(`the largest Kp expected is ${formatValue(o.kp_max_expected)}`)
  if (!parts.length) return null
  const when = [o.days ? `for ${o.days}` : null, o.issued ? `issued ${dateTimeWords(Date.parse(o.issued))}` : null].filter(Boolean).join(', ')
  return `NOAA’s outlook${when ? ` ${when}` : ''}: ${parts.join('; ')}.`
}

/** How old a reading is, from the source it came from (matched by its address). */
export function readingAge(meta: Pick<LifecycleMetaDTO, 'sources'>, match: (url: string) => boolean): string | null {
  const s = meta.sources.find((x) => x.url && match(x.url))
  const t = s ? Date.parse(s.issued_at ?? s.fetched_at ?? '') : NaN
  return Number.isNaN(t) ? null : `as of ${ageWords(t)}`
}

function Reading({ q, age }: { q: QuantityDTO; age: string | null }) {
  if (!shown(q)) return <span className="text-ink-2">{q.missing_reason ?? 'Not available'}</span>
  return (
    <>
      {quantityText(q)}
      {age && <span className="text-small text-ink-3"> · {age}</span>}
    </>
  )
}

const SHOWN_EVENTS = 3

/** "3 newest of 133" when DONKI gave more than are shown; null when every one is shown. */
export function eventCountWords(listed: number, count: number | null): string | null {
  const shownN = Math.min(listed, SHOWN_EVENTS)
  const total = Math.max(count ?? listed, listed)
  return total > shownN ? `${shownN} newest of ${formatValue(total)}` : null
}

function EventList({
  title,
  items,
  count,
  empty,
}: {
  title: string
  items: { key: string; text: string; link: string | null }[]
  count: number | null
  empty: string
}) {
  const of = eventCountWords(items.length, count)
  return (
    <div className="flex flex-col gap-1">
      <h5 className="text-small font-semibold text-ink-2">
        {title}
        {of && <span className="font-normal text-ink-3"> · {of}</span>}
      </h5>
      {items.length ? (
        <ul className="flex flex-col gap-1">
          {items.slice(0, SHOWN_EVENTS).map((e) => (
            <li key={e.key} className="text-small leading-5 text-ink">
              {e.text}
              {e.link && (
                <>
                  {' · '}
                  <a href={e.link} target="_blank" rel="noreferrer">
                    record
                  </a>
                </>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-small text-ink-2">{empty}</p>
      )}
    </div>
  )
}

/** The alert list: SWPC's headlines, "None" only when the list is current and empty, or why it is not shown. */
function Alerts({ sw, meta }: { sw: SpaceWeatherDTO; meta: LifecycleMetaDTO }) {
  if (sw.now.alerts.length) return <>{sw.now.alerts.join('; ')}</>
  if (!sw.now.alerts_missing_reason) return <>None</>
  const url = meta.sources.find((s) => /\/alerts\.json$/.test(s.url ?? ''))?.url
  return (
    <span className="text-ink-2">
      {sw.now.alerts_missing_reason}
      {url && (
        <>
          {' '}
          <a href={url} target="_blank" rel="noreferrer" className="underline underline-offset-2">
            SWPC’s alerts
          </a>
        </>
      )}
    </span>
  )
}

const when = (t: string | null) => (t ? dateTimeWords(Date.parse(t)) : 'time not given')

/**
 * Space weather now (Launch): what the Sun is doing, as NOAA SWPC and NASA
 * DONKI report it (`GET /space-weather`, answered at once). The readings in a
 * sentence, then each with its age or why it is not shown, NOAA's outlook with
 * the forecast as issued, and DONKI's newest events. No dose here: doses are
 * in the Trip section.
 */
export function SpaceWeatherRow() {
  const q = useSpaceWeather(true)
  const sw = q.data?.data
  const meta = q.data?.meta
  const kp = sw?.now.kp
  const summary = !sw
    ? undefined
    : `${kp && shown(kp) ? `Kp ${quantityText(kp)}` : 'no current reading'}${
        sw.now.alerts.length ? `, ${sw.now.alerts.length} alert${sw.now.alerts.length === 1 ? '' : 's'}` : ''
      }`
  return (
    <Disclosure title="Space weather now" meta={summary}>
      {q.isPending ? (
        <p className="text-small text-ink-3">Reading the space weather…</p>
      ) : !sw || !meta ? (
        <p className="text-body text-ink-2">
          The space weather could not be read: {(q.error as ApiError | null)?.title ?? 'the service did not answer'}.
        </p>
      ) : (
        <>
          <p className="text-body leading-6 text-ink">{spaceWeatherSentence(sw, meta)}</p>
          <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-body sm:grid-cols-[max-content_1fr]">
            {NUMBERS.map((n) => (
              <div key={n.key} className="contents">
                <dt className="text-ink-3">{n.label}</dt>
                <dd className="text-ink">
                  <Reading q={sw.now[n.key]} age={readingAge(meta, (u) => u === sw.now[n.key].source)} />
                </dd>
              </div>
            ))}
            <dt className="text-ink-3">X-ray flares (class)</dt>
            <dd className="text-ink">
              {sw.now.xray_class ?? <span className="text-ink-2">{sw.now.xray_missing_reason ?? 'Not reported'}</span>}
              {sw.now.xray_class && readingAge(meta, (u) => /xray/i.test(u)) && (
                <span className="text-small text-ink-3"> · {readingAge(meta, (u) => /xray/i.test(u))}</span>
              )}
            </dd>
            <dt className="text-ink-3">Alerts in the last 24 hours</dt>
            <dd className="text-ink">
              <Alerts sw={sw} meta={meta} />
            </dd>
          </dl>
          <div className="flex flex-col gap-1.5">
            <h4 className="text-small font-semibold text-ink">The next three days</h4>
            <p className="text-small leading-5 text-ink-2">{outlookSentence(sw.outlook) ?? 'NOAA’s outlook gives no numbers.'}</p>
            {sw.outlook.text && (
              <details>
                <summary className="cursor-pointer text-small font-semibold text-ink">NOAA’s forecast as issued</summary>
                <pre
                  tabIndex={0}
                  role="region"
                  aria-label="NOAA’s three-day forecast as issued"
                  className="mt-2 max-h-80 overflow-auto rounded-control bg-inset p-3 font-mono text-caption leading-5 whitespace-pre-wrap text-ink">
                  {sw.outlook.text}
                </pre>
              </details>
            )}
          </div>
          <div className="flex flex-col gap-2">
            <h4 className="text-small font-semibold text-ink">
              Newest events on the Sun{sw.donki.days ? `, last ${sw.donki.days} days` : ''} (NASA DONKI)
            </h4>
            {sw.donki.missing_reason ? (
              <p className="text-small leading-5 text-ink-2">{sw.donki.missing_reason}</p>
            ) : (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                <EventList
                  title="Clouds thrown off the Sun (coronal mass ejections)"
                  empty="None listed."
                  count={sw.donki.counts.cme}
                  items={sw.donki.cme.map((c) => ({
                    key: c.id,
                    text: `${when(c.start)}${c.speed_m_s !== null ? `, ${formatValue(Math.round(c.speed_m_s / 1000))} km/s` : ''}${
                      c.earth_arrival_estimates?.length
                        ? `; reaching Earth ${c.earth_arrival_estimates.map((t) => dateTimeWords(Date.parse(t))).join(' or ')}`
                        : '; no Earth arrival estimated'
                    }`,
                    link: c.link,
                  }))}
                />
                <EventList
                  title="Flares"
                  empty="None listed."
                  count={sw.donki.counts.flares}
                  items={sw.donki.flares.map((f) => ({ key: f.id, text: `${f.class ?? 'Class not given'}, peak ${when(f.peak)}`, link: f.link }))}
                />
                <EventList
                  title="Solar particle events"
                  empty="None listed."
                  count={sw.donki.counts.sep}
                  items={sw.donki.sep.map((e) => ({ key: e.id, text: when(e.time), link: e.link }))}
                />
              </div>
            )}
          </div>
          <p className="text-caption leading-caption text-ink-3">{sw.note}</p>
        </>
      )}
    </Disclosure>
  )
}
