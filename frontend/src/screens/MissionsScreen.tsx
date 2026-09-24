import { useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { useMission as useStore } from '../lib/store'
import { useSubSolar } from '../lib/mission'
import { useMissions, useSites } from '../lib/api/queries'
import type { InstrumentType, Mission } from '../lib/api/adapters'
import {
  INSTRUMENT_LABEL,
  INSTRUMENT_TYPES,
  LIST_GROUPS,
  STATUS_GLYPH,
  STATUS_GROUPS,
  STATUS_LABEL,
  coordinateKindWords,
  isInstrumentType,
  missionAccessibleName,
  missionDate,
  publishedTitle,
  publishedWords,
  type StatusFilter,
} from '../lib/missions'
import { MoonDiscs } from '../components/MoonDiscs'
import { PolarMap, POLAR_MAP_EDGE_LAT, type MissionPin } from '../components/PolarMap'
import { ProgrammeTimeline } from '../components/ProgrammeTimeline'
import { AskPanel } from '../components/Agents'
import { EmptyState, LoadingPanel, ProblemPanel } from '../components/States'
import { Chip, Panel, SectionLabel, Segmented, Unconfirmed } from '../components/ui'

/**
 * S9 — every CLPS delivery at a glance (§10.2), and the new home.
 *
 * Filter state lives in the URL query, so a filtered view is shareable and the
 * back button undoes a chip. The list is the primary accessible path; the
 * discs are pictures with a sentence, the inset's pins are real buttons, and
 * the timeline has a table twin. Hovering or focusing a mission in any of the
 * three highlights it in the other two.
 */

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'flown', label: 'Flown' },
  { value: 'upcoming', label: 'Upcoming' },
]

type LastFilter = { kind: 'type'; value: InstrumentType } | { kind: 'provider' } | { kind: 'status' }

