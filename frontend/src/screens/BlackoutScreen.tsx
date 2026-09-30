import { useShallow } from 'zustand/react/shallow'
import { useMission } from '../lib/store'
import { useFocusedView } from '../lib/mission'
import { siteById } from '../lib/sites'
import { BlackoutTimeline } from '../components/BlackoutTimeline'
import { DateSlider } from '../components/DateSlider'
import { SiteTitle } from '../components/SitePicker'
import { LoadingPanel, ProblemPanel, UncertaintyNote } from '../components/States'
import { Button, Panel, ScrollRegion, SectionLabel } from '../components/ui'
import { Icon } from '../components/Icon'
import { SURVIVAL_LIMIT_H } from '../lib/geometry/metrics'
import { arcsCsv, download, spiceWindows } from '../lib/export'
import { bound, hoursWithUnit, humanStamp, msFromModelH, spanWords } from '../lib/format'

/** S5: every stretch without contact, and what the lander must handle alone. */
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
      <div className="pw-page flex grow flex-col gap-6 py-5 lg:py-6">
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
  const nights = metrics.sun.arcs.filter((a) => !a.up).length
  const worstCompound = metrics.compound.reduce(
    (b, c) => (!b || c.hours > b.hours ? c : b),
    undefined as (typeof metrics.compound)[number] | undefined,
  )

  return (
    <div className="flex grow flex-col">
      <div className="flex flex-wrap items-center gap-x-8 gap-y-3 border-b border-line pw-page py-4">
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="text-small font-semibold text-ink-3">Plan for time without contact</span>
          <SiteTitle />
          <div className="text-caption text-ink-3">
            {blackouts.length} {blackouts.length === 1 ? 'time' : 'times'} without contact and {nights}{' '}
            {nights === 1 ? 'night' : 'nights'} in {spanWords(metrics.windowHours)}
          </div>
        </div>
        <div className="basis-full lg:basis-0 lg:grow">
          <DateSlider />
        </div>
      </div>

      <div className="flex grow flex-col gap-6 pw-page py-5 lg:flex-row lg:py-6">
        {/* min-w-0: the timeline and the ledger are wider than this column and
            scroll inside their own panels. Without it the column takes their
            width as its minimum and pushes the packet off the right edge. */}
        <div className="flex min-w-0 grow flex-col gap-6">
          {!terrainModelled && (
            <UncertaintyNote>
              No terrain data outside 80°S, so this is worked out as if the ground were flat. Real hills could block more.
            </UncertaintyNote>
          )}
          <Panel className="flex flex-col">
            <div className="flex items-center gap-4 border-b border-line px-4 py-3">
              <SectionLabel>These dates, hour by hour</SectionLabel>
            </div>
            <ScrollRegion label="Hour-by-hour timeline, scrolls sideways" className="p-4">
              <BlackoutTimeline metrics={metrics} cursorH={cursorH} className="min-w-[860px]" />
            </ScrollRegion>
          </Panel>

          <Panel guide="plan-list" className="flex flex-col">
            <div className="flex items-center gap-4 border-b border-line px-4 py-3">
              <SectionLabel>Every time without contact</SectionLabel>
              <span className="ml-auto text-caption text-ink-3">sorted by length</span>
            </div>
            <ScrollRegion label="Every time without contact, scrolls sideways">
              <table className="w-full min-w-[720px] border-collapse text-left">
                <caption className="sr-only">
                  Every time without contact with Earth on these dates, longest first, and whether it overlaps a
                  night.
                </caption>
                <thead>
                  <tr className="bg-inset">
                    {['#', 'Start', 'End', 'Length', 'Also dark?'].map((h) => (
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
                        None: Earth stayed above the skyline for all of these dates.
                      </td>
                    </tr>
                  )}
                  {blackouts.map((a, i) => {
                    // Whether a dark-and-silent stretch (from the API) falls inside
                    // this blackout; the ledger says so without adding up hours.
                    const overlaps = metrics.compound.some((c) => c.startH < a.endH && c.endH > a.startH && c.hours >= 0.25)
                    return (
                      <tr key={i} className={`border-t border-line ${overlaps ? 'bg-alert-wash' : ''}`}>
                        <td className="px-4 py-3 text-small text-ink-3 tnum">{i + 1}</td>
                        <td className="px-4 py-3 text-small text-ink tnum">
                          {a.openStart ? `before ${when(a.startH)}` : when(a.startH)}
                        </td>
                        <td className="px-4 py-3 text-small text-ink tnum">
                          {a.openEnd ? `after ${when(a.endH)}` : when(a.endH)}
                        </td>
                        <td className="px-4 py-3 text-right text-control font-semibold tnum">
                          {hoursWithUnit(a.hours, 0, a.openStart || a.openEnd)}
                        </td>
                        <td className="px-4 py-3 text-small">
                          {overlaps ? (
                            <span className="flex items-center gap-2 font-semibold text-alert">
                              <Icon name="alert" size={14} strokeWidth={2.4} />
                              yes, part of it is dark too
                            </span>
                          ) : (
                            <span className="text-ink-2">no, sunlit throughout</span>
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
            <div className="text-small font-semibold text-ink-2">
              Working alone
            </div>
            <div className="text-subhead font-semibold">What the lander must handle on its own</div>
            {noCompound && (
              <p className="text-small leading-5 text-ink-2">
                Sunlight and contact with Earth are never lost together on these dates, so nothing has to run alone;
                the battery still has to last the longest night.
              </p>
            )}
          </div>

          <div className="flex items-baseline gap-3 border-b border-line p-5">
            <span className="text-figure-lg leading-figure-lg-tight font-semibold tracking-figure tnum">
              {bound(packet.worstCompoundOpen)}
              {Math.round(packet.requiredAutonomyH)}
            </span>
            <div className="flex flex-col">
              <span className="text-lede text-ink-2">hours working alone</span>
              <span className="text-caption text-ink-3">
                {noCompound
                  ? 'never dark and out of contact at once'
                  : `the longest time dark and out of contact, ${hoursWithUnit(packet.worstCompoundH, 0, packet.worstCompoundOpen)}${
                      worstCompound ? ` from ${when(worstCompound.startH)}` : ''
                    }, plus ${marginPct}%`}
              </span>
            </div>
          </div>

          <PacketRow
            done
            title="Stored commands"
            detail={`${hoursWithUnit(packet.requiredAutonomyH)} of planned activity, sent up during the contact before.`}
            value={hoursWithUnit(packet.requiredAutonomyH)}
          />
          <PacketRow
            done
            title="Data storage"
            detail={`${hoursWithUnit(packet.requiredAutonomyH)} of science and health data at the payload’s own data rate, kept until the next contact.`}
            value="per payload"
          />
          <PacketRow
            alert={metrics.sun.longestDownH > SURVIVAL_LIMIT_H}
            title="Battery for the night"
            detail={
              packet.compoundInsideDark
                ? `The longest time without contact falls inside a night, and the battery has to last the longest night either way: ${hoursWithUnit(packet.survivalNeededH, 0, packet.survivalOpen)}.`
                : `No time without contact overlaps a night badly enough to matter, but the battery still has to last the longest night: ${hoursWithUnit(packet.survivalNeededH, 0, packet.survivalOpen)}.`
            }
            value={hoursWithUnit(packet.survivalNeededH, 0, packet.survivalOpen)}
          />
          <PacketRow
            done
            title="Handling faults"
            detail={`Rules that put the lander in a safe state for ${hoursWithUnit(packet.requiredAutonomyH)} without help from Earth, and a way to recover that does not need it.`}
            value="rules"
          />
          <PacketRow
            title="Decisions it makes itself"
            detail="Anything urgent that can’t wait for Earth: choosing targets, when to abort, which heaters to switch off first."
            value="to plan"
          />

          <div className="mt-auto flex flex-col gap-2.5 border-t border-line-strong p-5">
            {metrics.sun.longestDownH > SURVIVAL_LIMIT_H && (
              <p className="flex items-start gap-2 text-small leading-5 text-alert">
                <Icon name="alert" size={16} strokeWidth={2.2} className="mt-0.5 shrink-0" />
                The night alone is {Math.round(metrics.sun.longestDownH - SURVIVAL_LIMIT_H)} h past the{' '}
                {SURVIVAL_LIMIT_H} h battery limit, whatever the plan for working alone.
              </p>
            )}
            <Button
              variant="primary"
              onClick={() => download(`${site.id}-${stamp}-arcs.csv`, arcsCsv(exportSite), 'text/csv')}
            >
              <Icon name="table" size={16} strokeWidth={1.7} />
              Download as a spreadsheet (CSV)
            </Button>
            <details className="group">
              <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between text-small font-semibold text-ink-2 hover:text-ink [&::-webkit-details-marker]:hidden">
                More formats
                <Icon name="chevron" size={16} strokeWidth={2} className="text-ink-3 transition-transform group-open:rotate-180" />
              </summary>
              <div className="flex flex-col gap-2 pt-1">
                <Button onClick={() => download(`${site.id}-${stamp}-windows.txt`, spiceWindows(exportSite))}>
                  Download for SPICE (engineers)
                </Button>
                <p className="text-caption leading-caption text-ink-3">
                  Each sunlit, in-contact and dark-and-silent stretch in UTC, ready for NASA’s SPICE toolkit.
                </p>
              </div>
            </details>
          </div>
        </aside>
      </div>
    </div>
  )
}

/** One thing to plan: its name and size, with the detail one tap away. */
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
    <details className={`group border-b border-line ${alert ? 'bg-alert-wash' : ''}`}>
      <summary className="flex min-h-12 cursor-pointer list-none items-center gap-3.5 px-4 py-3 hover:bg-inset [&::-webkit-details-marker]:hidden">
        {/* A plain mark, not a box: this is a list of what to plan, not a checklist to tick. */}
        <span className="flex size-5 shrink-0 items-center justify-center" aria-hidden="true">
          {alert ? (
            <Icon name="alert" size={14} strokeWidth={2.6} className="text-alert" />
          ) : done ? (
            <Icon name="check" size={14} strokeWidth={2.6} className="text-ink-2" />
          ) : (
            <span className="size-1.5 bg-ink-3" />
          )}
        </span>
        <span className={`grow text-body font-semibold ${alert ? 'text-alert' : ''}`}>{title}</span>
        <span className={`shrink-0 text-small tnum ${alert ? 'text-alert' : 'text-ink'}`}>{value}</span>
        <Icon name="chevron" size={14} strokeWidth={2} className="shrink-0 text-ink-3 transition-transform group-open:rotate-180" />
      </summary>
      <p className="px-4 pb-3 pl-[3.25rem] text-small leading-5 text-ink-2">{detail}</p>
    </details>
  )
}
