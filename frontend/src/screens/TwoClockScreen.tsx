import { Link } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { useMission } from '../lib/store'
import { useFocusedMetrics, useFocusedView } from '../lib/mission'
import { Sources } from '../components/Sources'
import { siteById } from '../lib/sites'
import { DateSlider } from '../components/DateSlider'
import { TERRAIN_BLOCKER_MIN_EL_DEG, TwoClockRings } from '../components/TwoClockRings'
import { EducatorGuide } from '../components/EducatorGuide'
import { KeyNumberRow } from '../components/KeyNumbers'
import { ArcTable } from '../components/ArcTable'
import { LoadingPanel, UncertaintyNote } from '../components/States'
import { useProvenance } from '../lib/useProvenance'
import { Button, Panel, SampleDataBadge, SectionLabel } from '../components/ui'
import { Icon } from '../components/Icon'
import { bearing, bound, coords, degrees, hoursWithUnit, humanDuration } from '../lib/format'

/**
 * S2 — the signature screen. Everything else calibrates to this.
 * One shape, two bodies, four numbers underneath at display size.
 */
export function TwoClockScreen() {
  const view = useFocusedView()
  const provenance = useProvenance()
  const { siteId, cursorH, face, showTable, toggleTable } = useMission(
    useShallow((s) => ({
      siteId: s.siteId,
      cursorH: s.cursorH,
      face: s.face,
      showTable: s.tableOpen,
      toggleTable: s.toggleTable,
    })),
  )
  const metrics = useFocusedMetrics()
  const site = siteById(siteId)

  const worst = metrics?.sun.longestDownArc
  const worstOpen = Boolean(metrics?.sun.longestDownOpen)
  const byTerrain =
    worst?.blockedByElDeg !== undefined && worst.blockedByElDeg > TERRAIN_BLOCKER_MIN_EL_DEG
  const ringSize = face === 'public' ? 460 : 540

  return (
    <div className="flex grow flex-col">
      <div className="flex flex-wrap items-center gap-x-8 gap-y-3 border-b border-line px-4 py-4 lg:px-6">
        <div className="flex min-w-[260px] flex-col gap-1">
          <h1 className="text-[24px] font-semibold tracking-[-0.005em]">{site.name}</h1>
          <div className="font-mono text-[12px] text-ink-3">
            {coords(site.latDeg, site.lonDeg)} · elev {site.elevM.toLocaleString()} m
          </div>
        </div>
        <DateSlider />
        <span className="xl:hidden">
          <SampleDataBadge provenance={provenance} />
        </span>
      </div>

      <div className="flex grow flex-col gap-6 p-4 lg:flex-row lg:p-6">
        <div className="flex grow flex-col items-center gap-6">
          {metrics ? (
            <div className="flex w-full flex-col items-center gap-6 xl:flex-row xl:justify-center">
              <TwoClockRings
                metrics={metrics}
                cursorH={cursorH}
                maxSize={ringSize}
              />
              {face !== 'public' && <RingKey />}
            </div>
          ) : (
            <div className="w-full max-w-2xl">
              <LoadingPanel />
            </div>
          )}

          {face === 'public' && metrics && worst ? (
            <div className="flex max-w-[520px] flex-col items-center gap-4 text-center">
              <div className="text-[96px] leading-[88px] font-semibold tracking-[-0.03em] tnum">
                {bound(worstOpen)}
                {Math.round(worst.hours)}
              </div>
              <div className="text-[20px] text-ink-2">hours of night</div>
              <p className="text-[17px] leading-7 text-ink text-pretty">
                {byTerrain
                  ? `At this spot on the Moon, one ridge ${bearing(worst.blockedByBearingDeg ?? 0)} of here switches off the sunlight for ${humanDuration(worst.hours, 'public', worstOpen)}.`
                  : `At this spot on the Moon, the Sun dips below the horizon for ${humanDuration(worst.hours, 'public', worstOpen)}.`}{' '}
                {worstOpen ? 'This window cuts the night short, so the real one is longer. ' : ''}A lander
                has to survive that on batteries alone.
              </p>
              <Link
                to="/story"
                className="inline-flex h-12 items-center rounded-control bg-sun-fill px-6 text-[15px] font-semibold text-on-sun no-underline"
              >
                Why is that?
              </Link>
            </div>
          ) : (
            <div className="w-full">
              <KeyNumberRow metrics={metrics} face={face} />
            </div>
          )}

          {showTable && metrics && (
            <div className="w-full">
              <ArcTable metrics={metrics} />
            </div>
          )}
        </div>

        {face === 'planner' && (
          <aside className="flex w-full shrink-0 flex-col gap-4 lg:w-[320px]">
            <Panel className="flex flex-col gap-3 p-5">
              <SectionLabel>What blocks what</SectionLabel>
              {metrics && worst ? (
                <>
                  <div className="flex gap-2.5">
                    <div className="w-[3px] shrink-0 bg-sun-fill" />
                    <p className="text-[13px] leading-5 text-ink">
                      {byTerrain ? (
                        <>
                          The {hoursWithUnit(worst.hours, 0, worstOpen)} gap is terrain at bearing{' '}
                          {bearing(worst.blockedByBearingDeg ?? 0)}, standing{' '}
                          {degrees(worst.blockedByElDeg ?? 0, 2)} above the flat horizon —{' '}
                          {Math.round(
                            metrics.mask.rangeM[
                              Math.round(worst.blockedByBearingDeg ?? 0) % metrics.mask.rangeM.length
                            ],
                          ).toLocaleString()}{' '}
                          m away.
                        </>
                      ) : (
                        <>
                          The {hoursWithUnit(worst.hours, 0, worstOpen)} gap is the Sun below the horizon, not
                          a ridge: no terrain stands above level along its path.
                        </>
                      )}
                      {worstOpen ? ' The window cuts it short, so the night itself is longer.' : ''}
                    </p>
                  </div>
                  <div className="flex gap-2.5">
                    <div className="w-[3px] shrink-0 bg-earth-fill" />
                    <p className="text-[13px] leading-5 text-ink">
                      Earth sets below the horizon with libration, not with terrain — that is why its gap is
                      measured in days and no ridge is responsible for it.
                    </p>
                  </div>
                  <Link to="/horizon" className="text-[13px] font-semibold">
                    See it on the horizon profile →
                  </Link>
                </>
              ) : (
                <p className="text-[13px] text-ink-3">Computing the skyline…</p>
              )}
            </Panel>

            {metrics && view.meta && (
              <UncertaintyNote>
                Terrain heights carry up to ±{view.meta.uncertainty.demVerticalErrorM} m of vertical error.
                {worst?.grazing ? (
                  <>
                    {' '}The longest gap has a crossing too shallow to time, so it is marked{' '}
                    <span className="font-mono text-earth-soft">grazing</span> rather than given a false
                    precision.
                  </>
                ) : (
                  <>
                    {' '}The longest gap carries{' '}
                    <span className="font-mono text-earth-soft">
                      ±{(worst?.toleranceH ?? 0).toFixed(2)} h
                    </span>{' '}
                    here; a gap carries both of its edges.
                  </>
                )}
                {view.meta.uncertainty.partialCoverage
                  ? ` Terrain covers only ${(view.meta.uncertainty.coverage * 100).toFixed(0)}% of the sampled bearings; the rest assume a smooth Moon and are likely optimistic.`
                  : ''}
              </UncertaintyNote>
            )}

            <Panel className="flex flex-col gap-3 p-5">
              <SectionLabel>Every chart is also a table</SectionLabel>
              <Button onClick={toggleTable}>
                <Icon name="table" size={16} strokeWidth={1.7} />
                {showTable ? 'Hide the arc table' : `Read the ${metrics ? metrics.sun.arcs.length + metrics.earth.arcs.length : ''} arcs as a table`}
              </Button>
              <p className="text-[12px] leading-[18px] text-ink-3">
                Press T anywhere. Each arc announces its start, end, length and what blocks it.
              </p>
            </Panel>

            <Sources meta={view.meta} className="mt-auto" />
          </aside>
        )}

        {face === 'educator' && metrics && (
          <aside className="flex w-full shrink-0 flex-col gap-4 lg:w-[360px]">
            <EducatorGuide siteName={site.name} metrics={metrics} meta={view.meta} />
          </aside>
        )}
      </div>
    </div>
  )
}

