import { useShallow } from 'zustand/react/shallow'
import { useMission } from '../lib/store'
import { useFocusedView } from '../lib/mission'
import { siteById } from '../lib/sites'
import { BlackoutTimeline } from '../components/BlackoutTimeline'
import { DateSlider } from '../components/DateSlider'
import { LoadingPanel } from '../components/States'
import { Button, Panel, SectionLabel } from '../components/ui'
import { Icon } from '../components/Icon'
import { SURVIVAL_LIMIT_H } from '../lib/geometry/metrics'
import { arcsCsv, download, spiceWindows } from '../lib/export'
import { bound, clockUTC, hoursWithUnit } from '../lib/format'

/** S5 — the screen nobody else builds. */
export function BlackoutScreen() {
  const { siteId, cursorH } = useMission(
    useShallow((s) => ({ siteId: s.siteId, cursorH: s.cursorH })),
  )
  const view = useFocusedView()
  const metrics = view.data?.metrics
  const packet = view.data?.autonomy
  const site = siteById(siteId)

  if (!metrics || !packet) {
    return (
      <div className="flex grow flex-col gap-6 p-4 lg:p-6">
        <div className="max-w-2xl">
          <LoadingPanel />
        </div>
      </div>
    )
  }

  const marginPct = Math.round(packet.marginFraction * 100)
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
          <h1 className="text-[24px] font-semibold">Blackout planner — {site.code}</h1>
          <div className="font-mono text-[12px] text-ink-3">
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
          <Panel className="flex flex-col">
            <div className="flex items-center gap-4 border-b border-line px-4 py-3">
              <SectionLabel>The mission window, hour by hour</SectionLabel>
              <span className="ml-auto font-mono text-[11px] text-ink-3">
                {Math.round(metrics.windowHours)} h · one lunar day
              </span>
            </div>
            <div className="overflow-x-auto p-4">
              <BlackoutTimeline metrics={metrics} cursorH={cursorH} className="min-w-[860px]" />
            </div>
          </Panel>

          <Panel className="flex flex-col">
            <div className="flex items-center gap-4 border-b border-line px-4 py-3">
              <SectionLabel>Blackout ledger</SectionLabel>
              <span className="ml-auto text-[12px] text-ink-3">sorted by length</span>
            </div>
            <div className="overflow-x-auto">
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
                        className={`px-4 py-3 text-[11px] font-semibold tracking-[0.1em] text-ink-3 uppercase ${
                          h === 'Length' ? 'text-right' : ''
                        }`}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {blackouts.map((a, i) => {
                    const overlap = metrics.compound
                      .filter((c) => c.startH < a.endH && c.endH > a.startH)
                      .reduce((s, c) => s + c.hours, 0)
                    return (
                      <tr key={i} className={`border-t border-line ${overlap > 0 ? 'bg-alert-wash' : ''}`}>
                        <td className="px-4 py-3 font-mono text-[13px] text-ink-3">B{i + 1}</td>
                        <td className="px-4 py-3 font-mono text-[13px] text-ink">
                          {a.openStart ? `before ${clockUTC(a.startH)}` : clockUTC(a.startH)}
                        </td>
                        <td className="px-4 py-3 font-mono text-[13px] text-ink">
                          {a.openEnd ? `after ${clockUTC(a.endH)}` : clockUTC(a.endH)}
                        </td>
                        <td className="px-4 py-3 text-right text-[15px] font-semibold tnum">
                          {hoursWithUnit(a.hours, 0, a.openStart || a.openEnd)}
                        </td>
                        <td className="px-4 py-3 text-[13px]">
                          {overlap > 0.25 ? (
                            <span className="flex items-center gap-2 font-semibold text-alert">
                              <Icon name="alert" size={14} strokeWidth={2.4} />
                              yes — {Math.round(overlap)} h of it is also dark
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
            </div>
          </Panel>
        </div>

        <aside className="flex w-full shrink-0 flex-col border border-line-strong bg-raised lg:w-[400px]">
          <div className="flex flex-col gap-1.5 border-b border-line-strong p-5">
            <div className="text-[12px] font-semibold tracking-[0.14em] text-sun uppercase">
              Autonomy packet
            </div>
            <div className="text-[20px] font-semibold">What the lander runs alone on</div>
            <p className="text-[13px] leading-5 text-ink-2">
              Sized for the worst compound event:{' '}
              <strong className="text-ink">{hoursWithUnit(packet.worstCompoundH, 0, packet.worstCompoundOpen)}</strong>{' '}
              with neither sunlight nor an Earth link
              {worstCompound ? `, starting h${Math.round(worstCompound.startH)}` : ''}, plus a {marginPct}%
              margin.
            </p>
          </div>

          <div className="flex items-baseline gap-3 border-b border-line p-5">
            <span className="text-[64px] leading-[60px] font-semibold tracking-[-0.025em] tnum">
              {bound(packet.worstCompoundOpen)}
              {Math.round(packet.requiredAutonomyH)}
            </span>
            <div className="flex flex-col">
              <span className="text-[16px] text-ink-2">h of full autonomy</span>
              <span className="text-[12px] text-ink-3">
                {hoursWithUnit(packet.worstCompoundH, 0, packet.worstCompoundOpen)} event + {marginPct}%
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
            detail={`${hoursWithUnit(packet.requiredAutonomyH)} of science and housekeeping at [YOUR DATA RATE], held until the next pass.`}
            value="[Gb]"
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
            value="todo"
          />

          <div className="mt-auto flex flex-col gap-2.5 border-t border-line-strong p-5">
            {metrics.sun.longestDownH > SURVIVAL_LIMIT_H && (
              <p className="flex items-start gap-2 text-[13px] leading-5 text-alert">
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
            <p className="text-[12px] leading-[18px] text-ink-3">
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
          alert ? 'border-alert' : done ? 'border-earth' : 'border-line-strong'
        }`}
      >
        {alert ? (
          <Icon name="alert" size={12} strokeWidth={3} className="text-alert" />
        ) : done ? (
          <Icon name="check" size={12} strokeWidth={3.2} className="text-earth" />
        ) : null}
      </div>
      <div className="flex grow flex-col gap-0.5">
        <div className={`text-[14px] font-semibold ${alert ? 'text-alert' : ''}`}>{title}</div>
        <div className="text-[13px] leading-5 text-ink-2">{detail}</div>
      </div>
      <div className={`shrink-0 font-mono text-[13px] ${alert ? 'text-alert' : 'text-ink'}`}>{value}</div>
    </div>
  )
}
