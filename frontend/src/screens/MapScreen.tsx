import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { useSiteMetricsMap } from '../lib/useMetricsMap'
import { useMission } from '../lib/store'
import { useSubSolar } from '../lib/mission'
import { getCandidates, siteById } from '../lib/sites'
import { useMissions } from '../lib/api/queries'
import { PolarMap, type MissionPin } from '../components/PolarMap'
import { DateSlider } from '../components/DateSlider'
import { EmptyState, LoadingPanel, ProblemPanel } from '../components/States'
import { Button, Chip, Disclosure, Panel, SearchField, SectionLabel } from '../components/ui'
import { bound, coords, percent } from '../lib/format'
import { SURVIVAL_LIMIT_H } from '../lib/geometry/metrics'
import { coordinateKindWords } from '../lib/missions'
import type { Mission } from '../lib/api/adapters'
import type { SiteMetrics } from '../lib/types'

/** S1 — where you start: pick a site, see the terminator sweep across the pole. */
export function MapScreen() {
  const { siteId, setSite, cursorH, windowStartH, compareIds } = useMission(
    useShallow((s) => ({
      compareIds: s.compareIds,
      siteId: s.siteId,
      setSite: s.setSite,
      cursorH: s.cursorH,
      windowStartH: s.windowStartH,
    })),
  )
  // The candidates only: mission targets are a separate, optional layer.
  // Keyed on the registry's contents, not frozen at first render: a refetched
  // site list must reach the map.
  const sun = useSubSolar(windowStartH + cursorH)
  const candidates = getCandidates()
  const idKey = candidates.map((s) => s.id).join('|')
  const allIds = useMemo(() => (idKey ? idKey.split('|') : []), [idKey])
  const focusIds = useMemo(
    () => (allIds.includes(siteId) ? allIds : [...allIds, siteId]),
    [allIds, siteId],
  )
  const { map: metrics, done, total, isPending, error } = useSiteMetricsMap(focusIds)
  const compute = { status: isPending ? 'running' : 'ready', done, total } as const
  const site = siteById(siteId)
  const focused = metrics[siteId]
  const inCompare = compareIds.includes(siteId)
  const compareCount = compareIds.length

  const [query, setQuery] = useState('')
  const [minSun, setMinSun] = useState(0)
  // U5: no filter is applied until the user applies one. "Any" is Infinity,
  // and the slider's top is the longest night on this list rounded up to a
  // whole day, so every site can be shown.
  const [maxDark, setMaxDark] = useState(Infinity)
  const [nearPsr, setNearPsr] = useState(false)
  const [showMissions, setShowMissions] = useState(false)
  const missions = useMissions({})

  const darkMax = useMemo(() => {
    const longest = allIds.map((id) => metrics[id]?.sun.longestDownH ?? 0)
    const m = Math.max(0, ...longest)
    return m > 0 ? Math.ceil(m / 24) * 24 : 0
  }, [allIds, metrics])

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase()
    return candidates.filter((s) => {
      if (q && !`${s.code} ${s.name}`.toLowerCase().includes(q)) return false
      const m: SiteMetrics | undefined = metrics[s.id]
      if (!m) return true
      if (m.sun.fractionUp * 100 < minSun) return false
      if (m.sun.longestDownH > maxDark) return false
      // A rim site sits on the edge of a named polar crater, whose floor is
      // permanently shadowed. The previous test read a synthetic terrain
      // spec that no longer exists, so the chip silently emptied the list.
      if (nearPsr && s.searchKind !== 'rim') return false
      return true
    })
    // `candidates` is rebuilt from the registry each render; its ids are the key.
  }, [query, minSun, maxDark, nearPsr, metrics, idKey])

  const binding =
    minSun > 0 && matches.length === 0
      ? `sunlight at least ${minSun}%`
      : Number.isFinite(maxDark)
        ? `longest night under ${maxDark} h`
        : nearPsr
          ? 'beside a shadowed floor'
          : `the search “${query}”`

  const missionPins: MissionPin[] = useMemo(() => {
    if (!showMissions) return []
    const groups = new Map<string, Mission[]>()
    for (const m of missions.data?.items ?? []) {
      if (!m.target || !m.siteId) continue
      groups.set(m.siteId, [...(groups.get(m.siteId) ?? []), m])
    }
    return [...groups].map(([id, ms]) => {
      const t = ms[0].target!
      return {
        key: id,
        latDeg: t.latDeg,
        lonDeg: t.lonDeg,
        dashed: t.coordinateKind !== 'actual_landing',
        label: `${ms.map((m) => m.name).join(', ')}: ${t.name}, ${coordinateKindWords(t.coordinateKind, ms[0].targetName)}`,
        highlighted: id === siteId,
        pressed: id === siteId,
      }
    })
  }, [showMissions, missions.data, siteId])
  const missionsHere = (missions.data?.items ?? []).filter((m) => m.siteId === siteId)

  const filtersOn = (minSun > 0 ? 1 : 0) + (Number.isFinite(maxDark) ? 1 : 0) + (nearPsr ? 1 : 0) + (showMissions ? 1 : 0)

  return (
    <div className="flex grow flex-col">
      <div className="flex flex-wrap items-center gap-x-10 gap-y-3 border-b border-line pw-page py-4">
        <div className="flex min-w-0 flex-col gap-0.5 lg:max-w-sm">
          <h1 className="text-title-lg font-semibold tracking-title text-ink">Candidate landing sites</h1>
          <p className="text-small leading-5 text-ink-2">Spots near the south pole, measured for sunlight and contact with Earth. Choose one on the map or in the list.</p>
        </div>
        <div className="basis-full lg:basis-0 lg:grow">
          <DateSlider />
        </div>
      </div>

      <div className="flex grow flex-col gap-4 pw-page py-5 lg:flex-row lg:items-start lg:gap-6 lg:py-6">
        {/* On a phone the map comes first and the chosen site's numbers right
            under it, so a tap on a pin shows its answer without scrolling. */}
        <aside className="order-3 flex w-full shrink-0 flex-col gap-3 lg:order-none lg:w-[280px]" aria-label="Search and filters">
          <SearchField value={query} onChange={setQuery} />

          <Disclosure title="Filters" meta={filtersOn ? `${filtersOn} on` : undefined}>
            <Slider
              id="f-sun"
              label="Sunlight at least"
              value={minSun}
              display={`${minSun}%`}
              min={0}
              max={100}
              onChange={setMinSun}
              tone="bg-sun-fill"
            />
            <Slider
              id="f-dark"
              label="Longest night under"
              value={Number.isFinite(maxDark) ? maxDark : darkMax || 24}
              display={Number.isFinite(maxDark) ? `${maxDark} h` : 'Any'}
              min={24}
              max={darkMax || 24}
              step={24}
              disabled={!darkMax}
              valueText={Number.isFinite(maxDark) ? `${maxDark} hours` : 'Any length'}
              onChange={(v) => setMaxDark(v >= darkMax ? Infinity : v)}
              tone="bg-terrain-high"
            />
            <div className="flex flex-wrap gap-2">
              <Chip selected={nearPsr} onClick={() => setNearPsr((v) => !v)} tone="neutral">
                Beside a shadowed crater
              </Chip>
              <Chip selected={showMissions} onClick={() => setShowMissions((v) => !v)} tone="neutral">
                Show mission landing spots
              </Chip>
            </div>
          </Disclosure>

          <Panel className="relative flex flex-col lg:max-h-[560px] lg:overflow-y-auto">
            <div className="sticky top-0 z-10 flex items-baseline justify-between border-b border-line bg-panel px-4 py-3">
              <SectionLabel>Sites</SectionLabel>
              <span className="text-caption text-ink-2" aria-live="polite">
                {matches.length} of {candidates.length}
              </span>
            </div>
            {matches.length === 0 ? (
              <EmptyState
                title="No site clears every filter"
                detail={
                  <>
                    {candidates.length} sites checked. The one ruling them out is <strong className="text-ink">{binding}</strong>.
                  </>
                }
                primary={
                  Number.isFinite(maxDark)
                    ? { label: 'Allow a night of any length', onClick: () => setMaxDark(Infinity) }
                    : undefined
                }
                secondary={{
                  label: 'Clear all filters',
                  onClick: () => {
                    setMinSun(0)
                    setMaxDark(Infinity)
                    setNearPsr(false)
                    setQuery('')
                  },
                }}
              />
            ) : (
              matches.map((s) => {
                const m = metrics[s.id]
                const active = s.id === siteId
                return (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => setSite(s.id)}
                    aria-current={active ? 'true' : undefined}
                    className={`flex flex-col gap-0.5 border-b border-line px-4 py-2.5 text-left last:border-b-0 ${
                      active ? 'bg-inset shadow-[inset_3px_0_0_var(--color-ink)]' : 'hover:bg-inset'
                    }`}
                  >
                    <span className="flex items-baseline gap-2 text-body font-semibold text-ink">
                      <span className="w-4 shrink-0 font-mono text-caption text-ink-3" aria-hidden="true">
                        {s.code}
                      </span>
                      {s.name}
                    </span>
                    <span className="pl-6 text-caption text-ink-3 tnum">
                      {m ? (
                        <>
                          <span className="text-sun">{percent(m.sun.fractionUp)}</span> sun ·{' '}
                          <span className="text-earth">{percent(m.earth.fractionUp)}</span> contact · night{' '}
                          <span className={m.sun.longestDownH > SURVIVAL_LIMIT_H ? 'text-alert' : 'text-ink-2'}>
                            {bound(m.sun.longestDownOpen)}
                            {Math.round(m.sun.longestDownH)} h
                          </span>
                        </>
                      ) : (
                        'working out…'
                      )}
                    </span>
                  </button>
                )
              })
            )}
          </Panel>
        </aside>

        <section data-guide="map" className="order-1 flex min-w-0 grow flex-col border border-line bg-panel lg:order-none">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-line px-4 py-3">
            <h2 className="text-control font-semibold text-ink">The south pole from above</h2>
            <span className="text-caption text-ink-3">80°S to the pole · choose a site</span>
          </div>

          <div className="flex items-start justify-center p-3">
            <PolarMap
              sun={sun}
              selectedSiteId={siteId}
              onSelect={setSite}
              size={640}
              sites={candidates}
              missionPins={missionPins}
              poleView
              // Targets drawn together share one button: each press moves to
              // the next of them, so every one is reachable.
              onMissionPin={(keys) => setSite(keys[(keys.indexOf(siteId) + 1) % keys.length])}
            />
          </div>

          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-line px-4 py-3">
            <LegendSwatch className="bg-terrain-mid">Terrain (LOLA, 80 m)</LegendSwatch>
            <LegendSwatch className="bg-psr">In shadow now, if the ground were flat</LegendSwatch>
            <LegendSwatch className="hatch-uncertain">Shadow-line margin</LegendSwatch>
          </div>
        </section>

        <aside className="order-2 flex w-full shrink-0 flex-col gap-4 lg:order-none lg:w-[300px]">
          {error && !focused ? (
            <ProblemPanel error={error} fallbackTitle="Cannot compute this site" />
          ) : compute.status === 'running' && !focused ? (
            <LoadingPanel done={done} total={total} />
          ) : (
            <Panel elevated className="flex flex-col">
              <div className="flex flex-col gap-0.5 border-b border-line p-4">
                <div className="text-title font-semibold">
                  <span className="mr-2 font-mono text-body text-ink-3">{site.code}</span>
                  {site.name}
                </div>
                <div className="font-mono text-tag text-ink-3">{coords(site.latDeg, site.lonDeg)}</div>
              </div>
              <SiteNumbers metrics={focused} />
              <div className="flex flex-col gap-2.5 border-t border-line p-4">
                <p className="text-small leading-5 text-ink-2">{site.note}</p>
                {missionsHere.length > 0 && (
                  <p className="text-small leading-5 text-ink-2">
                    CLPS {missionsHere.length === 1 ? 'mission' : 'missions'} aiming here:{' '}
                    {missionsHere.map((m, i) => (
                      <span key={m.id}>
                        {i > 0 && ', '}
                        <Link to={`/missions/${m.id}`}>{m.name}</Link>
                      </span>
                    ))}
                  </p>
                )}
                <Link
                  to="/site"
                  className="inline-flex h-12 items-center justify-center rounded-control bg-ink text-control font-semibold text-canvas no-underline hover:bg-ink-2"
                >
                  Open the site page
                </Link>
                <Button
                  onClick={() => useMission.getState().toggleCompare(site.id)}
                  disabled={inCompare && compareCount <= 2}
                  title={inCompare && compareCount <= 2 ? 'A comparison needs at least two sites' : undefined}
                >
                  {inCompare ? '✓ In Compare' : 'Add to Compare'}
                </Button>
              </div>
            </Panel>
          )}
        </aside>
      </div>
    </div>
  )
}