function RingKey() {
  return (
    <div className="flex w-full flex-row flex-wrap gap-6 xl:w-[210px] xl:flex-col">
      <KeyItem swatch={<span className="h-3.5 w-6 bg-sun-fill" />} title="Outer — Sun" tone="text-sun">
        Filled where the Sun is above this site’s own horizon.
      </KeyItem>
      <KeyItem swatch={<span className="h-3.5 w-6 bg-earth-fill" />} title="Inner — Earth" tone="text-earth">
        Filled where Earth is above it.
      </KeyItem>
      <KeyItem
        swatch={<span className="hatch-blocked h-3.5 w-6" />}
        title="Blocked"
        tone="text-ink-2"
      >
        Below the horizon, or behind terrain.
      </KeyItem>
      <KeyItem swatch={<span className="h-[3px] w-6 bg-alert" />} title="Longest dark gap" tone="text-alert" />
      <KeyItem swatch={<span className="h-[3px] w-6 bg-ink" />} title="Now" tone="text-ink" />
    </div>
  )
}

function KeyItem({
  swatch,
  title,
  tone,
  children,
}: {
  swatch: React.ReactNode
  title: string
  tone: string
  children?: React.ReactNode
}) {
  return (
    <div className="flex min-w-[160px] flex-col gap-2">
      <div className="flex items-center gap-2.5">
        {swatch}
        <span className={`text-[13px] font-semibold tracking-[0.12em] uppercase ${tone}`}>{title}</span>
      </div>
      {children && <p className="text-[13px] leading-5 text-ink-2">{children}</p>}
    </div>
  )
}
