import { useMission } from '../lib/store'
import { useFocusedMetrics, useFocusedView } from '../lib/mission'
import { siteById } from '../lib/sites'
import { HorizonProfile } from '../components/HorizonProfile'
import { DateSlider } from '../components/DateSlider'
import { LoadingPanel, UncertaintyNote } from '../components/States'
import { Panel, SectionLabel } from '../components/ui'
import { bearing, compass, coords, degrees, hoursWithUnit } from '../lib/format'
import { DEM_VERTICAL_ERROR_M } from '../lib/geometry/mask'

/** S4 — the screen that makes the physics click for a non-expert. */
export function HorizonScreen() {
  const view = useFocusedView()
  const { siteId, cursorH } = useMission()
  const metrics = useFocusedMetrics()
  const site = siteById(siteId)

  if (!metrics) {
    return (
      <div className="flex grow flex-col gap-6 p-4 lg:p-6">
        <div className="max-w-2xl">
          <LoadingPanel />
        </div>
      </div>
    )
  }

  const worst = metrics.sun.longestDownArc
  const blockAz = worst?.blockedByBearingDeg ?? metrics.mask.maxElBearingDeg
  const blockIdx = Math.round(blockAz) % 360
  const rangeM = metrics.mask.rangeM[blockIdx]
  const elDeg = metrics.mask.elDeg[blockIdx]
  const heightM = Math.tan((elDeg * Math.PI) / 180) * rangeM

  // How many whole degrees of bearing sit above the Sun's highest elevation.
  const sunMax = metrics.sun.samples.reduce((m, s) => Math.max(m, s.elDeg), -90)
  const blockedBearings = Array.from(metrics.mask.elDeg).filter((e) => e > sunMax).length

  return (
    <div className="flex grow flex-col">
      <div className="flex flex-wrap items-center gap-x-8 gap-y-3 border-b border-line px-4 py-4 lg:px-6">
        <div className="flex min-w-[260px] flex-col gap-1">
          <h1 className="text-[24px] font-semibold">Standing at {site.code}, looking out</h1>
          <div className="font-mono text-[12px] text-ink-3">
            {coords(site.latDeg, site.lonDeg)} · horizon mask{' '}
            {view.meta ? `${view.meta.resolution.azimuthCount} az × ${(view.meta.resolution.maxRangeM / 1000).toFixed(0)} km` : '…'}
          </div>
        </div>
        <DateSlider />
      </div>

      <div className="flex grow flex-col gap-6 p-4 lg:flex-row lg:p-6">
        <div className="flex grow flex-col gap-6">
          <Panel className="flex flex-col">
            <div className="flex items-center gap-4 border-b border-line px-4 py-3">
              <SectionLabel>Local skyline — elevation above the flat horizon, by bearing</SectionLabel>
              <span className="ml-auto font-mono text-[11px] text-ink-3">
                peak {degrees(metrics.mask.maxElDeg, 2)} at {bearing(metrics.mask.maxElBearingDeg)}
              </span>
            </div>
            <div className="overflow-x-auto p-3">
              <HorizonProfile metrics={metrics} cursorH={cursorH} className="min-w-[860px]" />
            </div>
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-line px-4 py-3">
              <Legend swatch="h-[3px] w-5 bg-sun-fill">Sun over one lunar day</Legend>
              <Legend swatch="h-[3px] w-5 bg-earth-fill">Earth libration loop</Legend>
              <Legend swatch="h-2.5 w-5 bg-terrain-low border-t-2 border-terrain-high">Terrain skyline</Legend>
              <Legend swatch="h-3 w-5 hatch-blocked">Sun behind terrain</Legend>
              <Legend swatch="h-3 w-5 hatch-uncertain">Skyline margin</Legend>
            </div>
          </Panel>

          <Panel className="flex flex-col gap-3 p-5">
            <h2 className="text-[17px] font-semibold">Why the dashed line matters</h2>
            <p className="max-w-3xl text-[14px] leading-6 text-ink-2">
              The dashed line is where the horizon would be on a smooth Moon. Everything between it and the
              grey silhouette is rock that a globe-only calculation ignores — and at{' '}
              {Math.abs(site.latDeg).toFixed(1)}°S the Sun spends its entire day inside that band, never
              climbing above {degrees(sunMax, 2)}. Out of 360 bearings,{' '}
              <strong className="text-ink">{blockedBearings}</strong> have terrain standing higher than the
              Sun ever gets.
            </p>
          </Panel>
        </div>

        <aside className="flex w-full shrink-0 flex-col gap-4 lg:w-[320px]">
          <Panel elevated className="flex flex-col gap-3 p-5">
            <SectionLabel>The feature that costs you</SectionLabel>
            <div className="text-[20px] font-semibold">
              Skyline at {bearing(blockAz)} {compass(blockAz)}
            </div>
            <div className="font-mono text-[12px] leading-5 text-ink-2">
              elevation {degrees(elDeg, 2)}
              <br />
              range {Math.round(rangeM).toLocaleString()} m<br />
              rise {Math.round(heightM)} m above the site plane
            </div>
            {worst && (
              <div className="flex items-baseline gap-2 border-t border-line pt-3">
                <span className="text-[40px] leading-10 font-semibold tracking-[-0.02em] tnum">
                  ≈{Math.round(worst.hours)}
                </span>
                <span className="text-[14px] text-ink-2">h of darkness, every lunar day</span>
              </div>
            )}
          </Panel>

          <UncertaintyNote>
            The hatched band on the silhouette is the skyline’s own error, from a {DEM_VERTICAL_ERROR_M} m
            vertical accuracy at each blocking range. Where the Sun path runs inside it the crossing time is
            uncertain by{' '}
            <span className="font-mono text-earth-soft">±{(worst?.toleranceH ?? 0).toFixed(2)} h</span>.
          </UncertaintyNote>

          <Panel className="flex flex-col gap-2 p-5">
            <SectionLabel>Read it in one line</SectionLabel>
            <p className="text-[14px] leading-6 text-ink-2">
              {worst
                ? `The Sun clears every bearing except a stretch near ${compass(blockAz)}. It crosses into
                   that shadow once a month and stays there ${hoursWithUnit(worst.hours)}.`
                : 'The Sun clears the skyline at every bearing in this window. Nothing here blocks it.'}
            </p>
          </Panel>
        </aside>
      </div>
    </div>
  )
}

function Legend({ swatch, children }: { swatch: string; children: React.ReactNode }) {
  return (
    <span className="flex items-center gap-2 text-[12px] text-ink">
      <span className={swatch} aria-hidden="true" />
      {children}
    </span>
  )
}
