import { useId, useMemo, useRef, useState } from 'react'
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
import { Button, Chip, Disclosure, Panel, Segmented, Unconfirmed } from '../components/ui'
import { Icon } from '../components/Icon'
import { Select } from '../components/Select'

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
  const [showTypes, setShowTypes] = useState(types.length > 0)
  const [mapView, setMapView] = useState<'pole' | 'moon'>('pole')
  const filterId = useId()

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

  const activeFilters = types.length + (provider ? 1 : 0) + (status !== 'all' ? 1 : 0)

  return (
    <div className="flex grow flex-col">
      <header className="flex flex-col gap-3 pw-page pt-6 lg:pt-10">
        <p className="pw-eyebrow">NASA Commercial Lunar Payload Services</p>
        <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
          <h1 className="pw-display text-[36px] leading-[38px] sm:text-[48px] sm:leading-[50px] lg:text-[56px] lg:leading-[58px]">
            CLPS missions
          </h1>
          <p
            aria-live="polite"
            className="inline-flex h-9 items-center rounded-pill border border-line-strong bg-tray px-4 text-small font-semibold text-ink-2 tnum"
          >
            <span className="sr-only">Showing </span>
            {count}
          </p>
        </div>
        <p className="max-w-3xl text-lede leading-7 text-ink-2">
          Every NASA CLPS delivery to the Moon, flown and planned. Open one to follow it from getting ready to coming
          home.
        </p>
      </header>

      <div
        role="group"
        aria-label="Filters"
        data-guide="missions-filters"
        className="flex flex-col gap-3 pw-page pt-6 pb-1"
      >
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <Segmented label="Status" options={STATUS_OPTIONS} value={status} onChange={setStatus} />
          <Button
            onClick={() => setShowTypes((v) => !v)}
            expanded={showTypes}
            controls={`${filterId}-types`}
          >
            Instruments{types.length ? ` · ${types.length}` : ''}
            <Icon name="chevron" size={16} strokeWidth={2} className={`transition-transform ${showTypes ? 'rotate-180' : ''}`} />
          </Button>
          {providers.length > 0 && (
            <>
              <label htmlFor={`${filterId}-provider`} className="sr-only">
                Provider
              </label>
              <Select
                id={`${filterId}-provider`}
                look="pill"
                value={provider}
                onChange={(v) => update((p) => (v ? p.set('provider', v) : p.delete('provider')), v ? { kind: 'provider' } : null)}
                options={[{ value: '', label: 'Any provider' }, ...providers.map((p) => ({ value: p, label: p }))]}
                className={`text-small font-semibold ${provider ? 'border-ink text-ink' : 'text-ink-2'}`}
              />
            </>
          )}
          {/* The empty list has its own "Clear filters"; one is enough. */}
          {activeFilters > 0 && shown.length > 0 && (
            <Button variant="ghost" size="sm" onClick={clearAll}>
              Clear filters
            </Button>
          )}
        </div>
        <div
          id={`${filterId}-types`}
          hidden={!showTypes}
          className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 md:mx-0 md:flex-wrap md:overflow-visible md:px-0 md:pb-0"
        >
          <span className="sr-only">Instruments carried, any of:</span>
          {INSTRUMENT_TYPES.map((t) => (
            <Chip key={t} tone="neutral" selected={types.includes(t)} onClick={() => toggleType(t)}>
              {INSTRUMENT_LABEL[t]}
            </Chip>
          ))}
        </div>
      </div>

      <div className="grid gap-7 pw-page pt-6 pb-8 lg:pt-8 xl:grid-cols-[minmax(0,6fr)_minmax(0,5fr)]">
        {/* The list comes first in the DOM: it is the primary accessible path
            and, on a phone, the fastest answer. From 768 px up the map is
            drawn first (left at ≥ 1280). */}
        <section
          aria-labelledby="missions-list-h"
          className="flex min-w-0 flex-col gap-3 md:order-2 xl:order-none xl:col-start-2 xl:row-start-1"
        >
          <h2 id="missions-list-h" className="sr-only">
            Missions
          </h2>
          {list.isPending ? (
            <LoadingPanel done={0} total={1} title="Loading CLPS missions" unit="lists" />
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
            <Panel flush className={`relative flex flex-col xl:max-h-[640px] xl:overflow-y-auto ${list.isPlaceholderData ? 'opacity-70' : ''}`}>
              {LIST_GROUPS.map((g) => {
                const ms = shown.filter((m) => g.statuses.includes(m.status))
                if (!ms.length) return null
                return (
                  <div key={g.id} className="flex flex-col">
                    <h3 className="pw-eyebrow sticky top-0 z-10 border-b border-line bg-panel/95 px-4 py-3 backdrop-blur-sm sm:px-5">
                      {g.label} · {ms.length}
                    </h3>
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
          className="flex min-w-0 flex-col md:order-1 xl:order-none xl:col-start-1 xl:row-start-1"
        >
          <div
            ref={insetRef}
            tabIndex={-1}
            className="pw-card pw-card-flush flex flex-col outline-none focus-visible:outline-2"
          >
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 pt-4 pb-1 sm:px-5 sm:pt-5">
              <h2 id="missions-map-h" className="text-title-lg font-semibold tracking-title text-ink">
                Where they land
              </h2>
              <div className="ml-auto">
                <Segmented
                  label="Map"
                  options={[
                    { value: 'pole', label: 'South pole' },
                    { value: 'moon', label: 'Whole Moon' },
                  ]}
                  value={mapView}
                  onChange={setMapView}
                  pill
                />
              </div>
            </div>
            {mapView === 'pole' ? (
              <>
                <div className="flex justify-center p-3">
                  <PolarMap
                    sun={sun}
                    selectedSiteId=""
                    size={420}
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
                <PinLegend polarCount={polarCount} />
              </>
            ) : (
              <div className="p-4">
                <MoonDiscs
                  missions={list.isPending ? [] : shown}
                  highlight={highlight}
                  earthNeverRisesOnFarSide={earthNeverRises}
                  onPole={() => {
                    setMapView('pole')
                    focusInset()
                  }}
                />
              </div>
            )}
          </div>
        </section>
      </div>

      <div className="pw-page flex flex-col gap-4 pb-8">
        <Disclosure title="Timeline" meta="every dated mission, by provider">
          <ProgrammeTimeline
            missions={shown}
            highlight={highlight}
            onHover={(id) => setHover(id ? [id] : null)}
            showTable={tableOpen}
            onToggleTable={toggleTable}
            nowMs={Date.now()}
          />
        </Disclosure>
        <AskPanel />
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
      className={`group flex flex-col gap-1 border-b border-line px-4 py-3.5 no-underline transition-colors duration-[var(--pw-dur-quick)] focus-visible:-outline-offset-2 sm:px-5 ${
        highlighted ? 'bg-inset' : 'hover:bg-inset'
      }`}
    >
      <span className="flex items-baseline justify-between gap-3">
        <span className="text-control font-semibold text-ink transition-transform duration-[var(--pw-dur-lift)] ease-[var(--ease-settle)] group-hover:translate-x-0.5">{m.name}</span>
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
    </Link>
  )
}

function PinLegend({ polarCount }: { polarCount: number }) {
  const diamond = (dashed: boolean) => (
    <svg width="12" height="12" viewBox="-7 -7 14 14" aria-hidden="true">
      <rect
        x="-4"
        y="-4"
        width="8"
        height="8"
        transform="rotate(45)"
        fill="var(--color-panel)"
        stroke="var(--color-ink)"
        strokeWidth="1.5"
        strokeDasharray={dashed ? '2 1.5' : undefined}
      />
    </svg>
  )
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line px-4 py-3 text-caption text-ink-2 sm:px-5">
      <span>
        {polarCount} target{polarCount === 1 ? '' : 's'} south of 80°S:
      </span>
      <span className="flex items-center gap-1.5">{diamond(false)} where a lander came to rest</span>
      <span className="flex items-center gap-1.5">{diamond(true)} planned target</span>
      <span className="flex items-center gap-1.5">
        <svg width="10" height="10" viewBox="-6 -6 12 12" aria-hidden="true">
          <circle r="4.5" fill="var(--color-ink-2)" stroke="var(--color-canvas)" strokeWidth="1.5" />
        </svg>
        candidate site, named on the <Link to="/map">Map</Link>
      </span>
    </div>
  )
}