export function MissionsScreen() {
  const [params, setParams] = useSearchParams()
  const types = params.getAll('type').filter(isInstrumentType)
  const statusParam = params.get('status')
  const status: StatusFilter = statusParam === 'flown' || statusParam === 'upcoming' ? statusParam : 'all'
  const provider = params.get('provider') ?? ''
  const [last, setLast] = useState<LastFilter | null>(null)

  const list = useMissions({
    payloadType: types,
    status: status === 'all' ? undefined : STATUS_GROUPS[status],
    provider: provider || undefined,
  })
  const everything = useMissions({})
  const sites = useSites({ kind: 'all' })
  const { windowStartH, cursorH, tableOpen, toggleTable } = useStore(
    useShallow((s) => ({
      windowStartH: s.windowStartH,
      cursorH: s.cursorH,
      tableOpen: s.tableOpen,
      toggleTable: s.toggleTable,
    })),
  )

  const sun = useSubSolar(windowStartH + cursorH)
  const [hover, setHover] = useState<string[] | null>(null)
  const [picked, setPicked] = useState<string[]>([])
  const rowRefs = useRef(new Map<string, HTMLAnchorElement>())
  const insetRef = useRef<HTMLDivElement>(null)

  const shown = useMemo(() => list.data?.items ?? [], [list.data])
  const highlight = useMemo(() => new Set([...(hover ?? []), ...picked]), [hover, picked])

  const update = (mutate: (p: URLSearchParams) => void, lastFilter: LastFilter | null) => {
    const next = new URLSearchParams(params)
    mutate(next)
    setParams(next)
    setLast(lastFilter)
    setPicked([])
  }

  const toggleType = (t: InstrumentType) =>
    update(
      (p) => {
        const cur = p.getAll('type')
        p.delete('type')
        const on = !cur.includes(t)
        for (const v of on ? [...cur, t] : cur.filter((x) => x !== t)) p.append('type', v)
      },
      types.includes(t) ? null : { kind: 'type', value: t },
    )
  const setStatus = (s: StatusFilter) =>
    update((p) => (s === 'all' ? p.delete('status') : p.set('status', s)), s === 'all' ? null : { kind: 'status' })
  const toggleProvider = (name: string) =>
    update(
      (p) => (provider === name ? p.delete('provider') : p.set('provider', name)),
      provider === name ? null : { kind: 'provider' },
    )
  const clearAll = () => update((p) => ['type', 'status', 'provider'].forEach((k) => p.delete(k)), null)

  const providers = useMemo(
    () =>
      [...new Set((everything.data?.items ?? []).map((m) => m.provider).filter((p): p is string => Boolean(p)))].sort(),
    [everything.data],
  )

  // What "Remove {last chip}" removes: the filter added last, else any active one.
  const lastActive: LastFilter | null =
    last && ((last.kind === 'type' && types.includes(last.value)) || (last.kind === 'provider' && provider) || (last.kind === 'status' && status !== 'all'))
      ? last
      : types.length
        ? { kind: 'type', value: types[types.length - 1] }
        : provider
          ? { kind: 'provider' }
          : status !== 'all'
            ? { kind: 'status' }
            : null
  const lastLabel =
    lastActive?.kind === 'type'
      ? INSTRUMENT_LABEL[lastActive.value]
      : lastActive?.kind === 'provider'
        ? provider
        : lastActive?.kind === 'status'
          ? STATUS_OPTIONS.find((o) => o.value === status)?.label
          : undefined
  const removeLast = () => {
    if (!lastActive) return
    if (lastActive.kind === 'type') toggleType(lastActive.value)
    else if (lastActive.kind === 'provider') toggleProvider(provider)
    else setStatus('all')
  }

  const filterWords = [
    types.length ? `carries any of ${types.map((t) => INSTRUMENT_LABEL[t]).join(', ')}` : null,
    status !== 'all' ? `status ${STATUS_OPTIONS.find((o) => o.value === status)?.label}` : null,
    provider ? `provider ${provider}` : null,
  ].filter(Boolean)

  const total = list.data?.total
  const all = everything.data?.total
  const count =
    total === undefined ? 'Loading missions' : all === undefined ? `${total} missions` : `${total} of ${all} missions`

  // Pins: one per target coordinate, since several missions can share one.
  const pins: MissionPin[] = useMemo(() => {
    const groups = new Map<string, Mission[]>()
    for (const m of shown) {
      if (!m.target) continue
      const key = m.siteId ?? `${m.target.latDeg},${m.target.lonDeg}`
      groups.set(key, [...(groups.get(key) ?? []), m])
    }
    return [...groups].map(([key, ms]) => {
      const t = ms[0].target!
      return {
        key,
        latDeg: t.latDeg,
        lonDeg: t.lonDeg,
        dashed: t.coordinateKind !== 'actual_landing',
        label: `${ms.map((m) => m.name).join(', ')}: ${t.name}, ${coordinateKindWords(
          t.coordinateKind,
          ms[0].targetName,
        )}. Show in the list`,
        highlighted: ms.some((m) => highlight.has(m.id)),
      }
    })
  }, [shown, highlight])
  const idsForPin = (key: string) =>
    shown.filter((m) => m.target && (m.siteId ?? `${m.target.latDeg},${m.target.lonDeg}`) === key).map((m) => m.id)
  const polarCount = pins.filter((p) => p.latDeg <= POLAR_MAP_EDGE_LAT).length

  const siteSummary = useMemo(
    () => new Map((sites.data?.items ?? []).map((i) => [i.site.id, i.summary])),
    [sites.data],
  )
  const farFocus = shown.find((m) => highlight.has(m.id) && m.region === 'farside' && m.siteId)
  const earthNeverRises = Boolean(farFocus?.siteId && siteSummary.get(farFocus.siteId)?.earthHours === 0)

  const focusInset = () => {
    insetRef.current?.scrollIntoView({ block: 'nearest' })
    insetRef.current?.focus()
  }

  const rowHandlers = (id: string) => ({
    onMouseEnter: () => setHover([id]),
    onMouseLeave: () => setHover(null),
    onFocus: () => setHover([id]),
    onBlur: () => setHover(null),
  })

  return (
    <div className="flex grow flex-col">
      <header className="flex flex-col gap-2 border-b border-line px-4 py-4 lg:px-6">
        <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
          <h1 className="text-heading font-semibold tracking-title">CLPS missions</h1>
          <p aria-live="polite" className="text-body text-ink-2">
            <span className="sr-only">Showing </span>
            {count}
          </p>
        </div>
        <p className="max-w-3xl text-body leading-6 text-ink-2">
          Every NASA Commercial Lunar Payload Services delivery: where it went or will go, when, what it
          carries and how it went. Open one to see what the Sun and Earth do at its target.
        </p>
      </header>

      <div role="group" aria-label="Filters" data-guide="missions-filters" className="flex flex-col gap-3 border-b border-line px-4 py-3 lg:px-6">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <span className="text-small font-medium text-ink">Status</span>
          <Segmented label="Status" options={STATUS_OPTIONS} value={status} onChange={setStatus} />
        </div>
        <FilterRow label="Instruments carried (any of)">
          {INSTRUMENT_TYPES.map((t) => (
            <Chip key={t} tone="neutral" selected={types.includes(t)} onClick={() => toggleType(t)}>
              {INSTRUMENT_LABEL[t]}
            </Chip>
          ))}
        </FilterRow>
        {providers.length > 0 && (
          <FilterRow label="Provider">
            {providers.map((p) => (
              <Chip key={p} tone="neutral" selected={provider === p} onClick={() => toggleProvider(p)}>
                {p}
              </Chip>
            ))}
          </FilterRow>
        )}
      </div>

      <div className="grid gap-6 p-4 lg:p-6 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        {/* The list comes first in the DOM: it is the primary accessible path
            and, on a phone, the fastest answer. From 768 px up the Moon view
            is drawn first (left at ≥ 1280), as the handoff lays it out. */}
        <section
          aria-labelledby="missions-list-h"
          className="flex min-w-0 flex-col gap-3 md:order-2 xl:order-none xl:col-start-2 xl:row-start-1"
        >
          <SectionLabel id="missions-list-h">Missions</SectionLabel>
          {list.isPending ? (
            <LoadingPanel
              done={0}
              total={1}
              title="Loading CLPS missions"
              unit="lists"
              note="The mission records are compiled from NASA pages, LROC images and the IAU Gazetteer, and stored with the service; nothing is fetched from those sites while you wait."
            />
          ) : list.error && !list.data ? (
            <ProblemPanel error={list.error} fallbackTitle="Cannot load the missions" onRetry={() => void list.refetch()} />
          ) : shown.length === 0 ? (
            <Panel>
              <EmptyState
                title="No missions match these filters"
                detail={
                  <>
                    {all ?? 'All'} missions checked against: <strong className="text-ink">{filterWords.join('; ')}</strong>.
                  </>
                }
                primary={{ label: 'Clear filters', onClick: clearAll }}
                secondary={lastLabel ? { label: `Remove ${lastLabel}`, onClick: removeLast } : undefined}
              />
            </Panel>
          ) : (
            <Panel className={`flex flex-col xl:max-h-[820px] xl:overflow-y-auto ${list.isPlaceholderData ? 'opacity-70' : ''}`}>
              {LIST_GROUPS.map((g) => {
                const ms = shown.filter((m) => g.statuses.includes(m.status))
                if (!ms.length) return null
                return (
                  <div key={g.id} className="flex flex-col">
                    <SectionLabel as="h3" className="border-b border-line bg-inset px-4 py-2">
                      {g.label} · {ms.length}
                    </SectionLabel>
                    <ul>
                      {ms.map((m) => (
                        <li key={m.id}>
                          <MissionRow
                            mission={m}
                            highlighted={highlight.has(m.id)}
                            rowRef={(el) => {
                              if (el) rowRefs.current.set(m.id, el)
                              else rowRefs.current.delete(m.id)
                            }}
                            {...rowHandlers(m.id)}
                          />
                        </li>
                      ))}
                    </ul>
                  </div>
                )
              })}
            </Panel>
          )}
        </section>

        <section
          aria-labelledby="missions-map-h"
          className="flex min-w-0 flex-col gap-4 md:order-1 xl:order-none xl:col-start-1 xl:row-start-1"
        >
          <SectionLabel id="missions-map-h">Where they went, or will go</SectionLabel>
          <Panel className="flex flex-col gap-4 p-4">
            <MoonDiscs
              missions={list.isPending ? [] : shown}
              highlight={highlight}
              earthNeverRisesOnFarSide={earthNeverRises}
              onPole={focusInset}
            />
          </Panel>
          <div
            ref={insetRef}
            tabIndex={-1}
            role="group"
            aria-labelledby="missions-inset-h"
            className="flex flex-col border border-line bg-panel outline-none focus-visible:outline-2"
          >
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-line px-4 py-3">
              <SectionLabel as="h3" id="missions-inset-h">
                Close-up of the south pole · 80°S to the pole
              </SectionLabel>
              <span className="ml-auto text-caption text-ink-3">
                {polarCount} target{polarCount === 1 ? '' : 's'} inside 80°S
              </span>
            </div>
            <div className="flex justify-center p-3">
              <PolarMap
                sun={sun}
                selectedSiteId=""
                size={440}
                missionPins={pins}
                siteMarks="dots"
                onMissionPin={(keys) => {
                  const ids = keys.flatMap(idsForPin)
                  setPicked(ids)
                  rowRefs.current.get(ids[0])?.focus()
                }}
                onMissionHover={(keys) => setHover(keys ? keys.flatMap(idsForPin) : null)}
              />
            </div>
            <PinLegend />
          </div>
        </section>
      </div>

      <section className="px-4 pb-6 lg:px-6" aria-label="Timeline">
        <ProgrammeTimeline
          missions={shown}
          highlight={highlight}
          onHover={(id) => setHover(id ? [id] : null)}
          showTable={tableOpen}
          onToggleTable={toggleTable}
          nowMs={Date.now()}
        />
      </section>

      <div className="flex flex-col px-4 pb-8 lg:px-6">
        <AskPanel />
      </div>
    </div>
  )
}

function FilterRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2 md:flex-row md:items-center md:gap-4">
      <span className="shrink-0 text-small font-medium text-ink">{label}</span>
      {/* Scrolls sideways on a phone rather than wrapping into a wall of chips. */}
      <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 md:mx-0 md:flex-wrap md:overflow-visible md:px-0 md:pb-0">
        {children}
      </div>
    </div>
  )
}

function MissionRow({
  mission: m,
  highlighted,
  rowRef,
  ...handlers
}: {
  mission: Mission
  highlighted: boolean
  rowRef: (el: HTMLAnchorElement | null) => void
  onMouseEnter: () => void
  onMouseLeave: () => void
  onFocus: () => void
  onBlur: () => void
}) {
  const d = missionDate(m)
  return (
    <Link
      ref={rowRef}
      to={`/missions/${m.id}`}
      aria-label={missionAccessibleName(m)}
      {...handlers}
      className={`flex flex-col gap-1 border-b border-line px-4 py-3 no-underline ${
        highlighted ? 'bg-inset' : 'hover:bg-inset'
      }`}
    >
      <span className="flex items-baseline justify-between gap-3">
        <span className="text-control font-semibold text-ink">{m.name}</span>
        <span className="shrink-0 text-small text-ink-2" title={STATUS_LABEL[m.status]}>
          <span aria-hidden="true">{STATUS_GLYPH[m.status]} </span>
          {STATUS_LABEL[m.status]}
        </span>
      </span>
      <span className="text-small leading-5 text-ink-2">
        {m.provider ?? <Unconfirmed />} ·{' '}
        {d ? (
          <>
            {d.which === 'landing' ? 'landing' : 'launch'}{' '}
            <span title={publishedTitle(d.date)}>{publishedWords(d.date)}</span>
          </>
        ) : (
          <>
            landing date <Unconfirmed />
          </>
        )}
      </span>
      <span className="text-caption leading-caption text-ink-3">
        {m.payloadTypes.length ? m.payloadTypes.map((t) => INSTRUMENT_LABEL[t]).join(' · ') : 'Payloads unconfirmed'}
      </span>
      {m.unconfirmedFields.length > 0 && (
        <span className="text-caption text-uncertain">Some details unconfirmed</span>
      )}
    </Link>
  )
}

