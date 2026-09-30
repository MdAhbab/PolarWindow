import { useState } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { ApiError, api, type RoverOptions } from '../../lib/api/client'
import type { MissionDetail } from '../../lib/api/adapters'
import type { ContactDTO, LifecycleMetaDTO, OrbiterDTO, QuantityDTO, RelayOrbitDTO, RoverSightDTO } from '../../lib/api/lifecycle'
import { useHistory, useLifecycleWrite, useSection, useSectionStatus } from '../../lib/api/lifecycleQueries'
import { useSnapshotActive } from '../../lib/api/snapshot'
import { useWindowParams } from '../../lib/mission'
import { useMission as useStore } from '../../lib/store'
import { hasSite } from '../../lib/sites'
import { dateTimeWords, msFromModelH, windowLine } from '../../lib/format'
import { ageWords, formatValue, quantityText, quantityView } from '../../lib/lifecycle/quantity'
import { NumberRow, QuantityTile } from '../../components/lifecycle/QuantityTile'
import { Answer, ChartPanel, HowSure, Legend, Rows, SectionLayout, SectionStates, SourcesRow, WorkingPanel } from '../../components/lifecycle/Section'
import { ContactChart, ContactTable, contactRows, relayState } from '../../components/lifecycle/ContactChart'
import { Field, FormSheet, HistoryList, Select, TextInput } from '../../components/lifecycle/Forms'
import { WindowPicker } from '../../components/WindowPicker'
import { Button, Disclosure } from '../../components/ui'
import { ViewshedPanel, roverSentence } from '../../components/lifecycle/RoverSight'
import { RelayCompare } from '../../components/lifecycle/RelayCompare'
import { RoverInputs } from '../../components/lifecycle/RoverInputs'
import { anyGiven, plainReason } from '../../lib/lifecycle/roverInputs'
import { PlanDownload } from '../../components/lifecycle/PlanDownload'
import { Icon } from '../../components/Icon'
import { useCanWrite } from './ReadySection'

const TERMS = ['stationHears', 'viaRelay', 'contactUnheard', 'messageWait']

/**
 * Contact (design-lifecycle.md §4): how often the lander can talk to Earth,
 * through ground stations and, if they fly as planned, relays. Over the same
 * dates as Landing, so the two answers agree.
 */
export function ContactSection({ mission: m }: { mission: MissionDetail }) {
  const w = useWindowParams()
  // Relays added to compare (catalogue ids, at most three), for this mission only.
  const [pick, setPick] = useState<{ mission: string; ids: string[] }>({ mission: m.id, ids: [] })
  const added = pick.mission === m.id ? pick.ids : []
  const view = useSection<ContactDTO>(
    'contact',
    m.id,
    (signal) => api.contact(m.id, { start: w.start, end: w.end, relay: added }, signal),
    [w.start, w.end, ...added],
  )
  const status = useSectionStatus(m.id, 'contact')
  return (
    <SectionLayout question="How often can the lander talk to Earth?">
      <SectionStates view={view} terms={TERMS} status={status}>
        {({ data, meta }) => (
          <ContactAnswer
            contact={data}
            meta={meta}
            mission={m}
            added={added}
            onAdded={(ids) => setPick({ mission: m.id, ids: [...ids].sort() })}
            // The dates the answer says it covers; the asked-for ones if it does not say.
            start={Date.parse(data.start ?? w.start)}
            end={Date.parse(data.end ?? w.end)}
            // Say how the dates were chosen only when they are not the ones asked for.
            datesNote={servedOtherDates(data, w) ? data.window_note : null}
          />
        )}
      </SectionStates>
    </SectionLayout>
  )
}

/** A number given as a lo–hi range: with a relay, one that counts the relay if it flies as planned. */
const isRange = (q: QuantityDTO) => q.lo !== null && q.hi !== null

/**
 * Each relay with its launch status: `state` in words with a glyph (the
 * catalogue's status, else its node's); `launch` the served status line (its
 * launch plan), or the node's note.
 */
export function relayList(c: ContactDTO) {
  return c.relays.map((r) => {
    const node = c.nodes.find((n) => n.id === r.id)
    return { ...r, operator: node?.operator ?? null, state: relayState(c, r.id), launch: r.status || node?.launch_note || null }
  })
}

