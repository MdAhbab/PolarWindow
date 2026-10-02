import { PageHeader } from '../components/Page'
import { useShallow } from 'zustand/react/shallow'
import { useMission } from '../lib/store'
import { useFocusedMetrics, useFocusedView } from '../lib/mission'
import { siteById } from '../lib/sites'
import { HorizonProfile } from '../components/HorizonProfile'
import { DateSlider } from '../components/DateSlider'
import { TERRAIN_BLOCKER_MIN_EL_DEG } from '../components/TwoClockRings'
import { LoadingPanel, ProblemPanel, UncertaintyNote } from '../components/States'
import { Disclosure, Eyebrow, Panel, ScrollRegion } from '../components/ui'
import { bearing, bound, compassWords, degrees, edgeMargin, hoursWithUnit } from '../lib/format'

/** S4: what the site's own skyline does to the Sun, in one chart and one answer. */
export function HorizonScreen() {
  const view = useFocusedView()
  const { siteId, cursorH } = useMission(
    useShallow((s) => ({ siteId: s.siteId, cursorH: s.cursorH })),
  )
  const metrics = useFocusedMetrics()
  const site = siteById(siteId)

  if (!metrics || view.error) {
    return (
      <div className="pw-page flex grow flex-col gap-6 pt-6 pb-8 lg:pt-8">
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
  // The same rule as the Site page: a ridge is named only when it stands above
  // level. Below that, the Sun is setting below the horizon itself, and the
  // two pages must not give two causes for one night.
  const byTerrain =
    terrainModelled &&
    worst?.blockedByBearingDeg !== undefined &&
    worst.blockedByElDeg !== undefined &&
    worst.blockedByElDeg > TERRAIN_BLOCKER_MIN_EL_DEG
  // The highest the Sun gets in this window: one of the API's own samples.
  const sunMax = metrics.sun.samples.reduce((m, s) => Math.max(m, s.elDeg), -90)
  const nightWords = worst ? hoursWithUnit(worst.hours, 0, metrics.sun.longestDownOpen) : ''

  return (
    <div className="pw-page flex grow flex-col gap-6 pt-6 pb-8 lg:gap-8 lg:pt-8">
      <PageHeader
        compact
        crumbs={[{ label: 'Landing sites', to: '/map' }, { label: site.name, to: '/site' }, { label: 'Skyline' }]}
        title={`The skyline from ${site.name}`}
      />
      <DateSlider />

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_340px] lg:gap-8">
        <div className="flex min-w-0 flex-col gap-4">
          {!terrainModelled && (
            <UncertaintyNote>
              No terrain data outside 80°S, so this skyline is a flat horizon, not terrain. Real hills could block more.
            </UncertaintyNote>
          )}
          {/* The page's hero: the skyline all around the site, with the Sun's path over it. */}
          <Panel as="section" className="flex min-w-0 flex-col gap-3 p-4 sm:p-5">
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
              <h2 className="text-title leading-6 font-semibold tracking-title text-ink">All around the site, by compass direction</h2>
              <span className="ml-auto text-caption text-ink-3">
                highest point {degrees(metrics.mask.maxElDeg, 2)} at {bearing(metrics.mask.maxElBearingDeg)}
              </span>
            </div>
            <ScrollRegion label="Skyline chart, scrolls sideways" className="pb-1">
              <HorizonProfile metrics={metrics} cursorH={cursorH} className="min-w-[860px]" />
            </ScrollRegion>
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
              <Legend swatch="h-[3px] w-5 bg-sun-fill">The Sun’s path</Legend>
              <Legend swatch="h-[3px] w-5 bg-earth-fill">Earth’s small loop (libration)</Legend>
              <Legend swatch="h-2.5 w-5 bg-terrain-low border-t-2 border-terrain-high">Skyline</Legend>
              <Legend swatch="h-3 w-5 hatch-blocked">Sun behind terrain</Legend>
              <Legend swatch="h-3 w-5 hatch-uncertain">How far off the skyline could be</Legend>
            </div>
          </Panel>
          <p className="max-w-3xl text-small leading-5 text-ink-2">
            {terrainModelled
              ? `The dashed line is level ground (0°). Here the Sun never climbs above ${degrees(sunMax, 2)} on these dates, so the skyline, not level, decides when it sets.`
              : `The dashed line is level ground (0°), and here it is also the skyline. The Sun climbs to ${degrees(sunMax, 2)} on these dates.`}
          </p>
        </div>

        <aside className="flex min-w-0 flex-col gap-4">
          <Panel elevated className="flex flex-col gap-3 p-5 sm:p-6">
            <Eyebrow as="h2">What blocks the Sun</Eyebrow>
            {byTerrain ? (
              <>
                <div className="text-subhead leading-7 font-semibold tracking-heading">
                  A ridge to the {compassWords(blockAz)} ({bearing(blockAz)})
                </div>
                <div className="text-small leading-5 text-ink-2">
                  {degrees(elDeg, 2)} above level, {Math.round(rangeM).toLocaleString()} m away.
                </div>
              </>
            ) : (
              <div className="text-subhead leading-7 font-semibold tracking-heading">
                {worst ? 'Nothing: the Sun sets below the horizon itself' : 'Nothing on these dates'}
              </div>
            )}
            {worst ? (
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 border-t border-line pt-4">
                <span className="pw-figure text-[44px] leading-[46px]">
                  {bound(metrics.sun.longestDownOpen)}
                  {Math.round(worst.hours)}
                </span>
                <span className="text-body text-ink-2">
                  h of darkness{metrics.sun.longestDownOpen ? ', cut short by the last date' : ''}
                </span>
              </div>
            ) : (
              <p className="text-small leading-5 text-ink-2">
                The Sun stays above the skyline in every direction on these dates.
              </p>
            )}
          </Panel>

          {terrainModelled && (
            <Disclosure title="How sure is this?">
              <p className="text-small leading-5 text-ink-2">
                The hatched band is how far off the skyline could be in each direction: the terrain map’s height error (
                {view.meta ? `up to ±${view.meta.uncertainty.demVerticalErrorM} m` : 'a few metres'}) seen from that
                ridge’s distance, wide for a near ridge and thin for a far one. Where the Sun’s path runs inside it, the
                {nightWords ? ` ${nightWords}` : ''} night is uncertain by{' '}
                <span className="font-semibold text-ink">
                  {worst?.grazing ? 'more than can be timed' : edgeMargin(worst, terrainModelled)}
                </span>
                .
              </p>
              {view.meta && (
                <p className="text-caption text-ink-3">
                  Skyline measured in {view.meta.resolution.azimuthCount.toLocaleString()} directions, out to{' '}
                  {(view.meta.resolution.maxRangeM / 1000).toFixed(0)} km.
                </p>
              )}
            </Disclosure>
          )}
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
