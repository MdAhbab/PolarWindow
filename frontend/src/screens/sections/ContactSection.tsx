import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useShallow } from 'zustand/react/shallow'
import { API_BASE, api } from '../../lib/api/client'
import type { MissionDetail } from '../../lib/api/adapters'
import type { ContactDTO, LifecycleMetaDTO } from '../../lib/api/lifecycle'
import { useHistory, useLifecycleWrite, useSection, useSectionStatus } from '../../lib/api/lifecycleQueries'
import { keys } from '../../lib/api/queries'
import { useWindowParams } from '../../lib/mission'
import { useMission as useStore } from '../../lib/store'
import { hasSite } from '../../lib/sites'
import { dateTimeWords, msFromModelH, windowLine } from '../../lib/format'
import { quantityText } from '../../lib/lifecycle/quantity'
import { NumberRow, QuantityTile } from '../../components/lifecycle/QuantityTile'
import { Answer, ChartPanel, HowSure, Legend, Rows, SectionLayout, SectionStates, SourcesRow } from '../../components/lifecycle/Section'
import { ContactChart, ContactTable, contactRows } from '../../components/lifecycle/ContactChart'
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
        {({ data, meta }) => <ContactAnswer contact={data} meta={meta} mission={m} start={Date.parse(w.start)} end={Date.parse(w.end)} />}
      </SectionStates>
    </SectionLayout>
  )
}

function ContactAnswer({
  contact,
  meta,
  mission: m,
  start,
  end,
}: {
  contact: ContactDTO
  meta: LifecycleMetaDTO
  mission: MissionDetail
  start: number
  end: number
}) {
  const hours = (end - start) / 3_600_000
  const n = contact.numbers
  const rows = contactRows(contact)
  const planned = rows.some((r) => r.planned)
  const { windowStartH, windowHours } = useStore(useShallow((s) => ({ windowStartH: s.windowStartH, windowHours: s.windowHours })))
  const relayRange = n.via_relay_h.lo !== null || n.via_relay_h.value !== null
  return (
    <>
      <Answer meta={meta}>
        A ground station can hear it for {quantityText(n.station_hears_h)} over these dates.
        {relayRange && contact.relays.length > 0 && <> Through a relay it could add {quantityText(n.via_relay_h)}, if it flies as planned.</>}{' '}
        The longest time without contact is {quantityText(n.longest_unheard_h)}.
      </Answer>
      {contact.link_budget_note && <UncertaintyNote className="-mt-3">{contact.link_budget_note}</UncertaintyNote>}
      <NumberRow>
        <QuantityTile term="stationHears" q={n.station_hears_h} tone="earth" icon="earth" scale={hours} />
        <QuantityTile
          term="viaRelay"
          q={contact.relays.length ? n.via_relay_h : { ...n.via_relay_h, value: null, lo: null, hi: null, missing_reason: 'No relay serves this site.' }}
          tone="earth"
          scale={hours}
          note={contact.relays.length ? 'if it flies as planned' : undefined}
        />
        <QuantityTile term="contactUnheard" q={n.longest_unheard_h} scale={hours} />
        <QuantityTile term="messageWait" q={n.longest_message_wait_min} />
      </NumberRow>
      <ChartPanel
        title={`Who can hear the lander, ${windowLine(msFromModelH(windowStartH), windowHours)}`}
        chart={<ContactChart contact={contact} rows={rows} start={start} end={end} />}
        legend={
          <Legend
            items={[
              { swatch: <span className="h-3 w-5 bg-earth-fill" />, label: 'Can hear the lander' },
              ...(planned ? [{ swatch: <span className="hatch-uncertain h-3 w-5 border border-uncertain" />, label: 'A range: if it flies as planned' }] : []),
              ...(contact.bookings.length ? [{ swatch: <span className="h-3 w-5 border-2 border-ink" />, label: 'Booked pass' }] : []),
            ]}
          />
        }
        table={<ContactTable contact={contact} rows={rows} />}
      />
      <Rows>
        {contact.relays.length > 0 && (
          <Disclosure title="Relays" meta={contact.relays.map((r) => r.name).join(', ')}>
            <ul className="flex flex-col divide-y divide-line border-y border-line">
              {contact.relays.map((r) => (
                <li key={r.id} className="flex flex-col gap-0.5 py-2.5">
                  <span className="text-body font-semibold text-ink">{r.name}</span>
                  <span className="text-small text-ink-2">
                    Adds {quantityText(r.adds_h)}, if it flies as planned. {r.status}
                  </span>
                </li>
              ))}
            </ul>
          </Disclosure>
        )}
        <BookingsRow contact={contact} missionId={m.id} />
        <RoverRow missionId={m.id} />
        <Disclosure title="More numbers">
          <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-body sm:grid-cols-[max-content_1fr]">
            <dt className="text-ink-3">Time in contact with Earth (Earth above the skyline)</dt>
            <dd className="text-ink">{quantityText(n.direct_h)}</dd>
            <dt className="text-ink-3">In contact either way, directly or through a relay</dt>
            <dd className="text-ink">{quantityText(n.either_h)}</dd>
            <dt className="text-ink-3">Dark and out of contact at once</dt>
            <dd className="text-ink">{quantityText(n.dark_and_unheard_h)}</dd>
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