/**
 * The four numbers as label and value rows: the rail is too narrow for the
 * tiles, whose long labels wrapped onto four lines there.
 */
function SiteNumbers({ metrics: m }: { metrics: SiteMetrics | undefined }) {
  if (!m) return <p className="p-4 text-small text-ink-3">Working out the numbers…</p>
  const over = m.sun.longestDownH > SURVIVAL_LIMIT_H
  const rows: { label: string; value: string; extra?: string; tone: string }[] = [
    { label: 'Time in sunlight', value: `${Math.round(m.sun.upHours)} h`, extra: percent(m.sun.fractionUp), tone: 'text-sun' },
    {
      label: 'Time in contact with Earth',
      value: `${Math.round(m.earth.upHours)} h`,
      extra: percent(m.earth.fractionUp),
      tone: 'text-earth',
    },
    {
      label: 'Longest night',
      value: m.sun.longestDownArc ? `${bound(m.sun.longestDownOpen)}${Math.round(m.sun.longestDownH)} h` : 'none',
      extra: over ? `over the ${SURVIVAL_LIMIT_H} h battery limit` : undefined,
      tone: over ? 'text-alert' : 'text-ink',
    },
    {
      label: 'Longest time without contact',
      value: m.earth.longestDownArc ? `${bound(m.earth.longestDownOpen)}${Math.round(m.earth.longestDownH)} h` : 'none',
      tone: 'text-ink',
    },
  ]
  return (
    <dl className="flex flex-col px-4 py-2">
      {rows.map((r) => (
        <div key={r.label} className="flex items-baseline justify-between gap-3 border-b border-line py-2 last:border-b-0">
          <dt className="text-small text-ink-2">{r.label}</dt>
          <dd className="flex flex-col items-end text-right">
            <span className={`text-title font-semibold tnum ${r.tone}`}>{r.value}</span>
            {r.extra && <span className="text-caption text-ink-3">{r.extra}</span>}
          </dd>
        </div>
      ))}
    </dl>
  )
}

