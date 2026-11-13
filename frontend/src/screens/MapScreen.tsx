import { useMemo, useState } from 'react'
import { RidgeArt } from '../landing/Illustrations'
import { Link } from 'react-router-dom'
import { useTransitionClick } from '../lib/viewTransition'
import { useShallow } from 'zustand/react/shallow'
import { useSiteMetricsMap } from '../lib/useMetricsMap'
import { useMission } from '../lib/store'
import { useSubSolar } from '../lib/mission'
import { getCandidates, siteById } from '../lib/sites'
import { useMissions } from '../lib/api/queries'
import { PolarMap, type MissionPin } from '../components/PolarMap'
import { DateSlider } from '../components/DateSlider'
import { EmptyState, LoadingPanel, ProblemPanel } from '../components/States'
import { Button, Chip, Disclosure, Eyebrow, Panel, PillArrow, SearchField, pillClass } from '../components/ui'
import { PageHeader } from '../components/Page'
import { Icon } from '../components/Icon'
import { ShareRing } from '../components/ShareRing'
import { bound, coords, percent, plusMinus } from '../lib/format'
import { limitWords, longestNight, nightAgainstLimit, nightMargin } from '../lib/geometry/metrics'
import { useBatteryLimit } from '../lib/api/lifecycleQueries'
import { coordinateKindWords } from '../lib/missions'
import type { Mission } from '../lib/api/adapters'
import type { SiteMetrics } from '../lib/types'

