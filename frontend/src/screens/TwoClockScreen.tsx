import { useId } from 'react'
import { Link } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { useMission } from '../lib/store'
import { useFocusedMetrics, useFocusedView } from '../lib/mission'
import { Sources } from '../components/Sources'
import { siteById } from '../lib/sites'
import { DateSlider } from '../components/DateSlider'
import { SiteTitle } from '../components/SitePicker'
import { TERRAIN_BLOCKER_MIN_EL_DEG, TwoClockRings } from '../components/TwoClockRings'
import { KeyNumberRow } from '../components/KeyNumbers'
import { ArcTable } from '../components/ArcTable'
import { ProblemPanel, Skeleton, UncertaintyNote } from '../components/States'
import { Button, Disclosure, Panel, PillArrow, pillClass } from '../components/ui'
import { ANSWER_TEXT, Rows, UNDER_QUESTION } from '../components/lifecycle/Section'
import { surfaceSentence } from '../lib/siteSentence'
import { DomeCard } from '../scenes/DomeCard'
import { useMotionClass } from '../hooks/useMotion'
import { Icon } from '../components/Icon'
import { WindowPicker } from '../components/WindowPicker'
import { SummarySpeaker } from '../components/SummarySpeaker'
import { ExplainPanel } from '../components/Agents'
import { useWindowParams } from '../lib/mission'
import { bearing, compassWords, coords, degrees, edgeMargin, hoursWithUnit, msFromModelH, windowLine } from '../lib/format'
import type { SiteMetrics } from '../lib/types'
import type { Meta } from '../lib/api/adapters'

/**
 * S2, "Site" in the navigation: one site over the chosen dates.
 *
 * Answer first: the four numbers, then the ring that shows when they happen.
 * Everything else (what blocks the Sun, how sure the numbers are, other
 * dates, a written description) is one closed row each, opened on request.
 */
export function TwoClockScreen() {
  const view = useFocusedView()
  const w = useWindowParams()
  const { siteId, cursorH, windowStartH, windowHours, showTable } = useMission(
    useShallow((s) => ({
      siteId: s.siteId,
      cursorH: s.cursorH,
      windowStartH: s.windowStartH,
      windowHours: s.windowHours,
      showTable: s.tableOpen,
    })),
  )
  const metrics = useFocusedMetrics()
  const site = siteById(siteId)
  const terrainModelled = view.meta?.uncertainty.terrainModelled ?? site.terrainModelled
  const questionId = useId()
  const arrive = useMotionClass('pw-arrive')

  return (
    <div className="pw-page flex grow flex-col gap-6 pt-6 pb-8 lg:gap-8 lg:pt-8">
      <header className="flex min-w-0 flex-col gap-1.5">
        <SiteTitle />
        <span className="font-mono text-caption text-ink-3">
          {coords(site.latDeg, site.lonDeg)} · {site.elevM !== null ? `height ${site.elevM.toLocaleString()} m` : 'height not known'}
        </span>
      </header>
      <DateSlider />

      <section aria-labelledby={questionId} className="flex min-w-0 flex-col gap-7 lg:gap-8">
        <h2 id={questionId} className="pw-eyebrow">
          What does this spot get over these dates?
        </h2>
        {metrics && !view.error ? (
          <div className={`${UNDER_QUESTION} flex flex-col gap-3 ${arrive}`}>
            <p className={ANSWER_TEXT}>{surfaceSentence(metrics)}</p>
            <div data-guide="listen" className="pt-1">
              <SummarySpeaker view={view} />
            </div>
          </div>
        ) : view.error ? null : (
          <div className={`${UNDER_QUESTION} flex flex-col gap-2.5`} aria-hidden="true">
            <Skeleton className="h-8 w-full max-w-4xl lg:h-10" />
            <Skeleton className="h-8 w-1/2 max-w-xl lg:h-10" />
          </div>
        )}
        {!terrainModelled && (
          <UncertaintyNote className="-mt-2">
            No terrain data outside 80°S, so the Sun and Earth are worked out as if the ground were flat. Real hills
            could block more.
          </UncertaintyNote>
        )}
        {view.error ? (
          <div className="w-full max-w-2xl">
            <ProblemPanel error={view.error} fallbackTitle="Cannot compute this site" onRetry={view.refetch} />
          </div>
        ) : (
          <KeyNumberRow metrics={metrics} uncertain={!terrainModelled} />
        )}

        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,600px)_minmax(0,1fr)] lg:gap-8">
          {metrics && !view.error ? (
            <Panel as="section" guide="rings" className="flex min-w-0 flex-col items-center gap-5 p-4 sm:p-6">
              <h3 className="self-start text-title leading-6 font-semibold tracking-title text-ink">
                These dates as a clock
              </h3>
              <TwoClockRings metrics={metrics} cursorH={cursorH} maxSize={480} />
              <RingKey />
            </Panel>
          ) : (
            <div />
          )}

          <div className="flex min-w-0 flex-col gap-7 lg:gap-8">
          <Rows
            about={
              <Disclosure title="How sure is this?" meta="margins, sources, table">
                <HowSure metrics={metrics} meta={view.meta} terrainModelled={terrainModelled} />
              </Disclosure>
            }
          >
            <Disclosure title="What blocks the Sun and Earth here?">
              <Blockers metrics={metrics} failed={Boolean(view.error)} />
            </Disclosure>
            <Disclosure title="Change the dates" meta={windowLine(msFromModelH(windowStartH), windowHours)}>
              <WindowPicker siteId={siteId} />
            </Disclosure>
            <ExplainPanel siteId={siteId} start={w.start} end={w.end} />
          </Rows>
          {metrics && !view.error && <DomeCard metrics={metrics} cursorH={cursorH} />}
          </div>
        </div>

        <nav aria-label="More about this site" className="flex flex-wrap items-center gap-3">
          <Link to="/plan" className={pillClass('primary', true)}>
            Plan for time without contact
            <PillArrow />
          </Link>
          <Link to="/skyline" className={pillClass('secondary')}>
            See the skyline
          </Link>
          <Link to="/report" className={pillClass('ghost')}>
            Printable report
          </Link>
        </nav>
      </section>

      {showTable && metrics && <ArcTable metrics={metrics} />}
    </div>
  )
}

