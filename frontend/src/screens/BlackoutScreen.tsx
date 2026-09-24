import { useShallow } from 'zustand/react/shallow'
import { useMission } from '../lib/store'
import { useFocusedView } from '../lib/mission'
import { siteById } from '../lib/sites'
import { BlackoutTimeline } from '../components/BlackoutTimeline'
import { DateSlider } from '../components/DateSlider'
import { LoadingPanel, ProblemPanel, UncertaintyNote } from '../components/States'
import { Button, Panel, ScrollRegion, SectionLabel } from '../components/ui'
import { Icon } from '../components/Icon'
import { SURVIVAL_LIMIT_H } from '../lib/geometry/metrics'
import { arcsCsv, download, spiceWindows } from '../lib/export'
import { bound, hoursWithUnit, humanStamp, msFromModelH } from '../lib/format'

/** S5 — the screen nobody else builds. */
export function BlackoutScreen() {
  const { siteId, cursorH } = useMission(
    useShallow((s) => ({ siteId: s.siteId, cursorH: s.cursorH })),
  )
  const view = useFocusedView()
  const metrics = view.data?.metrics
  const packet = view.data?.autonomy
  const site = siteById(siteId)

  if (!metrics || !packet || view.error) {
    return (
      <div className="flex grow flex-col gap-6 p-4 lg:p-6">
        <div className="max-w-2xl">
          {view.error ? (
            <ProblemPanel error={view.error} fallbackTitle="Cannot plan this window" onRetry={view.refetch} />
          ) : (
            <LoadingPanel done={0} total={1} />
          )}
        </div>
      </div>
    )
  }
  const terrainModelled = view.meta?.uncertainty.terrainModelled ?? site.terrainModelled

  const marginPct = Math.round(packet.marginFraction * 100)
  const noCompound = packet.worstCompoundH < 0.25 && !packet.worstCompoundOpen
  const origin = metrics.windowStartIso ? Date.parse(metrics.windowStartIso) : msFromModelH(0)
  const when = (h: number) => humanStamp(origin, h)
  const exportSite = { id: site.id, name: site.name, metrics, meta: view.meta, autonomy: packet }
  const stamp = (metrics.windowStartIso ?? 'window').slice(0, 10)
  const blackouts = metrics.earth.arcs.filter((a) => !a.up).sort((a, b) => b.hours - a.hours)
  const worstCompound = metrics.compound.reduce(
    (b, c) => (!b || c.hours > b.hours ? c : b),
    undefined as (typeof metrics.compound)[number] | undefined,
  )

  return (
    <div className="flex grow flex-col">
      <div className="flex flex-wrap items-center gap-x-8 gap-y-3 border-b border-line px-4 py-4 lg:px-6">
        <div className="flex min-w-[260px] flex-col gap-1">
          <h1 className="text-heading font-semibold">Blackout planner — {site.code}</h1>
          <div className="font-mono text-caption text-ink-3">
            {Math.round(metrics.windowHours)} h · {blackouts.length} blackouts ·{' '}
            {metrics.sun.arcs.filter((a) => !a.up).length} dark periods
          </div>
        </div>
        <DateSlider />
      </div>

      <div className="flex grow flex-col gap-6 p-4 lg:flex-row lg:p-6">
        {/* min-w-0: the timeline and the ledger are wider than this column and
            scroll inside their own panels. Without it the column takes their
            width as its minimum and pushes the packet off the right edge. */}
        <div className="flex min-w-0 grow flex-col gap-6">
          {!terrainModelled && (
            <UncertaintyNote>
              Terrain is not modelled outside 80°S. Sun and Earth are computed against a smooth Moon, so real
              hills could block more.
            </UncertaintyNote>
          )}
          <Panel className="flex flex-col">
            <div className="flex items-center gap-4 border-b border-line px-4 py-3">
              <SectionLabel>The mission window, hour by hour</SectionLabel>
              <span className="ml-auto font-mono text-tag text-ink-3">
                {Math.round(metrics.windowHours)} h
              </span>
            </div>
            <ScrollRegion label="Hour-by-hour timeline, scrolls sideways" className="p-4">
              <BlackoutTimeline metrics={metrics} cursorH={cursorH} className="min-w-[860px]" />
            </ScrollRegion>
          </Panel>

          <Panel className="flex flex-col">
            <div className="flex items-center gap-4 border-b border-line px-4 py-3">
              <SectionLabel>Blackout ledger</SectionLabel>
              <span className="ml-auto text-caption text-ink-3">sorted by length</span>
            </div>
            <ScrollRegion label="Blackout ledger, scrolls sideways">
              <table className="w-full min-w-[720px] border-collapse text-left">
                <caption className="sr-only">
                  Every Earth-link blackout in the window, longest first, and whether it overlaps a dark
                  period.
                </caption>
                <thead>
                  <tr className="bg-inset">
                    {['#', 'Start', 'End', 'Length', 'Overlaps darkness'].map((h) => (
                      <th
                        key={h}
                        scope="col"
                        className={`px-4 py-3 text-tag font-semibold tracking-caps-md text-ink-3 uppercase ${
                          h === 'Length' ? 'text-right' : ''
                        }`}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {blackouts.length === 0 && (
                    <tr className="border-t border-line">
                      <td colSpan={5} className="px-4 py-4 text-body text-ink-2">
                        No blackouts: Earth stayed above the skyline for the whole window.
                      </td>
                    </tr>
                  )}
                  {blackouts.map((a, i) => {
                    // Whether a dark-and-silent stretch (from the API) falls inside
                    // this blackout; the ledger says so without adding up hours.
                    const overlaps = metrics.compound.some((c) => c.startH < a.endH && c.endH > a.startH && c.hours >= 0.25)
                    return (
                      <tr key={i} className={`border-t border-line ${overlaps ? 'bg-alert-wash' : ''}`}>
                        <td className="px-4 py-3 font-mono text-small text-ink-3">B{i + 1}</td>
                        <td className="px-4 py-3 font-mono text-small text-ink">
                          {a.openStart ? `before ${when(a.startH)}` : when(a.startH)}
                        </td>
                        <td className="px-4 py-3 font-mono text-small text-ink">
                          {a.openEnd ? `after ${when(a.endH)}` : when(a.endH)}
                        </td>
                        <td className="px-4 py-3 text-right text-control font-semibold tnum">
                          {hoursWithUnit(a.hours, 0, a.openStart || a.openEnd)}
                        </td>
                        <td className="px-4 py-3 text-small">
                          {overlaps ? (
                            <span className="flex items-center gap-2 font-semibold text-alert">
                              <Icon name="alert" size={14} strokeWidth={2.4} />
                              yes — part of it is also dark
                            </span>
                          ) : (
                            <span className="text-ink-2">no — solar power available throughout</span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </ScrollRegion>
          </Panel>
        </div>

        <aside className="flex w-full shrink-0 flex-col border border-line-strong bg-raised lg:w-[400px]">
          <div className="flex flex-col gap-1.5 border-b border-line-strong p-5">
            <div className="text-caption font-semibold tracking-caps-lg text-ink-3 uppercase">
              Autonomy packet
            </div>
            <div className="text-subhead font-semibold">What the lander runs alone on</div>
            <p className="text-small leading-5 text-ink-2">
              {noCompound ? (
                'Sunlight and an Earth link are never lost together in this window, so nothing has to run alone; the battery still carries the longest night.'
              ) : (
                <>
                  Sized for the worst compound event:{' '}
                  <strong className="text-ink">
                    {hoursWithUnit(packet.worstCompoundH, 0, packet.worstCompoundOpen)}
                  </strong>{' '}
                  with neither sunlight nor an Earth link
                  {worstCompound ? `, starting ${when(worstCompound.startH)}` : ''}, plus a {marginPct}% margin.
                </>
              )}
            </p>
          </div>

          <div className="flex items-baseline gap-3 border-b border-line p-5">
            <span className="text-figure-lg leading-figure-lg-tight font-semibold tracking-figure tnum">
              {bound(packet.worstCompoundOpen)}
              {Math.round(packet.requiredAutonomyH)}
            </span>
            <div className="flex flex-col">
              <span className="text-lede text-ink-2">h of full autonomy</span>
              <span className="text-caption text-ink-3">
                {noCompound
                  ? 'no compound event'
                  : `${hoursWithUnit(packet.worstCompoundH, 0, packet.worstCompoundOpen)} event + ${marginPct}%`}
              </span>
            </div>
          </div>

          <PacketRow
            done
            title="Command buffer"
            detail={`${hoursWithUnit(packet.requiredAutonomyH)} of sequenced activity, uplinked in the preceding contact window.`}
            value={hoursWithUnit(packet.requiredAutonomyH)}
          />
          <PacketRow
            done
            title="Onboard storage"
            detail={`${hoursWithUnit(packet.requiredAutonomyH)} of science and housekeeping at the payload’s own data rate, held until the next pass.`}
            value="per payload"
          />
          <PacketRow
            alert={metrics.sun.longestDownH > SURVIVAL_LIMIT_H}
            title="Survival energy"
            detail={
              packet.compoundInsideDark
                ? `The worst silence falls inside a night, and the battery carries the longest night whatever the radio is doing: ${hoursWithUnit(packet.survivalNeededH, 0, packet.survivalOpen)}.`
                : `No silence overlaps a night badly enough to matter, but the battery still carries the longest night: ${hoursWithUnit(packet.survivalNeededH, 0, packet.survivalOpen)}.`
            }
            value={hoursWithUnit(packet.survivalNeededH, 0, packet.survivalOpen)}
          />
          <PacketRow
            done
            title="Fault response"
            detail={`Safing rules that hold state for ${hoursWithUnit(packet.requiredAutonomyH)} without a ground call, and a recovery that does not need one.`}
            value="rules"
          />
          <PacketRow
            title="Decisions delegated"
            detail="Anything time-critical inside the window: target selection, abort thresholds, thermal shedding order."
            value="to plan"
          />

          <div className="mt-auto flex flex-col gap-2.5 border-t border-line-strong p-5">
            {metrics.sun.longestDownH > SURVIVAL_LIMIT_H && (
              <p className="flex items-start gap-2 text-small leading-5 text-alert">
                <Icon name="alert" size={16} strokeWidth={2.2} className="mt-0.5 shrink-0" />
                No packet saves this site: the night alone is{' '}
                {Math.round(metrics.sun.longestDownH - SURVIVAL_LIMIT_H)} h past the {SURVIVAL_LIMIT_H} h
                survival limit.
              </p>
            )}
            <Button
              variant="primary"
              onClick={() => download(`${site.id}-${stamp}-arcs.csv`, arcsCsv(exportSite), 'text/csv')}
            >
              <Icon name="table" size={16} strokeWidth={1.7} />
              Export the arcs as CSV
            </Button>
            <Button onClick={() => download(`${site.id}-${stamp}-windows.txt`, spiceWindows(exportSite))}>
              Export SPICE interval lists
            </Button>
            <p className="text-caption leading-caption text-ink-3">
              Both files are built from the same arcs as the timeline and the ledger, with their margins and
              provenance. The SPICE file lists each lit, contact and dark-and-silent interval in UTC, ready for{' '}
              <span className="font-mono">str2et</span> and <span className="font-mono">wninsd</span>.
            </p>
          </div>
        </aside>
      </div>
    </div>
  )
}

function PacketRow({
  title,
  detail,
  value,
  done,
  alert,
}: {
  title: string
  detail: string
  value: string
  done?: boolean
  alert?: boolean
}) {
  return (
    <div className={`flex gap-3.5 border-b border-line p-4 ${alert ? 'bg-alert-wash' : ''}`}>
      <div
        className={`mt-0.5 flex size-5 shrink-0 items-center justify-center border ${
          alert ? 'border-alert' : done ? 'border-ink' : 'border-line-strong'
        }`}
      >
        {alert ? (
          <Icon name="alert" size={12} strokeWidth={3} className="text-alert" />
        ) : done ? (
          <Icon name="check" size={12} strokeWidth={3.2} className="text-ink" />
        ) : null}
      </div>
      <div className="flex grow flex-col gap-0.5">
        <div className={`text-body font-semibold ${alert ? 'text-alert' : ''}`}>{title}</div>
        <div className="text-small leading-5 text-ink-2">{detail}</div>
      </div>
      <div className={`shrink-0 font-mono text-small ${alert ? 'text-alert' : 'text-ink'}`}>{value}</div>
    </div>
  )
}