/** A relay's orbit in plain words, each figure with where it comes from. */
const ORBIT_WORDS: [keyof RelayOrbitDTO, string][] = [
  ['periapsis_km', 'Lowest point above the surface'],
  ['apoapsis_km', 'Highest point above the surface'],
  ['inclination_deg', 'Tilt to the Moon’s equator'],
  ['arg_periapsis_deg', 'Where the highest point sits (about 90° is over the south pole)'],
  ['period_h', 'One orbit takes'],
]

export function orbitWords(q: QuantityDTO): string {
  const w = numberWords(q)
  if (q.provenance === 'assumed' && !w.startsWith('Not worked out')) return `${w}, assumed`
  if (q.provenance === 'published' && !w.startsWith('Not worked out')) return `${w}, published`
  return w
}

/**
 * The answer in words (design-lifecycle.md, Contact): what a ground station
 * hears, the time through a relay as a range with its launch status beside it
 * and what that adds to direct contact,
 * and the longest time without contact, saying when that counts the relay.
 */
export function contactAnswer(c: ContactDTO): string {
  const n = c.numbers
  const relays = relayList(c)
  const heardThroughout = n.longest_unheard_h.value === 0
  const out = [
    heardThroughout
      ? `A ground station can hear it for all ${quantityText(n.station_hears_h)} of these dates.`
      : `A ground station can hear it for ${quantityText(n.station_hears_h)} over these dates.`,
  ]
  const one = relays.length === 1 ? relays[0] : null
  const named = one ? `${one.name}${one.state ? ` (${one.state.words.toLowerCase()})` : ''}` : null
  if (relays.length && isRange(n.via_relay_h)) {
    out.push(
      one
        ? `Through ${named} it could reach Earth for ${quantityText(n.via_relay_h)}, if it flies as planned${
            !isRange(one.adds_h) ? '' : one.adds_h.hi === 0 ? '; it adds no time to direct contact' : `; that adds ${quantityText(one.adds_h)} to direct contact`
          }.`
        : `Through a relay it could reach Earth for ${quantityText(n.via_relay_h)}, if they fly as planned.`,
    )
  } else if (relays.length) {
    out.push(
      one
        ? `${named} could relay for it, but time through it is not worked out yet.`
        : `${relays.map((r) => r.name).join(' and ')} could relay for it, but time through them is not worked out yet.`,
    )
  }
  if (!heardThroughout) {
    const withRelay = relays.length > 0 && isRange(n.longest_unheard_h)
    const direct = c.direct_only?.longest_unheard_h
    out.push(
      withRelay && direct
        ? `The longest time without contact is ${quantityText(direct)} directly, or ${quantityText(n.longest_unheard_h)} with the relay, if it flies as planned.`
        : `The longest time without contact is ${quantityText(n.longest_unheard_h)}${withRelay ? ' with the relay, if it flies as planned' : ''}.`,
    )
  }
  return out.join(' ')
}

/** An orbiter's passes in words: how many, time in view, the longest pass and the longest wait between passes. */
export function orbiterWords(o: OrbiterDTO): string {
  const passes = `${o.pass_count} pass${o.pass_count === 1 ? '' : 'es'} over these dates`
  // No trajectory for these dates: not known, which is not the same as no pass.
  if (quantityView(o.in_view_h).kind === 'missing') return `Not known: ${o.in_view_h.missing_reason ?? 'no trajectory is recorded for these dates.'}`
  if (!o.pass_count) return 'No pass over these dates.'
  return `${passes}, ${quantityText(o.in_view_h)} in view in all; the longest pass ${quantityText(o.longest_pass_min)}, the longest wait between passes ${quantityText(o.longest_gap_h)}.`
}

/** Says so when the recorded trajectory covers only part of the dates. */
export function coveredWords(o: OrbiterDTO, start: number, end: number): string | null {
  if (!o.covered) return null
  const a = Date.parse(o.covered.start)
  const b = Date.parse(o.covered.end)
  if (a <= start + 60_000 && b >= end - 60_000) return null
  return `Its recorded trajectory covers ${dateTimeWords(a)} to ${dateTimeWords(b)} only; passes outside that are not known.`
}

/** A number for a list: the figure, or "Not worked out: {reason}". */
export function numberWords(q: QuantityDTO, rangeNote?: string): string {
  const v = quantityView(q)
  if (v.kind === 'missing') return `Not worked out: ${v.missingReason}`
  return v.kind === 'range' && rangeNote ? `${v.sentence}, ${rangeNote}` : v.sentence
}