function LegendSwatch({ children, className }: { children: React.ReactNode; className: string }) {
  return (
    <span className="flex items-center gap-2 text-caption text-ink">
      <span className={`h-3 w-5.5 border border-line-strong ${className}`} aria-hidden="true" />
      {children}
    </span>
  )
}

function Slider({
  id,
  label,
  value,
  display,
  min,
  max,
  step = 1,
  onChange,
  tone,
  disabled = false,
  valueText,
}: {
  id: string
  label: string
  value: number
  display: string
  min: number
  max: number
  step?: number
  onChange: (v: number) => void
  tone: string
  disabled?: boolean
  valueText?: string
}) {
  const pct = max > min ? ((value - min) / (max - min)) * 100 : 100
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-small font-medium text-ink">
        {label} <span className="font-mono text-sun">{display}</span>
      </label>
      <div className="relative flex h-12 items-center">
        <div className="absolute inset-x-0 h-[3px] bg-inset" />
        <div className={`absolute left-0 h-[3px] ${tone}`} style={{ width: `${pct}%` }} />
        <div
          className={`pointer-events-none absolute size-4 -translate-x-1/2 rounded-pill border-2 bg-canvas ${tone.replace('bg-', 'border-')}`}
          style={{ left: `${pct}%` }}
        />
        <input
          id={id}
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          disabled={disabled}
          aria-valuetext={valueText}
          onChange={(e) => onChange(Number(e.target.value))}
          className="absolute inset-x-0 h-12 w-full cursor-pointer opacity-0 disabled:cursor-not-allowed"
        />
      </div>
    </div>
  )
}