/** What causes the longest night and the longest time without contact: a ridge, or the horizon itself. */
function Blockers({ metrics, failed }: { metrics: SiteMetrics | undefined; failed: boolean }) {
  if (failed) return <p className="text-small text-ink-2">Not available: the numbers for these dates did not load.</p>
  if (!metrics) return <p className="text-small text-ink-3">Working out the skyline…</p>
  const worst = metrics.sun.longestDownArc
  const worstOpen = Boolean(metrics.sun.longestDownOpen)
  const byTerrain = worst?.blockedByElDeg !== undefined && worst.blockedByElDeg > TERRAIN_BLOCKER_MIN_EL_DEG
  const blackout = metrics.earth.longestDownArc
  const blackoutOpen = Boolean(metrics.earth.longestDownOpen)
  const blackoutByTerrain =
    blackout?.blockedByElDeg !== undefined && blackout.blockedByElDeg > TERRAIN_BLOCKER_MIN_EL_DEG
  const distance = (az: number) =>
    Math.round(metrics.mask.rangeM[Math.round(az) % metrics.mask.rangeM.length]).toLocaleString()

  return (
    <>
      <div className="flex gap-2.5">
        <div className="w-[3px] shrink-0 bg-sun-fill" />
        <p className="text-small leading-5 text-ink">
          {!worst ? (
            'The Sun stays above this site’s skyline on all of these dates. Choose longer dates to find its nights.'
          ) : byTerrain ? (
            <>
              The {hoursWithUnit(worst.hours, 0, worstOpen)} night comes from a ridge to the{' '}
              {compassWords(worst.blockedByBearingDeg ?? 0)} ({bearing(worst.blockedByBearingDeg ?? 0)}),{' '}
              {degrees(worst.blockedByElDeg ?? 0, 2)} above level and {distance(worst.blockedByBearingDeg ?? 0)} m
              away.
            </>
          ) : (
            <>
              The {hoursWithUnit(worst.hours, 0, worstOpen)} night is the Sun going below the horizon itself; no
              ridge is involved.
            </>
          )}
          {worst && worstOpen ? ' These dates cut it short, so the night itself is longer.' : ''}
        </p>
      </div>
      <div className="flex gap-2.5">
        <div className="w-[3px] shrink-0 bg-earth-fill" />
        <p className="text-small leading-5 text-ink">
          {!blackout ? (
            'Earth stays above this site’s skyline on all of these dates.'
          ) : blackoutByTerrain ? (
            <>
              The {hoursWithUnit(blackout.hours, 0, blackoutOpen)} without contact comes from a ridge to the{' '}
              {compassWords(blackout.blockedByBearingDeg ?? 0)} ({bearing(blackout.blockedByBearingDeg ?? 0)}), once
              the Moon’s wobble (libration) carries Earth low.
            </>
          ) : (
            <>
              The {hoursWithUnit(blackout.hours, 0, blackoutOpen)} without contact is Earth going below the horizon
              itself, as the Moon’s wobble (libration) carries it down.
            </>
          )}
        </p>
      </div>
      <Link to="/skyline" className="self-start text-small font-semibold">
        See it on the skyline →
      </Link>
    </>
  )
}

