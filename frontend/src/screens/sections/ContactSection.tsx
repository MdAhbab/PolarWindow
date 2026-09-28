import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useShallow } from 'zustand/react/shallow'
import { API_BASE, api } from '../../lib/api/client'
import type { MissionDetail } from '../../lib/api/adapters'
import type { ContactDTO, LifecycleMetaDTO, QuantityDTO } from '../../lib/api/lifecycle'
import { useHistory, useLifecycleWrite, useSection, useSectionStatus } from '../../lib/api/lifecycleQueries'
import { keys } from '../../lib/api/queries'
import { useWindowParams } from '../../lib/mission'
import { useMission as useStore } from '../../lib/store'
import { hasSite } from '../../lib/sites'
import { dateTimeWords, msFromModelH, windowLine } from '../../lib/format'
import { quantityText, quantityView } from '../../lib/lifecycle/quantity'
import { NumberRow, QuantityTile } from '../../components/lifecycle/QuantityTile'
import { Answer, ChartPanel, HowSure, Legend, Rows, SectionLayout, SectionStates, SourcesRow } from '../../components/lifecycle/Section'
import { ContactChart, ContactTable, ORBITER_CAPTION, RELAY_STATUS, contactRows, rowStretches } from '../../components/lifecycle/ContactChart'
import { Field, FormSheet, HistoryList, Select, TextInput } from '../../components/lifecycle/Forms'
import { WindowPicker } from '../../components/WindowPicker'
import { Button, Disclosure } from '../../components/ui'
import { UncertaintyNote } from '../../components/States'
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
  const view = useSection<ContactDTO>('contact', m.id, (signal) => api.contact(m.id, { start: w.start, end: w.end }, signal), [w.start, w.end])
  const status = useSectionStatus(m.id, 'contact')
  return (
    <SectionLayout question="How often can the lander talk to Earth?">
      <SectionStates view={view} terms={TERMS} status={status}>
        {({ data, meta }) => (
          <ContactAnswer
            contact={data}
            meta={meta}
            mission={m}
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
 * Each relay with its launch status: `state` in words with a glyph, from its
 * node; `launch` the served status line (its launch plan), or the node's note.
 */
export function relayList(c: ContactDTO) {
  return c.relays.map((r) => {
    const node = c.nodes.find((n) => n.id === r.id)
    return {
      id: r.id,
      name: r.name,
      adds_h: r.adds_h,
      operator: node?.operator ?? null,
      state: node ? RELAY_STATUS[node.status] : null,
      launch: r.status || node?.launch_note || null,
    }
  })
}

/**
 * The answer in words (design-lifecycle.md, Contact): what a ground station
 * hears, what a relay could add as a range with its launch status beside it,
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
        ? `Through ${named} it could add ${quantityText(n.via_relay_h)}, if it flies as planned.`
        : `Through a relay it could add ${quantityText(n.via_relay_h)}, if they fly as planned.`,
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
    out.push(`The longest time without contact is ${quantityText(n.longest_unheard_h)}${withRelay ? ' with the relay, if it flies as planned' : ''}.`)
  }
  return out.join(' ')
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
  start,
  end,
  datesNote,
}: {
  contact: ContactDTO
  meta: LifecycleMetaDTO
  mission: MissionDetail
  start: number
  end: number
  datesNote?: string | null
}) {
  const hours = (end - start) / 3_600_000
  const n = contact.numbers
  const rows = contactRows(contact)
  const planned = rows.some((r) => r.planned)
  const { windowStartH, windowHours } = useStore(useShallow((s) => ({ windowStartH: s.windowStartH, windowHours: s.windowHours })))
  const relays = relayList(contact)
  const orbiters = rows.filter((r) => r.orbiter)
  // A wait that counts a planned relay is a range, and says so.
  const relayNote = (q: QuantityDTO) => (relays.length && isRange(q) ? 'with the relay, if it flies as planned' : undefined)
  return (
    <>
      <Answer meta={meta}>{contactAnswer(contact)}</Answer>
      {contact.link_budget_note && <UncertaintyNote className="-mt-3">{contact.link_budget_note}</UncertaintyNote>}
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
        <QuantityTile term="contactUnheard" q={n.longest_unheard_h} scale={hours} note={relayNote(n.longest_unheard_h)} />
        <QuantityTile term="messageWait" q={n.longest_message_wait_min} note={relayNote(n.longest_message_wait_min)} />
      </NumberRow>
      <ChartPanel
        title={`Who can hear the lander, ${windowLine(start, hours)}`}
        chart={<ContactChart contact={contact} rows={rows} start={start} end={end} />}
        legend={
          <Legend
            items={[
              { swatch: <span className="h-3 w-5 bg-earth-fill" />, label: 'Can hear the lander' },
              ...(planned ? [{ swatch: <span className="hatch-uncertain h-3 w-5 border border-uncertain" />, label: 'A range: if it flies as planned' }] : []),
              ...(orbiters.length ? [{ swatch: <span className="h-3 w-5 border border-dashed border-earth" />, label: 'Could see the lander (an orbiter, not a relay)' }] : []),
              ...(contact.bookings.length ? [{ swatch: <span className="h-3 w-5 border-2 border-ink" />, label: 'Booked pass' }] : []),
            ]}
          />
        }
        table={<ContactTable contact={contact} rows={rows} />}
      />
      {datesNote && <p className="-mt-3 text-caption leading-caption text-ink-3">{datesNote}</p>}
      <Rows>
        {relays.length > 0 && (
          <Disclosure title="Relays" meta={relays.map((r) => (r.state ? `${r.name} · ${r.state.words.toLowerCase()}` : r.name)).join(', ')}>
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
                  <span className="text-small text-ink-2">
                    {isRange(r.adds_h)
                      ? `Adds ${quantityText(r.adds_h)} through it, if it flies as planned.`
                      : `Time through it: ${numberWords(r.adds_h).replace(/^Not worked out: /, 'not worked out. ')}`}
                  </span>
                </li>
              ))}
            </ul>
          </Disclosure>
        )}
        {orbiters.length > 0 && (
          <Disclosure title="Orbiters that could see the lander" meta={orbiters.map((r) => r.label).join(', ')}>
            <p className="text-body text-ink-2">
              {contact.orbiters_note ??
                'These orbiters already fly over the Moon and could see the lander. None is a relay for it: no agreement carries its data, so they count in no number above.'}
            </p>
            <ul className="flex flex-col divide-y divide-line border-y border-line">
              {orbiters.map((r) => {
                const node = contact.nodes.find((x) => x.kind === 'orbiter' && (x.id === r.links[0]?.to || x.id === r.links[0]?.from))
                const passes = rowStretches(r).length
                return (
                  <li key={r.key} className="flex flex-wrap items-baseline justify-between gap-x-4 py-2.5">
                    <span className="text-body text-ink">
                      {r.label}
                      {node?.operator ? <span className="text-small text-ink-3"> · {node.operator}</span> : null}
                    </span>
                    <span className="text-small text-ink-2">
                      {passes} pass{passes === 1 ? '' : 'es'} over these dates · {ORBITER_CAPTION}
                    </span>
                  </li>
                )
              })}
            </ul>
          </Disclosure>
        )}
        <BookingsRow contact={contact} missionId={m.id} />
        <RoverRow missionId={m.id} />
        <Disclosure title="More numbers">
          <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-body sm:grid-cols-[max-content_1fr]">
            <dt className="text-ink-3">Time in contact with Earth (Earth above the skyline)</dt>
            <dd className="text-ink">{numberWords(n.direct_h)}</dd>
            <dt className="text-ink-3">In contact either way, directly or through a relay</dt>
            <dd className="text-ink">{numberWords(n.either_h, 'if the relay flies as planned')}</dd>
            <dt className="text-ink-3">Dark and out of contact at once</dt>
            <dd className="text-ink">{numberWords(n.dark_and_unheard_h, 'with the relay, if it flies as planned')}</dd>
          </dl>
        </Disclosure>
        <Disclosure title="Download the contact plan" meta="ION, spreadsheet">
          <ul className="flex flex-wrap gap-3">
            {(
              [
                ['ion', 'Contact plan for ION (DTN)'],
                ['csv', 'Spreadsheet (CSV)'],
              ] as const
            ).map(([f, label]) => (
              <li key={f}>
                <a
                  className="inline-flex h-12 items-center rounded-control border border-line-strong px-4 text-body font-semibold text-ink no-underline hover:bg-inset"
                  href={`${API_BASE}/missions/${encodeURIComponent(m.id)}/contact/plan?format=${f}&start=${new Date(start).toISOString()}&end=${new Date(end).toISOString()}`}
                  download
                >
                  {label}
                </a>
              </li>
            ))}
          </ul>
        </Disclosure>
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
        <HowSure meta={meta} />
        <SourcesRow meta={meta} />
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

/** Whether the rover stays in sight of the lander (asked for when the row opens). */
function RoverRow({ missionId }: { missionId: string }) {
  const [open, setOpen] = useState(false)
  const q = useQuery({
    queryKey: keys.lifecycle('rover', missionId),
    enabled: open,
    retry: false,
    queryFn: ({ signal }) => api.rover(missionId, undefined, signal),
  })
  const d = q.data?.data
  return (
    <Disclosure title="Rover and lander line of sight" onOpen={() => setOpen(true)}>
      {q.isPending ? (
        <p className="text-small text-ink-3">Loading…</p>
      ) : q.error ? (
        <p className="text-body text-ink-2">Not available for this mission.</p>
      ) : d && !d.resolvable ? (
        <p className="text-body text-ink-2">{d.reason ?? 'Not resolvable with the terrain available.'}</p>
      ) : d ? (
        <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-body sm:grid-cols-[max-content_1fr]">
          <dt className="text-ink-3">Share of the planned drive out of the lander’s sight</dt>
          <dd className="text-ink">{quantityText(d.out_of_sight_share)}</dd>
          <dt className="text-ink-3">Longest stretch out of sight</dt>
          <dd className="text-ink">{quantityText(d.longest_out_of_sight_m)}</dd>
        </dl>
      ) : null}
    </Disclosure>
  )
}