function PinLegend() {
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-line px-4 py-3 text-caption text-ink">
      <span className="flex items-center gap-2">
        <svg width="14" height="14" viewBox="-7 -7 14 14" aria-hidden="true">
          <rect x="-4" y="-4" width="8" height="8" transform="rotate(45)" fill="var(--color-panel)" stroke="var(--color-ink)" strokeWidth="1.5" />
        </svg>
        Solid diamond: where a lander came to rest
      </span>
      <span className="flex items-center gap-2">
        <svg width="14" height="14" viewBox="-7 -7 14 14" aria-hidden="true">
          <rect x="-4" y="-4" width="8" height="8" transform="rotate(45)" fill="var(--color-panel)" stroke="var(--color-ink)" strokeWidth="1.5" strokeDasharray="2 1.5" />
        </svg>
        Dashed diamond: a planned target or a feature centre, not a landing point
      </span>
      <span className="flex items-center gap-2">
        <svg width="12" height="12" viewBox="-6 -6 12 12" aria-hidden="true">
          <circle r="4.5" fill="var(--color-ink-2)" stroke="var(--color-canvas)" strokeWidth="1.5" />
        </svg>
        Dot: a candidate site, named on the <Link to="/map">Map</Link>
      </span>
      <span className="flex items-center gap-2">
        <span className="font-semibold">×2</span> two targets drawn close together
      </span>
    </div>
  )
}
