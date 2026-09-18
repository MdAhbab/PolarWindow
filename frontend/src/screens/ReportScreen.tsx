import { useSiteMetricsMap } from '../lib/useMetricsMap'
import { SourcesLine } from '../components/Sources'
import { useFocusedView } from '../lib/mission'
import { useMission } from '../lib/store'
import { siteById } from '../lib/sites'
import { Ribbon } from '../components/Ribbon'
import { LoadingPanel } from '../components/States'
import { Button, SectionLabel } from '../components/ui'
import { Mark } from '../components/Icon'
import { rankSites, SURVIVAL_LIMIT_H, autonomyPacket } from '../lib/geometry/metrics'
import { hoursWithUnit, percent, shortDateUTC } from '../lib/format'

/**
 * S6 — the one page a planner can hand over.
 *
 * Forced to the light theme: this is made to be printed and projected, and the
 * light palette is the one that survives both.
 */
export function ReportScreen() {
  const reportMeta = useFocusedView().meta
  const { compareIds, windowStartH, windowHours } = useMission()
  const { map: metrics, done, total } = useSiteMetricsMap(compareIds)
  const ready = compareIds.every((id) => metrics[id])

  if (!ready) {
    return (
      <div className="p-6">
        <div className="max-w-2xl">
          <LoadingPanel done={done} total={total} />
        </div>
      </div>
    )
  }

  const order = rankSites(
    compareIds.map((id) => ({ siteId: id, metrics: metrics[id] })),
    'longestDark',
  )
  const survivors = order.filter((id) => metrics[id].sun.longestDownH <= SURVIVAL_LIMIT_H)
  const best = order[0]
  const bestPacket = autonomyPacket(metrics[best])

  return (
    <div className="flex grow flex-col items-center gap-4 bg-inset p-4 lg:p-8">
      <div className="flex w-full max-w-[816px] items-center justify-between">
        <SectionLabel>Export — one page, Letter, light theme</SectionLabel>
        <Button onClick={() => window.print()}>Print or save as PDF</Button>
      </div>

      <article
        data-theme="light"
        className="w-full max-w-[816px] bg-canvas p-10 text-ink shadow-[0_8px_24px_rgba(0,0,0,0.35)]"
        style={{ minHeight: 1056 }}
      >
        <header className="flex items-end justify-between gap-6 border-b-2 border-ink pb-3">
          <div className="flex items-center gap-3">
            <Mark size={30} />
            <span className="text-[17px] font-semibold tracking-[0.2em]">
              POLAR<span className="font-normal text-sun">&nbsp;WINDOW</span>
            </span>
          </div>
          <div className="text-right font-mono text-[13px] leading-5 text-ink-2">
            Landing site comparison
            <br />
            generated {new Date().toISOString().slice(0, 16).replace('T', ' ')} UTC
          </div>
        </header>

        <div className="mt-5 flex items-start justify-between gap-5">
          <div className="flex flex-col gap-2">
            <h1 className="text-[30px] leading-9 font-semibold tracking-[-0.015em] text-balance">
              {compareIds.length} candidates, one {Math.round(windowHours)} h window
            </h1>
            <p className="text-[16px] leading-6 text-ink-2">
              {shortDateUTC(windowStartH)} → {shortDateUTC(windowStartH + windowHours)} · survival limit{' '}
              {SURVIVAL_LIMIT_H} h of continuous darkness
            </p>
          </div>
          <div className="shrink-0 border-2 border-alert p-2 text-center">
            <div className="text-[14px] font-bold tracking-[0.1em] text-alert">SAMPLE DATA</div>
            <div className="text-[12px] text-ink-3">synthetic terrain · not flight values</div>
          </div>
        </div>

        <div className="mt-5 grid grid-cols-3 gap-4">
          {order.map((id, i) => {
            const m = metrics[id]
            const s = siteById(id)
            const over = m.sun.longestDownH > SURVIVAL_LIMIT_H
            return (
              <div key={id} className={`border bg-panel p-3.5 ${over ? 'border-2 border-alert' : 'border-line-strong'}`}>
                <div className="mb-2.5 flex items-baseline gap-2 border-b border-line pb-2">
                  <span className={`text-[20px] font-bold ${i === 0 ? 'text-earth' : 'text-ink-3'}`}>{i + 1}</span>
                  <span className="text-[15px] font-semibold">
                    {s.code} — {s.name.split(',')[0]}
                  </span>
                </div>
                <Figure label="Sunlight" value={hoursWithUnit(m.sun.upHours)} tone="text-sun" />
                <Figure label="Earth contact" value={hoursWithUnit(m.earth.upHours)} tone="text-earth" />
                <Figure
                  label={over ? 'Longest dark gap ▲' : 'Longest dark gap'}
                  value={hoursWithUnit(m.sun.longestDownH)}
                  tone={over ? 'text-alert' : 'text-ink'}
                />
                <Figure label="Longest RF blackout" value={hoursWithUnit(m.earth.longestDownH)} tone="text-ink" />
              </div>
            )
          })}
        </div>

        <div className="mt-5 flex flex-col gap-2.5">
          <div className="text-[13px] font-semibold tracking-[0.1em] text-ink-3 uppercase">
            Figure 1 — sunlight over the window. Solid = above the local skyline; hatched = blocked.
          </div>
          {order.map((id) => {
            const m = metrics[id]
            return (
              <div key={id} className="flex items-center gap-3">
                <span className="w-5 shrink-0 text-[16px] font-bold">{siteById(id).code}</span>
                <div className="grow">
                  <Ribbon
                    arcs={m.sun.arcs}
                    windowStartH={m.windowStartH}
                    windowHours={m.windowHours}
                    tone="sun"
                    height={22}
                    alertOverH={SURVIVAL_LIMIT_H}
                  />
                </div>
                <span className="w-14 shrink-0 text-right text-[14px] text-ink-2">
                  {percent(m.sun.fractionUp)}
                </span>
              </div>
            )
          })}
          <p className="text-[13px] leading-5 text-ink-2">
            Totals do not decide this. The pink hatch marks each site’s single longest night, and that is
            the number a battery has to survive.
          </p>
        </div>

        <div className="mt-5 border border-line-strong bg-panel p-4">
          <div className="mb-1.5 text-[13px] font-semibold tracking-[0.1em] text-ink-3 uppercase">
            Recommendation
          </div>
          <p className="text-[16px] leading-6">
            {survivors.length === 0 ? (
              <>
                No candidate in this set survives its longest night on stored energy alone. The binding
                constraint is latitude, not terrain: every site here except the ones within about a degree
                of the pole has a true seasonal night.
              </>
            ) : (
              <>
                <strong>{siteById(best).code}</strong> is the only one whose worst night (
                {hoursWithUnit(metrics[best].sun.longestDownH)}) fits inside the {SURVIVAL_LIMIT_H} h limit
                {survivors.length > 1
                  ? `, together with ${survivors
                      .slice(1)
                      .map((id) => siteById(id).code)
                      .join(' and ')}`
                  : ''}
                . It pays for that with Earth contact: {percent(metrics[best].earth.fractionUp)} of the
                window, in stretches broken by libration rather than by terrain.
              </>
            )}
          </p>
        </div>

        <div className="mt-4 flex gap-4">
          <div className="grow border border-line-strong bg-panel p-4">
            <div className="mb-1.5 text-[13px] font-semibold tracking-[0.1em] text-ink-3 uppercase">
              Autonomy required — site {siteById(best).code}
            </div>
            <p className="text-[16px] leading-6">
              Worst compound event {hoursWithUnit(bestPacket.worstCompoundH)} with neither sunlight nor an
              Earth link. With margin: <strong>{hoursWithUnit(bestPacket.requiredAutonomyH)}</strong> of
              command buffer, storage and autonomous fault response.
            </p>
          </div>
          <div className="w-60 shrink-0 border border-line-strong bg-panel p-4">
            <div className="mb-1.5 text-[13px] font-semibold tracking-[0.1em] text-ink-3 uppercase">
              Uncertainty
            </div>
            <p className="text-[16px] leading-6">
              Arc edges carry ±{metrics[best].sun.longestDownToleranceH.toFixed(2)} h from the elevation
              model’s vertical accuracy.
            </p>
          </div>
        </div>

        <footer className="mt-6 flex justify-between gap-5 border-t border-line-strong pt-2.5">
          <p className="font-mono text-[12px] leading-[18px] text-ink-2">
            <SourcesLine meta={reportMeta} />
            <br />
            Every figure is computed by this build from those inputs and is prefixed ≈. Not an official
            product of any space agency.
          </p>
          <span className="shrink-0 font-mono text-[12px] text-ink-2">page 1 of 1</span>
        </footer>
      </article>
    </div>
  )
}

function Figure({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className="mb-2">
      <div className="text-[12px] font-semibold tracking-[0.08em] text-ink-3 uppercase">{label}</div>
      <div className={`text-[24px] font-semibold tnum ${tone}`}>{value}</div>
    </div>
  )
}
