import { Link } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { useMission } from '../lib/store'
import { useFocusedMetrics, useFocusedView } from '../lib/mission'
import { siteById } from '../lib/sites'
import { HorizonProfile } from '../components/HorizonProfile'
import { DateSlider } from '../components/DateSlider'
import { SitePicker } from '../components/SitePicker'
import { LoadingPanel, ProblemPanel, UncertaintyNote } from '../components/States'
import { Panel, ScrollRegion, SectionLabel } from '../components/ui'
import { bearing, bound, compassWords, coords, degrees, edgeMargin, hoursWithUnit } from '../lib/format'

/** S4 — the screen that makes the physics click for a non-expert. */
export function HorizonScreen() {
  const view = useFocusedView()
  const { siteId, cursorH } = useMission(
    useShallow((s) => ({ siteId: s.siteId, cursorH: s.cursorH })),
  )
  const metrics = useFocusedMetrics()
  const site = siteById(siteId)

  if (!metrics || view.error) {
    return (
      <div className="flex grow flex-col gap-6 p-4 lg:p-6">
        <div className="max-w-2xl">
          {view.error ? (
            <ProblemPanel error={view.error} fallbackTitle="Cannot draw this skyline" onRetry={view.refetch} />
          ) : (
            <LoadingPanel done={0} total={1} />
          )}
        </div>
      </div>
    )
  }
  const terrainModelled = view.meta?.uncertainty.terrainModelled ?? site.terrainModelled

  const worst = metrics.sun.longestDownArc
  const blockAz = worst?.blockedByBearingDeg ?? metrics.mask.maxElBearingDeg
  const blockIdx = Math.round((blockAz / 360) * metrics.mask.elDeg.length) % metrics.mask.elDeg.length
  const rangeM = metrics.mask.rangeM[blockIdx]
  const elDeg = metrics.mask.elDeg[blockIdx]
  // Where terrain is modelled the skyline is the terrain's own silhouette, even
  // where it lies below level, so the bearing the Sun set on names a real
  // feature. On a smooth Moon there is none to name.
  const byTerrain = terrainModelled && worst?.blockedByBearingDeg !== undefined
  // The highest the Sun gets in this window: one of the API's own samples.
  const sunMax = metrics.sun.samples.reduce((m, s) => Math.max(m, s.elDeg), -90)
  const hemisphere = site.latDeg < 0 ? 'S' : 'N'
  const nightWords = worst ? hoursWithUnit(worst.hours, 0, metrics.sun.longestDownOpen) : ''

  return (
    <div className="flex grow flex-col">
      <div className="flex flex-wrap items-center gap-x-8 gap-y-3 border-b border-line px-4 py-4 lg:px-6">
        <div className="flex min-w-[260px] flex-col gap-1">
          <Link to="/clocks" className="inline-flex h-8 items-center text-small font-semibold">
            ← Back to {site.name}
          </Link>
          <h1 className="text-heading font-semibold">The skyline from {site.name}</h1>
          <div className="font-mono text-caption text-ink-3">
            {coords(site.latDeg, site.lonDeg)} · skyline measured in{' '}
            {view.meta ? `${view.meta.resolution.azimuthCount} directions, out to ${(view.meta.resolution.maxRangeM / 1000).toFixed(0)} km` : '…'}
          </div>
        </div>
        <SitePicker />
        <DateSlider />
      </div>

      <div className="flex grow flex-col gap-6 p-4 lg:flex-row lg:p-6">
        <div className="flex min-w-0 grow flex-col gap-6">
          {!terrainModelled && (
            <UncertaintyNote>
              There is no terrain data outside 80°S, so the Sun and Earth are worked out as if the ground were flat. Real hills could block more. The skyline below is that flat horizon, not terrain.
            </UncertaintyNote>
          )}
          <Panel className="flex flex-col">
            <div className="flex items-center gap-4 border-b border-line px-4 py-3">
              <SectionLabel>The skyline all around the site, by compass direction</SectionLabel>
              <span className="ml-auto font-mono text-tag text-ink-3">
                highest {degrees(metrics.mask.maxElDeg, 2)} at {bearing(metrics.mask.maxElBearingDeg)}
              </span>
            </div>
            <ScrollRegion label="Skyline chart, scrolls sideways" className="p-3">
              <HorizonProfile metrics={metrics} cursorH={cursorH} className="min-w-[860px]" />
            </ScrollRegion>
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-line px-4 py-3">
              <Legend swatch="h-[3px] w-5 bg-sun-fill">The Sun’s path on these dates</Legend>
              <Legend swatch="h-[3px] w-5 bg-earth-fill">Earth’s small loop in the sky (libration)</Legend>
              <Legend swatch="h-2.5 w-5 bg-terrain-low border-t-2 border-terrain-high">Terrain skyline</Legend>
              <Legend swatch="h-3 w-5 hatch-blocked">Sun behind terrain</Legend>
              <Legend swatch="h-3 w-5 hatch-uncertain">How far off the skyline could be</Legend>
            </div>
          </Panel>

          <Panel className="flex flex-col gap-3 p-5">
            <h2 className="text-title font-semibold">Why the dashed line matters</h2>
            <p className="max-w-3xl text-body leading-6 text-ink-2">
              {terrainModelled ? (
                <>
                  The dashed line is level, 0°: where a tool that ignores terrain puts the horizon. The grey
                  shape is the real skyline, and at {Math.abs(site.latDeg).toFixed(1)}°{hemisphere} the Sun never
                  climbs above {degrees(sunMax, 2)} on these dates, so that skyline, not level, decides when it
                  sets.
                </>
              ) : (
                <>
                  Outside the polar terrain map the ground is treated as flat, so the skyline and the dashed
                  line are the same line: every sunset here is the Sun going below a flat horizon. On these dates
                  the Sun climbs to {degrees(sunMax, 2)}.
                </>
              )}
            </p>
          </Panel>
        </div>

        <aside className="flex w-full shrink-0 flex-col gap-4 lg:w-[320px]">
          <Panel elevated className="flex flex-col gap-3 p-5">
            <SectionLabel>What blocks the Sun</SectionLabel>
            {byTerrain ? (
              <>
                <div className="text-subhead font-semibold">
                  Terrain to the {compassWords(blockAz)} ({bearing(blockAz)})
                </div>
                <div className="font-mono text-caption leading-5 text-ink-2">
                  height above the flat horizon {degrees(elDeg, 2)}
                  <br />
                  distance {Math.round(rangeM).toLocaleString()} m
                </div>
              </>
            ) : (
              <div className="text-subhead font-semibold">
                {worst ? 'Nothing: the Sun sets below the horizon itself' : 'Nothing on these dates'}
              </div>
            )}
            {worst && (
              <div className="flex items-baseline gap-2 border-t border-line pt-3">
                <span className="text-display leading-10 font-semibold tracking-figure-sm tnum">
                  {bound(metrics.sun.longestDownOpen)}
                  {Math.round(worst.hours)}
                </span>
                <span className="text-body text-ink-2">
                  h of darkness on these dates{metrics.sun.longestDownOpen ? ', cut short by the last date' : ''}
                </span>
              </div>
            )}
          </Panel>

          <UncertaintyNote hatchKey={terrainModelled}>
            {terrainModelled ? (
              <>
                The hatched band on the skyline is how far off it could be in each direction: the terrain map’s
                height error (
                {view.meta ? `up to ±${view.meta.uncertainty.demVerticalErrorM} m` : 'a few metres'}) seen from
                the distance of that ridge, so it is wide for a near ridge and thin for a far one. Where the
                Sun’s path runs inside it, the crossing time is uncertain by{' '}
                <span className="font-mono text-ink">
                  {worst?.grazing ? 'more than can be timed (grazing)' : edgeMargin(worst, terrainModelled)}
                </span>
                .
              </>
            ) : (
              'No terrain map covers this site, so its skyline has no stated error and the crossing times carry no margin. Real hills could only block more.'
            )}
          </UncertaintyNote>

          <Panel className="flex flex-col gap-2 p-5">
            <SectionLabel>Read it in one line</SectionLabel>
            <p className="text-body leading-6 text-ink-2">
              {!worst
                ? 'The Sun stays above the skyline in every direction on these dates. Nothing here blocks it.'
                : byTerrain
                  ? `The Sun clears the skyline everywhere except a stretch to the ${compassWords(blockAz)}. It passes behind that and stays hidden ${nightWords}.`
                  : `The Sun sets below the horizon itself here, for ${nightWords} on these dates; no ridge is responsible.`}
            </p>
          </Panel>
        </aside>
      </div>
    </div>
  )
}

function Legend({ swatch, children }: { swatch: string; children: React.ReactNode }) {
  return (
    <span className="flex items-center gap-2 text-caption text-ink">
      <span className={swatch} aria-hidden="true" />
      {children}
    </span>
  )
}
