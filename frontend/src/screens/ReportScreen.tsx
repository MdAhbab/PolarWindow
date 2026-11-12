import { useShallow } from 'zustand/react/shallow'
import { PageHeader } from '../components/Page'
import { useSiteMetricsMap } from '../lib/useMetricsMap'
import { SourcesLine } from '../components/Sources'
import { useCompare, useFocusedView, useWindowParams } from '../lib/mission'
import { useMission } from '../lib/store'
import { siteById } from '../lib/sites'
import { useProvenance } from '../lib/useProvenance'
import { Ribbon } from '../components/Ribbon'
import { LoadingPanel, ProblemPanel } from '../components/States'
import { BriefPanel } from '../components/Agents'
import { Button, PROVENANCE_COPY } from '../components/ui'
import { BrandName } from '../components/Brand'
import { longestNight, nightAgainstLimit } from '../lib/geometry/metrics'
import { useBatteryLimit } from '../lib/api/lifecycleQueries'
import { EnterLimit, LimitPhrase, LimitTally } from '../components/KeyNumbers'
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
  // R2: the team's entered battery limit, or 120 h said to be assumed.
  const limit = useBatteryLimit()
  const ready = compareIds.every((id) => metrics[id] && autonomy[id]) && !limit.pending

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
          incomparableWith: it.incomparable_with.map((x) => siteById(x).name),
          places: items.length,
          metric: 'longestDark',
        })
      : undefined
  }
  const terrainOf = (id: string) => siteById(id).terrainModelled
  // Each longest night against the limit, with its margin (R2, R6). A night
  // the dates cut short is a lower bound: it can be past the limit, never
  // inside it.
  const nightOf = (id: string) => longestNight(metrics[id], terrainOf(id))
  const againstOf = (id: string) => nightAgainstLimit(nightOf(id), limit.h)
  // The first in the order by longest night: its packet is the one shown.
  const first = order[0]
  const firstPacket = autonomy[first]
  const stamp = PROVENANCE_COPY[provenance]
  const exportRows = order.map((id) => ({
    site: { id, name: siteById(id).name, metrics: metrics[id], autonomy: autonomy[id] },
    rank: rankOf[id] ?? undefined,
    tied: tiedOf[id],
  }))

  return (
    <div className="pw-page flex grow flex-col items-center gap-6 pt-6 pb-8 lg:gap-8 lg:pt-8 print:p-0">
      <div className="w-full max-w-[816px] print:hidden">
        <PageHeader
          compact
          crumbs={[{ label: 'Landing sites', to: '/map' }, { label: 'Compare', to: '/compare' }, { label: 'Printable report' }]}
          title="Printable report"
          titleExtra="· one page"
          actions={
            <>
          <Button
            onClick={() =>
              download(
                `comparison-${new Date().toISOString().slice(0, 10)}.csv`,
                comparisonCsv(exportRows, 'longest night'),
                'text/csv',
              )
            }
          >
            Download as a spreadsheet (CSV)
          </Button>
              <Button variant="primary" onClick={() => window.print()}>
                Print or save as PDF
              </Button>
            </>
          }
        />
      </div>

      <article
        data-theme="light"
        className="w-full max-w-[816px] bg-canvas p-5 text-ink shadow-page sm:p-10"
        style={{ minHeight: 1056 }}
      >
        <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2 border-b-2 border-ink pb-3">
          <BrandName mark="h-10" words="h-3" />
          <div className="text-small leading-5 text-ink-2 sm:text-right">
            Landing site comparison
            <br />
            <span className="font-mono">
              generated {new Date().toISOString().slice(0, 16).replace('T', ' ')} UTC
            </span>
          </div>
        </header>

        <div className="mt-5 flex flex-wrap items-start justify-between gap-5 sm:flex-nowrap">
          <div className="flex flex-col gap-2">
            <h2 className="text-figure leading-9 font-semibold tracking-display text-balance">
              {compareIds.length} candidate sites, {spanWords(windowHours)}
            </h2>
            <p className="text-lede leading-6 text-ink-2">
              {shortDate(msFromModelH(windowStartH))} → {shortDate(msFromModelH(windowStartH + windowHours))} · against{' '}
              <LimitPhrase limit={limit} /> <EnterLimit limit={limit} className="text-body" />
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
            // Magenta only past the limit by more than the night's margin.
            const over = againstOf(id).kind === 'past'
            const rank = rankOf[id] ?? null
            const label = labelOf(id)
            return (
              <div key={id} className={`border bg-panel p-3.5 ${over ? 'border-2 border-alert' : 'border-line-strong'}`}>
                <div className="mb-2.5 flex flex-wrap items-baseline gap-x-2 gap-y-0.5 border-b border-line pb-2">
                  <span
                    className={`text-subhead font-bold ${
                      rank === null ? 'text-uncertain' : rank === 1 ? 'text-ink' : 'text-ink-3'
                    }`}
                  >
                    {/* No place stated: no number, and no dash standing in for one; the line below says why. */}
                    {rank ?? (itemOf[id] ? '' : i + 1)}
                  </span>
                  <span className="text-control font-semibold">
                    {s.code} · {s.name.split(',')[0]}
                  </span>
                  {label && (
                    <span
                      className={`w-full text-caption ${label.tone === 'uncertain' ? 'text-uncertain' : 'text-ink-3'}`}
                      title={label.title}
                    >
                      {/* A place in the order by longest night, never a verdict (R5); a range in words (V140). */}
                      {label.kind === 'unranked'
                        ? `Too close to call: ${label.title ?? label.why ?? 'no place can be stated'}`
                        : `${label.text} by longest night`}
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
                    windowStartIso={m.windowStartIso}
                    windowHours={m.windowHours}
                    tone="sun"
                    height={22}
                    alertOverH={limit.h}
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
            past <LimitPhrase limit={limit} /> by more than its margin; that is the stretch a battery has to
            last. “≥” marks a night the chosen dates cut short: the real one is longer.
          </p>
        </div>

        {/* R6: what was worked out for these sites and dates, counted, with
            each night's margin and the limit's label. No verdict, and no
            sentence that is not derived from the sites compared. Same box,
            same place on the page (C-7). */}
        <div className="mt-5 border border-line-strong bg-panel p-4">
          <div className="mb-1.5 text-small font-semibold tracking-caps-md text-ink-3 uppercase">
            Against the battery limit
          </div>
          <p className="text-lede leading-6">
            <LimitTally
              sites={order.map((id) => ({ name: siteById(id).name, night: nightOf(id), against: againstOf(id) }))}
              limit={limit}
              figures
            />
          </p>
        </div>

        <div className="mt-4 flex flex-col gap-4 sm:flex-row">
          <div className="grow border border-line-strong bg-panel p-4">
            <div className="mb-1.5 text-small font-semibold tracking-caps-md text-ink-3 uppercase">
              Time working alone: site {siteById(first).code}
            </div>
            <p className="text-lede leading-6">
              The longest time dark and out of contact is{' '}
              {hoursWithUnit(firstPacket.worstCompoundH, 0, firstPacket.worstCompoundOpen)}. With a{' '}
              {Math.round(firstPacket.marginFraction * 100)}% margin: <strong>{hoursWithUnit(firstPacket.requiredAutonomyH)}</strong>{' '}
              of stored commands, data storage and fault handling. The battery still has to last the longest night,{' '}
              {hoursWithUnit(firstPacket.survivalNeededH, 0, firstPacket.survivalOpen)}.
            </p>
          </div>
          <div className="shrink-0 border border-line-strong bg-panel p-4 sm:w-60">
            <div className="mb-1.5 text-small font-semibold tracking-caps-md text-ink-3 uppercase">
              Uncertainty
            </div>
            <p className="text-lede leading-6">
              {metrics[first].sun.longestDownArc?.grazing
                ? 'The longest night starts or ends too shallowly to time; its length stands, its edges do not.'
                : `The longest night’s start and end carry ${edgeMargin(metrics[first].sun.longestDownArc, terrainOf(first))} from the terrain map’s height accuracy.`}
            </p>
          </div>
        </div>

        <footer className="mt-6 flex flex-wrap justify-between gap-5 border-t border-line-strong pt-2.5">
          <p className="text-caption leading-caption text-ink-2">
            <span className="font-mono">
              <SourcesLine meta={reportMeta} />
            </span>
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