/** S1 — where you start: pick a site, see the terminator sweep across the pole. */
export function MapScreen() {
  const limit = useBatteryLimit()
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
  const go = useTransitionClick()

  const filtersOn = (minSun > 0 ? 1 : 0) + (Number.isFinite(maxDark) ? 1 : 0) + (nearPsr ? 1 : 0) + (showMissions ? 1 : 0)

  return (
    <div className="pw-page flex grow flex-col gap-6 pt-6 pb-8 lg:gap-8 lg:pt-8">
      <PageHeader
        compact
        title="Landing sites"
        lede="Sites near the south pole, measured for sunlight and contact with Earth. Choose one on the map or in the list."
      />
      <DateSlider />

      <div className="flex grow flex-col gap-6 lg:flex-row lg:items-start">
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

          <Panel quiet flush className="relative flex flex-col lg:max-h-[600px] lg:overflow-y-auto">
            <div className="sticky top-0 z-10 flex items-baseline justify-between border-b border-line bg-panel px-4 py-3">
              <Eyebrow as="h2">Sites</Eyebrow>
              <span className="text-caption text-ink-2" aria-live="polite">
                {matches.length} of {candidates.length}
              </span>
            </div>
            {matches.length === 0 ? (
              <EmptyState
                art={<RidgeArt />}
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
                    className={`flex items-center gap-3 rounded-none border-b border-line px-4 py-2.5 text-left last:border-b-0 ${
                      active ? 'bg-inset shadow-[inset_3px_0_0_var(--color-ink)]' : 'hover:bg-inset'
                    }`}
                  >
                    <span className="flex min-w-0 grow flex-col gap-0.5">
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
                          <span className={m.sun.longestDownH > limit.h ? 'text-alert' : 'text-ink-2'}>
                            {bound(m.sun.longestDownOpen)}
                            {Math.round(m.sun.longestDownH)} h
                          </span>
                        </>
                      ) : (
                        'working out…'
                      )}
                    </span>
                    </span>
                    {m && <ShareRing sun={m.sun.fractionUp} earth={m.earth.fractionUp} />}
                  </button>
                )
              })
            )}
          </Panel>
        </aside>

        {/* The page's hero: the pole on the real relief, the Sun's shadow line sweeping across it. */}
        <Panel as="section" guide="map" flush className="order-1 flex min-w-0 grow flex-col lg:order-none">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-4 pt-4 sm:px-5">
            <Eyebrow as="h2">The south pole from above</Eyebrow>
            <span className="text-caption text-ink-3">choose a site on the map</span>
          </div>

          <div className="flex items-start justify-center p-2 sm:p-3">
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

          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 px-4 pb-4 sm:px-5">
            <LegendSwatch className="bg-terrain-mid">The ground: NASA’s LRO photograph over the LOLA terrain</LegendSwatch>
            <LegendSwatch className="bg-psr">In shadow now, if the ground were flat</LegendSwatch>
            <LegendSwatch className="hatch-uncertain">Shadow-line margin</LegendSwatch>
          </div>
          <p className="px-4 pb-4 text-caption leading-caption text-ink-3 sm:px-5">
            The photograph’s own shadows are from the days it was taken. Sunlight for your dates is the amber line and
            the shaded side.
          </p>
        </Panel>

        <aside className="order-2 flex w-full shrink-0 flex-col gap-4 lg:order-none lg:w-[300px]">
          {error && !focused ? (
            <ProblemPanel error={error} fallbackTitle="Cannot compute this site" />
          ) : compute.status === 'running' && !focused ? (
            <LoadingPanel done={done} total={total} />
          ) : (
            <Panel elevated className="flex flex-col">
              <div className="flex flex-col gap-1 p-5 pb-4">
                <Eyebrow>Chosen site</Eyebrow>
                <div className="text-heading leading-7 font-semibold tracking-heading">
                  <span className="mr-2 font-mono text-body font-normal text-ink-3">{site.code}</span>
                  {/* Grows into the site page's title when that page is opened from here (rule 5). */}
                  <span data-pw-carry="pw-site-name">{site.name}</span>
                </div>
                <div className="font-mono text-caption text-ink-3">{coords(site.latDeg, site.lonDeg)}</div>
              </div>
              <SiteNumbers metrics={focused} />
              <div className="flex flex-col gap-3 p-5 pt-4">
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
                <Link to="/site" onClick={go('/site', undefined, 'pw-site-name')} className={pillClass('primary', true)}>
                  Open the site page
                  <PillArrow />
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
 * The four numbers as small figures, two by two: the rail is too narrow for
 * the tiles, whose long labels wrapped onto four lines there.
 */
function SiteNumbers({ metrics: m }: { metrics: SiteMetrics | undefined }) {
  const limit = useBatteryLimit()
  if (!m) return <p className="px-5 py-4 text-small text-ink-3">Working out the numbers…</p>
  // The same rule as Site and Compare: magenta only past the limit by more than the margin.
  const against = nightAgainstLimit(longestNight(m), limit.h)
  const over = against.kind === 'past'
  // A margin beside a figure the dates did not cut short, as on the tiles (a cut-short figure is a lower bound).
  const margin = (w: SiteMetrics['sun'], h: number | undefined) => (w.longestDownArc && !w.longestDownOpen && h !== undefined ? plusMinus(h) : undefined)
  const blackoutMargin = m.earth.longestDownArc && !m.earth.longestDownArc.grazing ? m.earth.longestDownToleranceH : undefined
  const rows: { label: string; value: string; margin?: string; unit?: string; extra?: string; tone: string; alert?: boolean }[] = [
    { label: 'Time in sunlight', value: `${Math.round(m.sun.upHours)}`, unit: 'h', extra: percent(m.sun.fractionUp), tone: 'text-sun' },
    {
      label: 'Time in contact with Earth',
      value: `${Math.round(m.earth.upHours)}`,
      unit: 'h',
      extra: percent(m.earth.fractionUp),
      tone: 'text-earth',
    },
    {
      label: 'Longest night',
      value: m.sun.longestDownArc ? `${bound(m.sun.longestDownOpen)}${Math.round(m.sun.longestDownH)}` : 'none',
      margin: margin(m.sun, nightMargin(m)),
      unit: m.sun.longestDownArc ? 'h' : undefined,
      extra: over ? `over ${limitWords(limit)}` : against.kind === 'within-margin' ? `within the margin of ${limitWords(limit)}` : undefined,
      tone: over ? 'text-alert' : 'text-ink',
      alert: over,
    },
    {
      label: 'Longest time without contact',
      value: m.earth.longestDownArc ? `${bound(m.earth.longestDownOpen)}${Math.round(m.earth.longestDownH)}` : 'none',
      margin: margin(m.earth, blackoutMargin),
      unit: m.earth.longestDownArc ? 'h' : undefined,
      tone: 'text-ink',
    },
  ]
  return (
    <dl className="mx-5 grid grid-cols-2 gap-x-4 gap-y-4 border-y border-line py-4">
      {rows.map((r) => (
        <div key={r.label} className="flex min-w-0 flex-col gap-1">
          <dt className={`flex min-h-8 items-start gap-1.5 text-caption leading-4 ${r.alert ? 'text-alert' : 'text-ink-2'}`}>
            {r.alert && <Icon name="alert" size={12} strokeWidth={2.4} className="mt-0.5 shrink-0" />}
            {r.label}
          </dt>
          <dd className="flex flex-col">
            <span className={`pw-figure text-[26px] leading-7 ${r.tone}`}>
              {r.value}
              {r.margin && <span className="ml-1 text-small font-normal tracking-normal text-uncertain tnum [font-stretch:100%]">{r.margin}</span>}
              {r.unit && <span className="ml-1 text-body font-normal tracking-normal text-ink-2 [font-stretch:100%]">{r.unit}</span>}
            </span>
            {r.extra && <span className={`text-caption leading-4 ${r.alert ? 'text-alert' : 'text-ink-3'}`}>{r.extra}</span>}
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
        {label} <span className={`font-mono ${tone === 'bg-sun-fill' ? 'text-sun' : 'text-ink'}`}>{display}</span>
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
