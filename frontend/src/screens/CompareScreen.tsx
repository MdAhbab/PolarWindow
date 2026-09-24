import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { useSiteMetricsMap } from '../lib/useMetricsMap'
import { useCompare, useWindowParams } from '../lib/mission'
import { useMission } from '../lib/store'
import { hasSite, siteById } from '../lib/sites'
import { useMissions } from '../lib/api/queries'
import type { CompareItemDTO } from '../lib/api/client'
import { rankLabel, type RankLabel } from '../lib/rank'
import { DateSlider } from '../components/DateSlider'
import { Ribbon } from '../components/Ribbon'
import { KeyNumberTile } from '../components/KeyNumbers'
import { LoadingPanel, ProblemPanel } from '../components/States'
import { AdvisePanel } from '../components/Agents'
import { Panel, SectionLabel, Segmented } from '../components/ui'
import { Icon } from '../components/Icon'
import { useReducedMotion } from '../hooks/useMotion'
import { metricValue, SURVIVAL_LIMIT_H } from '../lib/geometry/metrics'
import { bound, coords, hoursWithUnit, termLabel } from '../lib/format'
import type { MetricKey, SiteMetrics } from '../lib/types'

const GAP = 24

/** The UI's metric names, as the API spells them. */
const API_METRIC: Record<MetricKey, string> = {
  sunHours: 'sunlit_s',
  earthHours: 'earth_contact_s',
  longestDark: 'longest_dark_s',
  longestBlackout: 'longest_blackout_s',
}

const RANKS: { value: MetricKey; label: string }[] = [
  { value: 'sunHours', label: 'Time in the Sun' },
  { value: 'earthHours', label: 'Time it can call home' },
  { value: 'longestDark', label: 'Longest night' },
  { value: 'longestBlackout', label: "Longest time it can't call home" },
]

function useIsWide() {
  const [wide, setWide] = useState(() => typeof window !== 'undefined' && window.innerWidth >= 1024)
  useEffect(() => {
    const on = () => setWide(window.innerWidth >= 1024)
    window.addEventListener('resize', on)
    return () => window.removeEventListener('resize', on)
  }, [])
  return wide
}

/**
 * S3 — the decision screen.
 *
 * M3: when the ranking changes the columns keep their identity and slide. The
 * finding is the movement, so a cross-fade would throw away the only thing
 * worth seeing.
 */