function HowSure({
  metrics,
  meta,
  terrainModelled,
}: {
  metrics: SiteMetrics | undefined
  meta: Meta | undefined
  terrainModelled: boolean
}) {
  const toggleTable = useMission((s) => s.toggleTable)
  const showTable = useMission((s) => s.tableOpen)
  const worst = metrics?.sun.longestDownArc
  return (
    <>
      {metrics && meta && (
        <p className="text-small leading-5 text-ink-2">
          {terrainModelled
            ? `Terrain heights can be off by up to ±${meta.uncertainty.demVerticalErrorM} m. `
            : 'No terrain data here, so the skyline is a flat horizon; real hills could block more. '}
          {worst?.grazing ? (
            'The longest night starts or ends with the Sun only skimming the skyline, too shallow to time precisely.'
          ) : (
            <>
              The longest night has <span className="font-semibold text-ink">{edgeMargin(worst, terrainModelled)}</span>,
              counting both of its ends.
            </>
          )}
          {meta.uncertainty.partialCoverage && meta.uncertainty.terrainModelled
            ? ` Terrain covers only ${(meta.uncertainty.coverage * 100).toFixed(0)}% of the directions around this site; the rest assume flat ground, so these numbers are likely too hopeful.`
            : ''}
        </p>
      )}
      <Sources meta={meta} />
      <div className="flex flex-wrap items-center gap-3">
        <Button size="sm" onClick={toggleTable} expanded={showTable}>
          <Icon name="table" size={16} strokeWidth={1.7} />
          {showTable
            ? 'Hide the table'
            : `Show every stretch as a table${metrics ? ` (${metrics.sun.arcs.length + metrics.earth.arcs.length})` : ''}`}
        </Button>
        <span className="text-caption text-ink-3">or press T</span>
      </div>
    </>
  )
}

function RingKey() {
  return (
    <ul className="flex flex-wrap justify-center gap-x-5 gap-y-2 text-caption text-ink-2">
      <KeyItem swatch={<span className="h-3 w-5 bg-sun-fill" />}>Outer ring: Sun up</KeyItem>
      <KeyItem swatch={<span className="h-3 w-5 bg-earth-fill" />}>Inner ring: Earth up</KeyItem>
      <KeyItem swatch={<span className="hatch-blocked h-3 w-5" />}>Blocked</KeyItem>
      <KeyItem swatch={<span className="h-[3px] w-5 bg-alert" />}>Longest night</KeyItem>
      <KeyItem swatch={<span className="h-[3px] w-5 bg-ink" />}>Now</KeyItem>
    </ul>
  )
}

function KeyItem({ swatch, children }: { swatch: React.ReactNode; children: React.ReactNode }) {
  return (
    <li className="flex items-center gap-2">
      <span aria-hidden="true" className="flex">
        {swatch}
      </span>
      {children}
    </li>
  )
}
