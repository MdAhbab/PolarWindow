import { useShallow } from 'zustand/react/shallow'
import { useSiteMetricsMap } from '../lib/useMetricsMap'
import { SourcesLine } from '../components/Sources'
import { useCompare, useFocusedView, useWindowParams } from '../lib/mission'
import { useMission } from '../lib/store'
import { siteById } from '../lib/sites'
import { useProvenance } from '../lib/useProvenance'
import { Ribbon } from '../components/Ribbon'
import { LoadingPanel, ProblemPanel } from '../components/States'
import { BriefPanel } from '../components/Agents'
import { Button, PROVENANCE_COPY, SectionLabel } from '../components/ui'
import { Mark } from '../components/Icon'
import { SURVIVAL_LIMIT_H } from '../lib/geometry/metrics'
import { rankLabel } from '../lib/rank'
import { comparisonCsv, download } from '../lib/export'
import { TERM, edgeMargin, hoursWithUnit, msFromModelH, percent, shortDate, spanWords } from '../lib/format'

/**
 * S6 — the one page a planner can hand over.
 *
 * Forced to the light theme: this is made to be printed and projected, and the
 * light palette is the one that survives both.
 */
export function ReportScreen() {
  const reportMeta = useFocusedView().meta
  const provenance = useProvenance()
  const { compareIds, windowStartH, windowHours, siteId } = useMission(
    useShallow((s) => ({
      compareIds: s.compareIds,
      windowStartH: s.windowStartH,
      windowHours: s.windowHours,
      siteId: s.siteId,
    })),
  )
  const { map: metrics, autonomy, done, total, error } = useSiteMetricsMap(compareIds)
  const w = useWindowParams()
  const ranking = useCompare(compareIds, w, 'longest_dark_s')
  const ready = compareIds.every((id) => metrics[id] && autonomy[id])

  if (!ready) {
    return (
      <div className="p-6">
        <div className="max-w-2xl">
          {error ? (
            <ProblemPanel error={error} fallbackTitle="Cannot build the report" />
          ) : (
            <LoadingPanel done={done} total={total} />
          )}
        </div>
      </div>
    )
  }

  // The server's order and ranks (ties share a rank). Request order until the
  // ranking arrives, so the page never waits on it.
  const items = ranking.data?.items ?? []
  const ranked = items.map((it) => it.site_id).filter((id) => compareIds.includes(id))
  const order = [...ranked, ...compareIds.filter((id) => !ranked.includes(id))]
  const itemOf = Object.fromEntries(items.map((it) => [it.site_id, it]))
  const rankOf = Object.fromEntries(items.map((it) => [it.site_id, it.rank])) as Record<string, number | null>
  const tiedOf = Object.fromEntries(items.map((it) => [it.site_id, it.tied])) as Record<string, boolean>
  const labelOf = (id: string) => {
    const it = itemOf[id]
    return it
      ? rankLabel({
          rank: it.rank,
          rankRange: it.rank_range,
          tied: it.tied,
          censored: it.censored,
          grazing: it.grazing,
          overLimit: metrics[id].sun.longestDownH > SURVIVAL_LIMIT_H,
          incomparableWith: it.incomparable_with.map((x) => siteById(x).code),
        })
      : undefined
  }
  // A night the window cuts short is a lower bound: it cannot be said to fit
  // inside the limit, only to exceed it.
  const survivors = order.filter(
    (id) => metrics[id].sun.longestDownH <= SURVIVAL_LIMIT_H && !metrics[id].sun.longestDownOpen,
  )
  const best = order[0]
  const terrainOf = (id: string) => siteById(id).terrainModelled
  const bestPacket = autonomy[best]
  const stamp = PROVENANCE_COPY[provenance]
  const exportRows = order.map((id) => ({
    site: { id, name: siteById(id).name, metrics: metrics[id], autonomy: autonomy[id] },
    rank: rankOf[id] ?? undefined,
    tied: tiedOf[id],
  }))

  return (
    <div className="flex grow flex-col items-center gap-4 bg-inset p-4 lg:p-8">
      <div className="flex w-full max-w-[816px] flex-wrap items-center justify-between gap-3">
        <SectionLabel>Printable report · one page</SectionLabel>
        <div className="flex flex-wrap gap-3">
          <Button
            onClick={() =>
              download(
                `comparison-${new Date().toISOString().slice(0, 10)}.csv`,
                comparisonCsv(exportRows, 'longest night'),
                'text/csv',
              )
            }
          >
            Download as CSV
          </Button>
          <Button onClick={() => window.print()}>Print or save as PDF</Button>
        </div>
      </div>

      <article
        data-theme="light"
        className="w-full max-w-[816px] bg-canvas p-5 text-ink shadow-page sm:p-10"
        style={{ minHeight: 1056 }}
      >
        <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2 border-b-2 border-ink pb-3">
          <div className="flex items-center gap-3">
            <Mark size={30} />
            <span className="text-title font-semibold tracking-wordmark">
              POLAR<span className="font-normal text-sun">&nbsp;WINDOW</span>
            </span>
          </div>
          <div className="font-mono text-small leading-5 text-ink-2 sm:text-right">
            Landing site comparison
            <br />
            generated {new Date().toISOString().slice(0, 16).replace('T', ' ')} UTC
          </div>
        </header>

        <div className="mt-5 flex flex-wrap items-start justify-between gap-5 sm:flex-nowrap">
          <div className="flex flex-col gap-2">
            <h1 className="text-figure leading-9 font-semibold tracking-display text-balance">
              {compareIds.length} candidate sites, {spanWords(windowHours)}
            </h1>
            <p className="text-lede leading-6 text-ink-2">
              {shortDate(msFromModelH(windowStartH))} → {shortDate(msFromModelH(windowStartH + windowHours))} · battery limit{' '}
              {SURVIVAL_LIMIT_H} h of continuous darkness
            </p>
          </div>
          {/* From /healthz, like the badge in the header -- never a typed-in
              label. This box used to read SAMPLE DATA / synthetic terrain
              unconditionally, which stopped being true when the terrain became
              LOLA and the positions SPICE. */}
          {/* Magenta means over the survival limit and nothing else, so the
              provenance stamp uses the uncertain edge, like the header badge. */}
          <div className="shrink-0 border-2 border-uncertain p-2 text-center" title={stamp.title}>
            <div className="text-body font-bold tracking-caps-md text-ink uppercase">{stamp.label}</div>
            <div className="text-caption text-ink-3">derived values · not flight values</div>
          </div>
        </div>

        <div className="mt-5 grid gap-4 sm:grid-cols-3">
          {order.map((id, i) => {
            const m = metrics[id]
            const s = siteById(id)
            const over = m.sun.longestDownH > SURVIVAL_LIMIT_H
            const rank = rankOf[id] ?? null
            const label = labelOf(id)
            return (
              <div key={id} className={`border bg-panel p-3.5 ${over ? 'border-2 border-alert' : 'border-line-strong'}`}>
                <div className="mb-2.5 flex flex-wrap items-baseline gap-x-2 gap-y-0.5 border-b border-line pb-2">
                  <span
                    className={`text-subhead font-bold ${
                      rank === null ? 'text-uncertain' : label?.kind === 'best' ? 'text-ink' : 'text-ink-3'
                    }`}
                  >
                    {rank ?? (itemOf[id] ? '–' : i + 1)}
                  </span>
                  <span className="text-control font-semibold">
                    {s.code} · {s.name.split(',')[0]}
                  </span>
                  {label && (
                    <span
                      className={`w-full text-caption ${label.tone === 'uncertain' ? 'text-uncertain' : 'text-ink-3'}`}
                      title={label.title}
                    >
                      {label.kind === 'unranked' ? `Too close to call${label.title ? `: ${label.title}` : ''}` : label.text}
                    </span>
                  )}
                </div>
                <Figure label={TERM.sunHours.label} value={hoursWithUnit(m.sun.upHours)} tone="text-sun" />
                <Figure label={TERM.earthHours.label} value={hoursWithUnit(m.earth.upHours)} tone="text-earth" />
                <Figure
                  label={over ? `${TERM.longestDark.label} ▲` : TERM.longestDark.label}
                  value={hoursWithUnit(m.sun.longestDownH, 0, m.sun.longestDownOpen)}
                  tone={over ? 'text-alert' : 'text-ink'}
                />
                <Figure
                  label={TERM.longestBlackout.label}
                  value={hoursWithUnit(m.earth.longestDownH, 0, m.earth.longestDownOpen)}
                  tone="text-ink"
                />
              </div>
            )
          })}
        </div>

        <div className="mt-5 flex flex-col gap-2.5">
          <div className="text-small font-semibold tracking-caps-md text-ink-3 uppercase">
            Sunlight over these dates (solid: Sun up; hatched: blocked)
          </div>
          {order.map((id) => {
            const m = metrics[id]
            return (
              <div key={id} className="flex items-center gap-3">
                <span className="w-5 shrink-0 text-lede font-bold">{siteById(id).code}</span>
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
                <span className="w-14 shrink-0 text-right text-body text-ink-2">
                  {percent(m.sun.fractionUp)}
                </span>
              </div>
            )
          })}
          <p className="text-small leading-5 text-ink-2">
            Totals do not decide this. The magenta hatch marks a site’s single longest night where it runs
            past the {SURVIVAL_LIMIT_H} h limit, and that is the number a battery has to survive. “≥” marks a
            night the chosen dates cut short: the real one is longer.
          </p>
        </div>

        <div className="mt-5 border border-line-strong bg-panel p-4">
          <div className="mb-1.5 text-small font-semibold tracking-caps-md text-ink-3 uppercase">
            Recommendation
          </div>
          <p className="text-lede leading-6">
            {survivors.length === 0 ? (
              <>
                No candidate in this set survives its longest night on its battery alone. What limits them
                is latitude, not terrain: every site here except those within about a degree of the pole
                has a real seasonal night.
              </>
            ) : (
              <>
                <strong>{survivors.map((id) => siteById(id).code).join(' and ')}</strong>{' '}
                {survivors.length > 1 ? 'are the ones' : 'is the only one'} whose worst night fits inside
                the {SURVIVAL_LIMIT_H} h limit ({survivors
                  .map((id) => `${siteById(id).code} ${hoursWithUnit(metrics[id].sun.longestDownH)}`)
                  .join(', ')}
                ). {siteById(survivors[0]).code} pays for that with Earth contact:{' '}
                {percent(metrics[survivors[0]].earth.fractionUp)} of the time.
              </>
            )}
          </p>
        </div>

        <div className="mt-4 flex flex-col gap-4 sm:flex-row">
          <div className="grow border border-line-strong bg-panel p-4">
            <div className="mb-1.5 text-small font-semibold tracking-caps-md text-ink-3 uppercase">
              Time working alone: site {siteById(best).code}
            </div>
            <p className="text-lede leading-6">
              The longest time dark and out of contact is{' '}
              {hoursWithUnit(bestPacket.worstCompoundH, 0, bestPacket.worstCompoundOpen)}. With a{' '}
              {Math.round(bestPacket.marginFraction * 100)}% margin: <strong>{hoursWithUnit(bestPacket.requiredAutonomyH)}</strong>{' '}
              of stored commands, data storage and fault handling. The battery still has to last the longest night,{' '}
              {hoursWithUnit(bestPacket.survivalNeededH, 0, bestPacket.survivalOpen)}.
            </p>
          </div>
          <div className="shrink-0 border border-line-strong bg-panel p-4 sm:w-60">
            <div className="mb-1.5 text-small font-semibold tracking-caps-md text-ink-3 uppercase">
              Uncertainty
            </div>
            <p className="text-lede leading-6">
              {metrics[best].sun.longestDownArc?.grazing
                ? 'The longest night starts or ends too shallowly to time; its length stands, its edges do not.'
                : `The longest night’s start and end carry ${edgeMargin(metrics[best].sun.longestDownArc, terrainOf(best))} from the terrain map’s height accuracy.`}
            </p>
          </div>
        </div>

        <footer className="mt-6 flex flex-wrap justify-between gap-5 border-t border-line-strong pt-2.5">
          <p className="font-mono text-caption leading-caption text-ink-2">
            <SourcesLine meta={reportMeta} />
            <br />
            Every figure is an estimate computed by this build from those inputs. Not an official
            product of any space agency.
          </p>
          <span className="shrink-0 font-mono text-caption text-ink-2">page 1 of 1</span>
        </footer>
      </article>

      <div className="w-full max-w-[816px] print:hidden">
        <BriefPanel siteId={siteId} start={w.start} end={w.end} />
      </div>
    </div>
  )
}

function Figure({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className="mb-2">
      <div className="text-caption font-semibold tracking-caps-sm text-ink-3 uppercase">{label}</div>
      <div className={`text-heading font-semibold tnum ${tone}`}>{value}</div>
    </div>
  )
}