export function CompareScreen() {
  const { compareIds, rankBy, setRankBy, face, cursorH } = useMission(
    useShallow((s) => ({
      compareIds: s.compareIds,
      rankBy: s.rankBy,
      setRankBy: s.setRankBy,
      face: s.face,
      cursorH: s.cursorH,
    })),
  )
  const { map: metrics, done, total, isPending, error } = useSiteMetricsMap(compareIds)
  const w = useWindowParams()
  const ranking = useCompare(compareIds, w, API_METRIC[rankBy])
  const [params] = useSearchParams()
  const fromId = params.get('from')
  const fromMission = useMissions({}).data?.items.find((m) => m.id === fromId)
  const seeded = fromMission?.siteId && compareIds[0] === fromMission.siteId ? fromMission : undefined
  const compute = { status: isPending ? 'running' : 'ready', done, total } as const
  const reduced = useReducedMotion()
  const wide = useIsWide()
  const ref = useRef<HTMLDivElement>(null)
  const [colW, setColW] = useState(0)
  const [colH, setColH] = useState(560)
  const cards = useRef(new Map<string, HTMLDivElement>())

  const ready = compareIds.every((id) => metrics[id])

  useLayoutEffect(() => {
    if (!ref.current || !wide || !ready) return
    const measure = () => {
      const w = ref.current?.clientWidth ?? 0
      setColW((w - GAP * (compareIds.length - 1)) / compareIds.length)
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [compareIds.length, wide, ready])

  // The absolutely positioned columns give the container no height of their
  // own, so it takes the tallest card's -- measured at the real column width
  // and re-measured when a card's content changes. It used to only ever grow,
  // and the first measurement was at zero width, which left a gap of several
  // hundred pixels under the cards.
  useLayoutEffect(() => {
    if (!wide || !colW) return
    const measure = () => {
      const hs = [...cards.current.values()].map((el) => el.offsetHeight)
      if (hs.length) setColH(Math.max(...hs))
    }
    measure()
    const ro = new ResizeObserver(measure)
    for (const el of cards.current.values()) ro.observe(el)
    return () => ro.disconnect()
  }, [wide, colW, compareIds])

  // Order, ranks and ties are the server's (`POST /compare`), so this screen
  // and the API can never disagree, and sites the data cannot tell apart share
  // a rank instead of being put in an order that is not there. Until the
  // ranking arrives the columns keep request order.
  const { order, items, tiedWith } = useMemo(() => {
    const list = ranking.data?.items ?? []
    const known = list.map((it) => it.site_id).filter((id) => compareIds.includes(id))
    const rest = compareIds.filter((id) => !known.includes(id))
    const tied: Record<string, string[]> = {}
    for (const group of ranking.data?.ties ?? []) {
      for (const id of group) tied[id] = group.filter((x) => x !== id)
    }
    return {
      order: [...known, ...rest],
      items: Object.fromEntries(list.map((it) => [it.site_id, it])) as Record<string, CompareItemDTO>,
      tiedWith: tied,
    }
  }, [ranking.data, compareIds])

  // U11: what each site may be called, from the server's rank, range and
  // flags. "best" only for a definite first place that is neither cut short
  // nor over the survival limit.
  const code = (id: string) => (hasSite(id) ? siteById(id).code : id)
  const labels: Record<string, RankLabel | undefined> = {}
  for (const id of compareIds) {
    const it = items[id]
    const m = metrics[id]
    labels[id] = it
      ? rankLabel({
          rank: it.rank,
          rankRange: it.rank_range,
          tied: it.tied,
          censored: it.censored,
          grazing: it.grazing,
          overLimit: m ? m.sun.longestDownH > SURVIVAL_LIMIT_H : false,
          incomparableWith: it.incomparable_with.map(code),
        })
      : undefined
  }

  const orderLabel = order
    .map((id) => `${code(id)}${labels[id] ? ` (${labels[id]!.text})` : ''}`)
    .join(' → ')
  const tieSentence = (ranking.data?.ties ?? [])
    .map((g) => `${g.map((id) => siteById(id).code).join(' and ')} are tied — the data cannot tell them apart`)
    .join('. ')

  if (!ready) {
    return (
      <div className="flex grow flex-col gap-6 p-4 lg:p-6">
        <DateSlider />
        <div className="max-w-2xl">
          {error ? (
            <ProblemPanel error={error} fallbackTitle="Cannot compute the comparison" />
          ) : (
            <LoadingPanel done={done} total={total} />
          )}
        </div>
      </div>
    )
  }

  const best = order[0]
  const bestLabel = labels[best]
  const leads = bestLabel?.kind === 'best' || (bestLabel?.kind === 'joint' && items[best]?.rank === 1)
  const disqualified = order.filter((id) => metrics[id].sun.longestDownH > SURVIVAL_LIMIT_H)
  const unavailable = ranking.data?.unavailable ?? []

  return (
    <div className="flex grow flex-col">
      <div className="flex flex-wrap items-end gap-x-8 gap-y-4 border-b border-line px-4 py-4 lg:px-6">
        <DateSlider />
        <div className="flex min-w-0 max-w-full flex-col gap-2">
          <SectionLabel as="div">Rank by</SectionLabel>
          <Segmented options={RANKS} value={rankBy} onChange={setRankBy} label="Rank by" />
        </div>
      </div>

      <p aria-live="polite" className="sr-only">
        Now ranked by {termLabel(rankBy, face).label}: {orderLabel}.{tieSentence ? ` ${tieSentence}.` : ''}
      </p>

      {(seeded || unavailable.length > 0 || ranking.error) && (
        <div className="flex flex-col gap-1 border-b border-line px-4 py-3 text-[13px] leading-5 text-ink-2 lg:px-6">
          {seeded && (
            <p>
              Seeded from {seeded.name}: its target and the three candidate sites nearest to it by distance.
            </p>
          )}
          {unavailable.map((u) => (
            <p key={u.site_id}>
              {code(u.site_id)} could not be ranked: {u.reason}
            </p>
          ))}
          {ranking.error ? (
            <p>
              The ranking did not load ({(ranking.error as { title?: string }).title ?? 'request failed'}), so the
              columns are in the order you chose them and none is called best.
            </p>
          ) : null}
        </div>
      )}

      <div className="grow p-4 lg:p-6">
        {wide ? (
          <div ref={ref} className="relative" style={{ height: colH }}>
            {compareIds.map((id) => {
              const position = order.indexOf(id)
              return (
                <div
                  key={id}
                  ref={(el) => {
                    if (el) cards.current.set(id, el)
                    else cards.current.delete(id)
                  }}
                  className="absolute top-0 left-0"
                  style={{
                    width: colW,
                    transform: `translateX(${position * (colW + GAP)}px)`,
                    transition: reduced ? 'none' : 'transform 460ms cubic-bezier(.2,.8,.2,1)',
                  }}
                >
                  <CompareCard
                    siteId={id}
                    item={items[id]}
                    label={labels[id]}
                    metrics={metrics[id]}
                    cursorH={cursorH}
                    rankBy={rankBy}
                  />
                </div>
              )
            })}
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {order.map((id) => (
              <CompareCard
                key={id}
                siteId={id}
                item={items[id]}
                label={labels[id]}
                metrics={metrics[id]}
                cursorH={cursorH}
                rankBy={rankBy}
              />
            ))}
          </div>
        )}
      </div>

      <footer className="flex flex-wrap items-center gap-x-8 gap-y-3 border-t border-line bg-panel px-4 py-5 lg:px-6">
        <SectionLabel className="shrink-0">The trade-off, stated</SectionLabel>
        <p className="max-w-4xl text-[15px] leading-6 text-ink">
          Ranked by {termLabel(rankBy, face).label.toLowerCase()},{' '}
          {!leads ? (
            <>
              no site can be called first: {bestLabel ? 'a value cut short by the window, or an edge that cannot be timed, overlaps the others' : 'the ranking has not arrived'}.{' '}
            </>
          ) : tiedWith[best]?.length ? (
            <>
              <strong>{[best, ...tiedWith[best]].map(code).join(' and ')}</strong> share the lead — the data
              cannot separate them.{' '}
            </>
          ) : (
            <>
              <strong>{code(best)}</strong> leads.{' '}
            </>
          )}
          {disqualified.length > 0 ? (
            <>
              {disqualified.map(code).join(' and ')}{' '}
              {disqualified.length > 1 ? 'are' : 'is'} out on the night alone —{' '}
              <span className="text-alert">
                over the {SURVIVAL_LIMIT_H} h survival limit
              </span>
              , and no launch date changes that, because the gap is terrain and latitude, not timing.
            </>
          ) : (
            'Every candidate here survives its longest night, so the choice is genuinely about what the payload needs.'
          )}
        </p>
        <span className="ml-auto font-mono text-[12px] text-ink-3">
          {compute.status === 'ready' ? `order: ${orderLabel}` : 'computing…'}
        </span>
      </footer>

      <div className="px-4 py-6 lg:px-6">
        <AdvisePanel start={w.start} end={w.end} />
      </div>
    </div>
  )
}

function CompareCard({
  siteId,
  item,
  label,
  metrics,
  cursorH,
  rankBy,
}: {
  siteId: string
  /** The server's ranking of this site; undefined until it arrives. */
  item: CompareItemDTO | undefined
  /** What the site may be called (U11); undefined until the ranking arrives. */
  label: RankLabel | undefined
  metrics: SiteMetrics
  cursorH: number
  rankBy: MetricKey
}) {
  const site = siteById(siteId)
  const face = useMission((s) => s.face)
  const over = metrics.sun.longestDownH > SURVIVAL_LIMIT_H
  const rank = item?.rank ?? null
  const tied = Boolean(item?.tied)
  const leading = label?.kind === 'best' || (label?.kind === 'joint' && rank === 1)
  const range = item?.rank_range ?? []
  const openFor: Record<MetricKey, boolean> = {
    sunHours: false,
    earthHours: false,
    longestDark: Boolean(metrics.sun.longestDownOpen),
    longestBlackout: Boolean(metrics.earth.longestDownOpen),
  }

  return (
    <Panel
      className={`flex flex-col ${over ? 'border-alert' : leading ? 'border-ink' : ''}`}
      as="section"
    >
      <div className="flex items-start gap-3 border-b border-line p-4">
        {rank !== null ? (
          <span
            className={`inline-flex size-7 shrink-0 items-center justify-center text-[14px] font-bold ${
              leading ? 'bg-ink text-canvas' : 'bg-line-strong text-ink'
            }`}
            aria-label={`Rank ${rank}`}
          >
            {rank}
          </span>
        ) : (
          // No place can be stated: the badge carries the range the server
          // gives, in the uncertain ink and dashed edge, never a number alone.
          <span
            className="inline-flex h-7 min-w-7 shrink-0 items-center justify-center border border-dashed border-uncertain px-1 text-[12px] font-bold text-uncertain"
            aria-label={label?.title ?? 'Rank not stated'}
            title={label?.title}
          >
            {range.length === 2 ? `${range[0]}–${range[1]}` : '?'}
          </span>
        )}
        <div className="flex min-w-0 flex-col gap-0.5">
          <div className="text-[17px] font-semibold">
            {site.code} — {site.name}
          </div>
          {label && (
            <div
              className={`text-[13px] font-semibold ${label.tone === 'uncertain' ? 'text-uncertain' : 'text-ink'}`}
              title={label.title}
            >
              {label.text}
              {label.title && <span className="sr-only"> ({label.title})</span>}
            </div>
          )}
          {tied && <div className="text-[12px] text-ink-2">tied — the data cannot separate these</div>}
          <div className="font-mono text-[11px] text-ink-3">{coords(site.latDeg, site.lonDeg)}</div>
        </div>
        {over && (
          <span className="ml-auto inline-flex shrink-0 items-center gap-1.5 bg-alert-deep px-2 py-1 text-[11px] font-semibold tracking-[0.08em] text-alert uppercase">
            <Icon name="alert" size={12} strokeWidth={2.4} />
            Over limit
          </span>
        )}
      </div>

      <div className="p-4">
        <KeyNumberTile
          label={`${termLabel(rankBy, face).label}${label?.kind === 'best' ? ' · best' : ''}`}
          expert={termLabel(rankBy, face).expert}
          value={metricValue(metrics, rankBy)}
          open={openFor[rankBy]}
          tone={rankBy === 'sunHours' ? 'sun' : rankBy === 'earthHours' ? 'earth' : over ? 'alert' : 'neutral'}
          size="md"
          fraction={
            rankBy === 'longestDark'
              ? metrics.sun.longestDownH / SURVIVAL_LIMIT_H
              : metricValue(metrics, rankBy) / metrics.windowHours
          }
        />
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-3 px-4">
        <Mini label="Sun, h" value={metrics.sun.upHours} tone="text-sun" />
        <Mini label="Call home, h" value={metrics.earth.upHours} tone="text-earth" />
        <Mini
          label="Longest night, h"
          value={metrics.sun.longestDownH}
          open={metrics.sun.longestDownOpen}
          tone={over ? 'text-alert' : 'text-ink'}
        />
        <Mini label="Can't call home, h" value={metrics.earth.longestDownH} open={metrics.earth.longestDownOpen} tone="text-ink" />
      </div>

      <div className="flex flex-col gap-3 p-4">
        <div className="flex flex-col gap-1.5">
          <span className="text-[11px] font-semibold tracking-[0.1em] text-sun uppercase">Sun over the window</span>
          <Ribbon
            arcs={metrics.sun.arcs}
            windowStartH={metrics.windowStartH}
            windowHours={metrics.windowHours}
            tone="sun"
            cursorH={cursorH}
            alertOverH={SURVIVAL_LIMIT_H}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <span className="text-[11px] font-semibold tracking-[0.1em] text-earth uppercase">Earth contact</span>
          <Ribbon
            arcs={metrics.earth.arcs}
            windowStartH={metrics.windowStartH}
            windowHours={metrics.windowHours}
            tone="earth"
            cursorH={cursorH}
          />
        </div>
      </div>

      <div className="mt-auto border-t border-line bg-raised p-4">
        <p className="text-[14px] leading-6 text-ink">
          {over
            ? `${metrics.sun.longestDownOpen ? 'At least ' : ''}${Math.round(metrics.sun.longestDownH - SURVIVAL_LIMIT_H)} h over the limit in a single block. ${site.note}`
            : metrics.sun.longestDownOpen
              ? `At most ${hoursWithUnit(SURVIVAL_LIMIT_H - metrics.sun.longestDownH)} of margin: the window cuts this night short. ${site.note}`
              : `${hoursWithUnit(SURVIVAL_LIMIT_H - metrics.sun.longestDownH)} of margin on the night. ${site.note}`}
        </p>
      </div>
    </Panel>
  )
}

function Mini({
  label,
  value,
  tone,
  open,
}: {
  label: string
  value: number
  tone: string
  open?: boolean
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] font-semibold tracking-[0.08em] text-ink-3 uppercase">{label}</span>
      <span className={`text-[22px] leading-6 font-semibold tnum ${tone}`}>
        {bound(open)}
        {Math.round(value)}
      </span>
    </div>
  )
}
