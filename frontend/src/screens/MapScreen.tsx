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
import { KeyNumberRow } from '../components/KeyNumbers'
import { EmptyState, LoadingPanel, ProblemPanel } from '../components/States'
import { Button, Chip, Panel, SearchField, SectionLabel } from '../components/ui'
import { bound, coords, percent } from '../lib/format'
import { SURVIVAL_LIMIT_H } from '../lib/geometry/metrics'
import { coordinateKindWords } from '../lib/missions'
import type { Mission } from '../lib/api/adapters'
import type { SiteMetrics } from '../lib/types'

/** S1 — where you start: pick a site, see the terminator sweep across the pole. */
export function MapScreen() {
  const { siteId, setSite, cursorH, windowStartH, face } = useMission(
    useShallow((s) => ({
      siteId: s.siteId,
      setSite: s.setSite,
      cursorH: s.cursorH,
      windowStartH: s.windowStartH,
      face: s.face,
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
        ? `longest dark gap under ${maxDark} h`
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

  return (
    <div className="flex grow flex-col">
      <div className="flex flex-wrap items-center gap-x-8 gap-y-3 border-b border-line px-4 py-4 lg:px-6">
        <DateSlider />
      </div>

      <div className="flex grow flex-col gap-4 p-4 lg:flex-row lg:gap-6 lg:p-6">
        {face === 'planner' && (
          <aside className="flex w-full shrink-0 flex-col gap-4 lg:w-[260px]" aria-label="Search and filters">
            <SearchField value={query} onChange={setQuery} />

            <Panel className="flex flex-col gap-5 p-4">
              <SectionLabel>Filters</SectionLabel>

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

              <div className="flex flex-wrap gap-2 border-t border-line pt-4">
                <Chip selected={nearPsr} onClick={() => setNearPsr((v) => !v)} tone="earth">
                  Beside a shadowed floor
                </Chip>
                <p className="text-[12px] leading-[17px] text-ink-3">
                  Sites on the rim of a named polar crater, next to its permanently shadowed floor.
                </p>
              </div>
              <div className="flex flex-wrap gap-2 border-t border-line pt-4">
                <Chip selected={showMissions} onClick={() => setShowMissions((v) => !v)} tone="neutral">
                  Mission targets
                </Chip>
                <p className="text-[12px] leading-[17px] text-ink-3">
                  Adds the CLPS targets inside 80°S as diamonds. Choose one to see its numbers here.
                </p>
              </div>
            </Panel>

            <Panel className="flex grow flex-col">
              <div className="flex items-baseline justify-between border-b border-line px-4 py-3">
                <SectionLabel>Matching sites</SectionLabel>
                  <span className="text-[12px] text-ink-2" aria-live="polite">
                  {matches.length} of {candidates.length}
                </span>
              </div>
              {matches.length === 0 ? (
                <EmptyState
                  title="No site clears every filter"
                  detail={
                    <>
                      {candidates.length} sites checked. The binding one is <strong className="text-ink">{binding}</strong>.
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
                      className={`flex flex-col gap-1 border-b border-line px-4 py-3 text-left last:border-b-0 ${
                        active ? 'bg-inset' : 'hover:bg-inset'
                      }`}
                    >
                      <span className="text-[14px] font-semibold text-ink">
                        {s.code} — {s.name}
                      </span>
                      <span className="font-mono text-[11px] text-ink-3">
                        {m
                          ? `sun ${percent(m.sun.fractionUp)} · call home ${percent(m.earth.fractionUp)} · night `
                          : 'computing…'}
                        {m && (
                          <span className={m.sun.longestDownH > SURVIVAL_LIMIT_H ? 'text-alert' : ''}>
                            {bound(m.sun.longestDownOpen)}
                            {Math.round(m.sun.longestDownH)} h
                          </span>
                        )}
                      </span>
                    </button>
                  )
                })
              )}
            </Panel>
          </aside>
        )}

        <section className="flex grow flex-col border border-line bg-panel">
          <div className="flex items-center gap-4 border-b border-line px-4 py-3">
            <SectionLabel>South polar stereographic · 80°S to the pole</SectionLabel>
            <span className="ml-auto text-[12px] text-ink-3">relief from LOLA; shadow on a smooth Moon</span>
          </div>

          <div className="flex grow items-start justify-center p-3">
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

          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-line px-4 py-3">
            <LegendSwatch className="bg-terrain-mid">Relief: LOLA hillshade, 80 m</LegendSwatch>
            <LegendSwatch className="bg-psr">Sun down at this instant, smooth Moon</LegendSwatch>
            <LegendSwatch className="hatch-uncertain">Shadow-line margin</LegendSwatch>
            <p className="ml-auto max-w-[360px] text-right text-[12px] leading-[17px] text-ink-3">
              The shadow line is where the Sun sets on a smooth Moon, from the same SPICE Sun as every number.
              Ridges and craters are not shaded here; each site’s own skyline decides its numbers.
            </p>
          </div>
        </section>

        <aside className="flex w-full shrink-0 flex-col gap-4 lg:w-[320px]">
          {error && !focused ? (
            <ProblemPanel error={error} fallbackTitle="Cannot compute this site" />
          ) : compute.status === 'running' && !focused ? (
            <LoadingPanel done={done} total={total} />
          ) : (
            <Panel elevated className="flex flex-col">
              <div className="flex items-start gap-3 border-b border-line p-4">
                <span className="inline-flex size-7 shrink-0 items-center justify-center bg-sun-fill text-[14px] font-bold text-on-sun">
                  {site.code}
                </span>
                <div className="flex min-w-0 flex-col gap-0.5">
                  <div className="text-[17px] font-semibold">{site.name}</div>
                  <div className="font-mono text-[11px] text-ink-3">{coords(site.latDeg, site.lonDeg)}</div>
                </div>
              </div>
              <div className="p-4">
                <KeyNumberRow metrics={focused} face={face} size="sm" columns={2} />
              </div>
              <div className="flex flex-col gap-2.5 border-t border-line p-4">
                <p className="text-[13px] leading-5 text-ink-2">{site.note}</p>
                {missionsHere.length > 0 && (
                  <p className="text-[13px] leading-5 text-ink-2">
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
                  to="/clocks"
                  className="inline-flex h-12 items-center justify-center rounded-control bg-sun-fill text-[15px] font-semibold text-on-sun no-underline"
                >
                  Open in Site view
                </Link>
                <Button onClick={() => useMission.getState().toggleCompare(site.id)}>Add to compare</Button>
              </div>
            </Panel>
          )}

          <Panel className="mt-auto flex flex-col gap-2 p-4">
            <SectionLabel>Keyboard</SectionLabel>
            <p className="font-mono text-[11px] leading-[19px] text-ink-2">
              [ ] step the date by 6 h
              <br />
              ⇧[ ⇧] step by one day
              <br />
              1 2 3 Simple, Explain, Expert
              <br />
              T read the current chart as a table
            </p>
            <p className="text-[12px] leading-[18px] text-ink-3">Single-key shortcuts can be turned off in Settings.</p>
          </Panel>
        </aside>
      </div>
    </div>
  )
}

function LegendSwatch({ children, className }: { children: React.ReactNode; className: string }) {
  return (
    <span className="flex items-center gap-2 text-[12px] text-ink">
      <span className={`h-3 w-5.5 ${className}`} aria-hidden="true" />
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
      <label htmlFor={id} className="text-[13px] font-medium text-ink">
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