/** True when the answer covers dates other than the ones asked for. */
function servedOtherDates(c: Pick<ContactDTO, 'start' | 'end'>, asked: { start: string; end: string }): boolean {
  const differs = (served: string | undefined, want: string) => served !== undefined && Date.parse(served) !== Date.parse(want)
  return differs(c.start, asked.start) || differs(c.end, asked.end)
}

function ContactAnswer({
  contact,
  meta,
  mission: m,
  added,
  onAdded,
  start,
  end,
  datesNote,
}: {
  contact: ContactDTO
  meta: LifecycleMetaDTO
  mission: MissionDetail
  /** The relays this answer was asked to compare, and how to ask for others. */
  added: string[]
  onAdded: (ids: string[]) => void
  start: number
  end: number
  datesNote?: string | null
}) {
  const offline = useSnapshotActive()
  const hours = (end - start) / 3_600_000
  const n = contact.numbers
  const rows = contactRows(contact)
  const planned = rows.some((r) => r.planned)
  const { windowStartH, windowHours } = useStore(useShallow((s) => ({ windowStartH: s.windowStartH, windowHours: s.windowHours })))
  const relays = relayList(contact)
  const orbiters = contact.orbiters ?? []
  // A wait that counts a planned relay is a range, and says so.
  const relayNote = (q: QuantityDTO, direct?: QuantityDTO) =>
    relays.length && isRange(q) ? `with the relay, if it flies as planned${direct ? `; ${quantityText(direct)} directly` : ''}` : undefined
  return (
    <>
      <Answer meta={meta}>{contactAnswer(contact)}</Answer>
      <NumberRow>
        <QuantityTile term="stationHears" q={n.station_hears_h} tone="earth" icon="earth" scale={hours} />
        <QuantityTile
          term="viaRelay"
          q={
            contact.relays.length || n.via_relay_h.missing_reason
              ? n.via_relay_h
              : { ...n.via_relay_h, value: null, lo: null, hi: null, missing_reason: 'No relay serves this site.' }
          }
          tone="earth"
          scale={hours}
          note={contact.relays.length ? 'if it flies as planned' : undefined}
        />
        <QuantityTile term="contactUnheard" q={n.longest_unheard_h} scale={hours} note={relayNote(n.longest_unheard_h, contact.direct_only?.longest_unheard_h)} />
        <QuantityTile term="messageWait" q={n.longest_message_wait_min} note={relayNote(n.longest_message_wait_min, contact.direct_only?.longest_message_wait_min)} />
      </NumberRow>
      <ChartPanel
        title={`Who can hear the lander, ${windowLine(start, hours)}`}
        chart={<ContactChart contact={contact} rows={rows} start={start} end={end} />}
        legend={
          <Legend
            items={[
              { swatch: <span className="h-3 w-5 bg-earth-fill" />, label: 'Can hear the lander' },
              ...(planned ? [{ swatch: <span className="hatch-uncertain h-3 w-5 border border-uncertain" />, label: 'A range: if it flies as planned' }] : []),
              ...(rows.some((r) => r.orbiter) ? [{ swatch: <span className="h-3 w-5 border border-dashed border-earth" />, label: 'Could see the lander (an orbiter, not a relay)' }] : []),
              ...(rows.some((r) => r.noData?.length) ? [{ swatch: <span className="h-3 w-5 border border-dashed border-line-strong" />, label: 'No trajectory recorded' }] : []),
              ...(contact.bookings.length ? [{ swatch: <span className="h-3 w-5 border-2 border-ink" />, label: 'Booked pass' }] : []),
            ]}
          />
        }
        table={<ContactTable contact={contact} rows={rows} />}
      />
      {datesNote && <p className="-mt-3 text-caption leading-caption text-ink-3">{datesNote}</p>}
      <Rows
        about={
          <>
            <HowSure meta={meta}>
              {contact.link_budget_note && <p className="text-body leading-6 text-ink-2">{contact.link_budget_note}</p>}
            </HowSure>
            <SourcesRow meta={meta} />
          </>
        }
      >
        {relays.length > 0 && (
          <Disclosure title="Relays" meta={relays.map((r) => (r.state ? `${r.name} · ${r.state.words.toLowerCase()}` : r.name)).join(', ')}>
            {contact.relay_note && <p className="text-body text-ink-2">{contact.relay_note}</p>}
            <ul className="flex flex-col divide-y divide-line border-y border-line">
              {relays.map((r) => (
                <li key={r.id} className="flex flex-col gap-0.5 py-2.5">
                  <span className="text-body font-semibold text-ink">
                    {r.name}
                    {r.operator && <span className="font-normal text-ink-3"> · {r.operator}</span>}
                  </span>
                  <span className="text-small text-ink">
                    {r.state && (
                      <>
                        <span aria-hidden="true">{r.state.glyph} </span>
                        {r.state.words}.{' '}
                      </>
                    )}
                    {r.launch}
                  </span>
                  {r.for_this_mission === false && <span className="text-small text-ink-2">Added to compare: not planned for this mission.</span>}
                  <span className="text-small text-ink-2">
                    {isRange(r.adds_h)
                      ? `${r.adds_h.hi === 0 ? 'Adds no time to direct contact' : `Adds ${quantityText(r.adds_h)} to direct contact`}${
                          r.via_h && isRange(r.via_h) ? `, ${quantityText(r.via_h)} in all through it` : ''
                        }, if it flies as planned.`
                      : `Time through it: ${numberWords(r.adds_h).replace(/^Not worked out: /, 'not worked out. ')}`}
                  </span>
                  {r.orbit && (
                    <dl className="mt-1.5 grid grid-cols-1 gap-x-6 gap-y-1 text-small sm:grid-cols-[max-content_1fr]">
                      {ORBIT_WORDS.map(([k, label]) => (
                        <div key={k} className="contents">
                          <dt className="text-ink-3">{label}</dt>
                          <dd className="text-ink">{orbitWords(r.orbit![k])}</dd>
                        </div>
                      ))}
                    </dl>
                  )}
                  {r.orbit_note && <span className="text-small text-ink-2">{r.orbit_note}</span>}
                  {r.sweep_note && <span className="text-small text-ink-2">{r.sweep_note}</span>}
                </li>
              ))}
            </ul>
          </Disclosure>
        )}
        {!offline && (
          <RelayCompare own={contact.relays.filter((r) => r.for_this_mission !== false).map((r) => r.id)} applied={added} onApply={onAdded} />
        )}
        {orbiters.length > 0 && (
          <Disclosure title="Orbiters that could see the lander" meta={orbiters.map((o) => o.name).join(', ')}>
            <p className="text-body text-ink-2">
              {contact.orbiters_note ??
                'These orbiters already fly over the Moon and could see the lander. None is a relay for it: no agreement carries its data, so they count in no number above.'}
            </p>
            <ul className="flex flex-col divide-y divide-line border-y border-line">
              {orbiters.map((o) => (
                <li key={o.id} className="flex flex-col gap-0.5 py-2.5">
                  <span className="text-body font-semibold text-ink">
                    {o.name}
                    {o.operator && <span className="font-normal text-ink-3"> · {o.operator}</span>}
                  </span>
                  <span className="text-small text-ink">{orbiterWords(o)}</span>
                  {coveredWords(o, start, end) && <span className="text-small text-ink-2">{coveredWords(o, start, end)}</span>}
                  {o.note !== contact.orbiters_note && <span className="text-small text-ink-2">{o.note}</span>}
                  {o.source && (
                    <span className="text-small text-ink-3">
                      {o.source.url ? (
                        <a href={o.source.url} className="text-ink-2 underline">
                          {o.source.name}
                        </a>
                      ) : (
                        o.source.name
                      )}
                      {o.source.fetched_at ? `, fetched ${ageWords(Date.parse(o.source.fetched_at))}` : ''}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </Disclosure>
        )}
        <BookingsRow contact={contact} missionId={m.id} />
        <RoverRow mission={m} />
        <Disclosure title="More numbers">
          <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-body sm:grid-cols-[max-content_1fr]">
            <dt className="text-ink-3">Time in contact with Earth (Earth above the skyline)</dt>
            <dd className="text-ink">{numberWords(n.direct_h)}</dd>
            <dt className="text-ink-3">In contact either way, directly or through a relay</dt>
            <dd className="text-ink">{numberWords(n.either_h, 'if the relay flies as planned')}</dd>
            {contact.direct_only && (
              <>
                <dt className="text-ink-3">Longest time without contact, directly</dt>
                <dd className="text-ink">{numberWords(contact.direct_only.longest_unheard_h)}</dd>
                <dt className="text-ink-3">Longest message wait, directly</dt>
                <dd className="text-ink">{numberWords(contact.direct_only.longest_message_wait_min)}</dd>
              </>
            )}
            <dt className="text-ink-3">Dark and out of contact at once</dt>
            <dd className="text-ink">{numberWords(n.dark_and_unheard_h, 'with the relay, if it flies as planned')}</dd>
          </dl>
        </Disclosure>
        <PlanDownload missionId={m.id} start={start} end={end} relays={contact.relays} />
        {m.siteId && hasSite(m.siteId) && (
          <Disclosure title="Change the dates" meta={windowLine(msFromModelH(windowStartH), windowHours)}>
            <p className="text-small text-ink-2">The same dates as Landing: changing them here changes them there.</p>
            <WindowPicker
              siteId={m.siteId}
              missionWindow={
                m.surfaceWindow.startIso && m.surfaceWindow.endIso
                  ? { startMs: Date.parse(m.surfaceWindow.startIso), endMs: Date.parse(m.surfaceWindow.endIso) }
                  : null
              }
            />
          </Disclosure>
        )}
      </Rows>
    </>
  )
}

/** Ground-station passes the team has booked (ADR-16): entered, audited, and they take priority. */
function BookingsRow({ contact, missionId }: { contact: ContactDTO; missionId: string }) {
  const canWrite = useCanWrite()
  const [open, setOpen] = useState(false)
  const stations = contact.nodes.filter((n) => n.kind === 'station')
  const [station, setStation] = useState(stations[0]?.id ?? '')
  const [startAt, setStartAt] = useState('')
  const [endAt, setEndAt] = useState('')
  const [err, setErr] = useState<string | undefined>()
  const history = useHistory('booking', open ? missionId : null)
  const write = useLifecycleWrite((b: Parameters<typeof api.bookPass>[1]) => api.bookPass(missionId, b))
  const name = (id: string) => contact.nodes.find((n) => n.id === id)?.name ?? id
  return (
    <Disclosure title="Booked ground-station passes" meta={String(contact.bookings.length)}>
      {contact.bookings.length ? (
        <ul className="flex flex-col divide-y divide-line border-y border-line">
          {contact.bookings.map((b) => (
            <li key={b.station + b.start} className="flex flex-wrap items-baseline justify-between gap-x-4 py-2.5">
              <span className="text-body text-ink">{name(b.station)}</span>
              <span className="text-small text-ink-2">
                {dateTimeWords(Date.parse(b.start))} to {dateTimeWords(Date.parse(b.end))} · booked by {b.entered_by}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-body text-ink-2">No passes booked. The chart shows when a station can hear the lander, not when it is scheduled.</p>
      )}
      {canWrite && stations.length > 0 && (
        <div>
          <Button onClick={() => setOpen(true)}>
            <Icon name="plus" size={16} />
            Add a booked pass
          </Button>
        </div>
      )}
      <FormSheet
        open={open}
        onClose={() => setOpen(false)}
        title="Add a booked pass"
        intro="A pass the station has confirmed. Times in UTC."
        saving={write.isPending}
        error={write.error}
        history={<HistoryList entries={history.data} pending={history.isPending} error={history.error} />}
        onSave={async () => {
          const a = Date.parse(`${startAt}Z`)
          const b = Date.parse(`${endAt}Z`)
          if (!station || Number.isNaN(a) || Number.isNaN(b) || b <= a) {
            setErr('Give a start and an end, the end after the start.')
            return false
          }
          setErr(undefined)
          try {
            await write.mutateAsync({ station, start: new Date(a).toISOString(), end: new Date(b).toISOString() })
            return true
          } catch {
            return false
          }
        }}
      >
        <Field label="Ground station">
          {(p) => <Select {...p} value={station} onChange={(e) => setStation(e.target.value)} options={stations.map((s) => ({ value: s.id, label: s.name }))} />}
        </Field>
        <Field label="Start (UTC)" error={err}>
          {(p) => <TextInput {...p} type="datetime-local" value={startAt} onChange={(e) => setStartAt(e.target.value)} />}
        </Field>
        <Field label="End (UTC)">{(p) => <TextInput {...p} type="datetime-local" value={endAt} onChange={(e) => setEndAt(e.target.value)} />}</Field>
      </FormSheet>
    </Disclosure>
  )
}

/**
 * Whether a rover stays in sight of the lander (asked for when the row
 * opens): the answer first, then the viewshed as a map with its table twin.
 * Shown only for a mission that carries a rover.
 */
function RoverRow({ mission: m }: { mission: MissionDetail }) {
  const [open, setOpen] = useState(false)
  const [roverId, setRoverId] = useState(m.rovers[0]?.id)
  // The values the team gave for how far out, the antennas and the radio; what is not given is assumed.
  const [given, setGiven] = useState<RoverOptions>({})
  const view = useSection<RoverSightDTO>(
    'rover',
    m.id,
    (signal) => api.rover(m.id, roverId, signal, given),
    [roverId, given.radius_m, given.lander_antenna_m, given.rover_antenna_m, given.freq_mhz],
    open,
  )
  if (!m.rovers.length) return null
  const rover = m.rovers.find((r) => r.id === roverId) ?? m.rovers[0]
  return (
    <Disclosure title="Rover and lander line of sight" meta={m.rovers.map((r) => r.name).join(', ')} onOpen={() => setOpen(true)}>
      {m.rovers.length > 1 && (
        <Field label="Rover">
          {(p) => <Select {...p} value={rover.id} onChange={(e) => setRoverId(e.target.value)} options={m.rovers.map((r) => ({ value: r.id, label: r.name }))} />}
        </Field>
      )}
      {view.status === 'pending' ? (
        <p className="text-small text-ink-3">Loading…</p>
      ) : view.status === 'working' ? (
        <WorkingPanel job={view.job} />
      ) : view.status === 'error' ? (
        <p className="text-body text-ink-2">
          Not available: {view.error instanceof ApiError ? view.error.detail : 'the service did not answer.'}
        </p>
      ) : (
        <RoverAnswer d={view.section.data} meta={view.section.meta} roverName={view.section.data.rover?.name ?? rover.name} given={given} onGiven={setGiven} />
      )}
    </Disclosure>
  )
}

function RoverAnswer({
  d,
  meta,
  roverName,
  given,
  onGiven,
}: {
  d: RoverSightDTO
  meta: LifecycleMetaDTO
  roverName: string
  /** The values this answer was asked for, and how to ask for others. */
  given: RoverOptions
  onGiven: (o: RoverOptions) => void
}) {
  return (
    <div className="flex flex-col gap-4" data-testid="rover-sight">
      <p className="text-control leading-7 text-ink">
        {!d.resolvable && (
          <span className="font-semibold">
            <span aria-hidden="true">? </span>Cannot be said here.{' '}
          </span>
        )}
        {roverSentence(d, roverName)}
      </p>
      {d.resolvable && d.viewshed ? (
        <ViewshedPanel v={d.viewshed} roverName={roverName} tile={d.viewshed_tile} at={d.lander} />
      ) : d.resolvable ? (
        <p className="text-small text-ink-2">The directions around the lander are not served yet, so there is no map to draw.</p>
      ) : null}
      {d.note && <p className="text-small text-ink-2">{d.note}</p>}
      <Rows about={<><HowSure meta={meta} /><SourcesRow meta={meta} /></>}>
        {(d.assumptions || d.terrain) && (
          <Disclosure title="Antennas, radio and terrain" meta={d.assumptions ? 'assumed unless given' : undefined} defaultOpen={anyGiven(given)}>
            <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-small sm:grid-cols-[max-content_1fr]">
              {d.assumptions &&
                (
                  [
                    ['lander_antenna_m', 'Lander’s antenna above the ground', given.lander_antenna_m],
                    ['rover_antenna_m', 'Rover’s antenna above the ground', given.rover_antenna_m],
                    ['radio_mhz', 'Radio frequency', given.freq_mhz],
                  ] as const
                ).map(([k, label, mine]) => (
                  <div key={k} className="contents">
                    <dt className="text-ink-3">{label}</dt>
                    <dd className="text-ink">
                      {/* A value the team gave is theirs, not an assumption, whatever the service calls it. */}
                      {mine !== undefined ? `${numberWords(d.assumptions![k])}, as you gave it` : orbitWords(d.assumptions![k])}
                      {mine === undefined && d.assumptions![k].provenance === 'assumed' && d.assumptions![k].no_margin_reason && (
                        <span className="block text-ink-2">{plainReason(d.assumptions![k].no_margin_reason as string)}</span>
                      )}
                    </dd>
                  </div>
                ))}
              {d.terrain && (
                <>
                  <dt className="text-ink-3">Terrain</dt>
                  <dd className="text-ink">
                    {d.terrain.product}: a height every {formatValue(d.terrain.post_m)} m, each good to ±{formatValue(d.terrain.vertical_error_m)} m
                  </dd>
                </>
              )}
            </dl>
            {d.resolvable && <RoverInputs answer={d} given={given} onApply={onGiven} />}
          </Disclosure>
        )}
      </Rows>
    </div>
  )
}
