import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { useSiteMetricsMap } from '../lib/useMetricsMap'
import { useCompare, useWindowParams } from '../lib/mission'
import { useMission } from '../lib/store'
import { siteById } from '../lib/sites'
import { DateSlider } from '../components/DateSlider'
import { Ribbon } from '../components/Ribbon'
import { KeyNumberTile } from '../components/KeyNumbers'
import { LoadingPanel } from '../components/States'
import { Panel, SectionLabel, Segmented } from '../components/ui'
import { Icon } from '../components/Icon'
import { useReducedMotion } from '../hooks/useMotion'
import { metricValue, SURVIVAL_LIMIT_H } from '../lib/geometry/metrics'
import { TERM, bound, coords, hoursWithUnit } from '../lib/format'
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
  { value: 'sunHours', label: 'Sunlight' },
  { value: 'earthHours', label: 'Earth contact' },
  { value: 'longestDark', label: 'Dark gap' },
  { value: 'longestBlackout', label: 'RF blackout' },
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
  const { map: metrics, done, total, isPending } = useSiteMetricsMap(compareIds)
  const ranking = useCompare(compareIds, useWindowParams(), API_METRIC[rankBy])
  const compute = { status: isPending ? 'running' : 'ready', done, total } as const
  const reduced = useReducedMotion()
  const wide = useIsWide()
  const ref = useRef<HTMLDivElement>(null)
  const [colW, setColW] = useState(0)
  const [colH, setColH] = useState(560)

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

  // Order, ranks and ties are the server's (`POST /compare`), so this screen
  // and the API can never disagree, and sites the data cannot tell apart share
  // a rank instead of being put in an order that is not there. Until the
  // ranking arrives the columns keep request order.
  const { order, ranks, tiedWith } = useMemo(() => {
    const items = ranking.data?.items ?? []
    const known = items.map((it) => it.site_id).filter((id) => compareIds.includes(id))
    const rest = compareIds.filter((id) => !known.includes(id))
    const tied: Record<string, string[]> = {}
    for (const group of ranking.data?.ties ?? []) {
      for (const id of group) tied[id] = group.filter((x) => x !== id)
    }
    return {
      order: [...known, ...rest],
      ranks: Object.fromEntries(items.map((it) => [it.site_id, it.rank])) as Record<string, number>,
      tiedWith: tied,
    }
  }, [ranking.data, compareIds])

  const orderLabel = order
    .map((id) => `${siteById(id).code}${tiedWith[id]?.length ? ' (tied)' : ''}`)
    .join(' → ')
  const tieSentence = (ranking.data?.ties ?? [])
    .map((g) => `${g.map((id) => siteById(id).code).join(' and ')} are tied — the data cannot tell them apart`)
    .join('. ')

  if (!ready) {
    return (
      <div className="flex grow flex-col gap-6 p-4 lg:p-6">
        <DateSlider />
        <div className="max-w-2xl">
          <LoadingPanel />
        </div>
      </div>
    )
  }

  const best = order[0]
  const disqualified = order.filter((id) => metrics[id].sun.longestDownH > SURVIVAL_LIMIT_H)

  return (
    <div className="flex grow flex-col">
      <div className="flex flex-wrap items-end gap-x-8 gap-y-4 border-b border-line px-4 py-4 lg:px-6">
        <DateSlider />
        <div className="flex flex-col gap-2">
          <SectionLabel>Rank by</SectionLabel>
          <Segmented options={RANKS} value={rankBy} onChange={setRankBy} label="Rank by" />
        </div>
      </div>

      <p aria-live="polite" className="sr-only">
        Now ranked by {TERM[rankBy][face]}: {orderLabel}.{tieSentence ? ` ${tieSentence}.` : ''}
      </p>

      <div className="grow p-4 lg:p-6">
        {wide ? (
          <div ref={ref} className="relative" style={{ height: colH }}>
            {compareIds.map((id) => {
              const position = order.indexOf(id)
              return (
                <div
                  key={id}
                  ref={(el) => {
                    if (el) setColH((h) => Math.max(h, el.offsetHeight))
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
                    rank={ranks[id] ?? position + 1}
                    tied={Boolean(tiedWith[id]?.length)}
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
            {order.map((id, position) => (
              <CompareCard
                key={id}
                siteId={id}
                rank={ranks[id] ?? position + 1}
                tied={Boolean(tiedWith[id]?.length)}
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
          Ranked by {TERM[rankBy][face].toLowerCase()},{' '}
          {tiedWith[best]?.length ? (
            <>
              <strong>{[best, ...tiedWith[best]].map((id) => siteById(id).code).join(' and ')}</strong> share
              the lead — the data cannot separate them.{' '}
            </>
          ) : (
            <>
              <strong>{siteById(best).code}</strong> leads.{' '}
            </>
          )}
          {disqualified.length > 0 ? (
            <>
              {disqualified.map((id) => siteById(id).code).join(' and ')}{' '}
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
    </div>
  )
}

function CompareCard({
  siteId,
  rank,
  tied,
  metrics,
  cursorH,
  rankBy,
}: {
  siteId: string
  /** Competition rank from the server: tied sites share it (1, 1, 3). */
  rank: number
  tied: boolean
  metrics: SiteMetrics
  cursorH: number
  rankBy: MetricKey
}) {
  const site = siteById(siteId)
  const face = useMission((s) => s.face)
  const over = metrics.sun.longestDownH > SURVIVAL_LIMIT_H
  const leading = rank === 1
  const openFor: Record<MetricKey, boolean> = {
    sunHours: false,
    earthHours: false,
    longestDark: Boolean(metrics.sun.longestDownOpen),
    longestBlackout: Boolean(metrics.earth.longestDownOpen),
  }

  return (
    <Panel
      className={`flex flex-col ${over ? 'border-alert' : leading ? 'border-earth' : ''}`}
      as="section"
    >
      <div className="flex items-start gap-3 border-b border-line p-4">
        <span
          className={`inline-flex size-7 shrink-0 items-center justify-center text-[14px] font-bold ${
            leading ? 'bg-earth-fill text-on-earth' : 'bg-line-strong text-ink'
          }`}
        >
          {rank}
        </span>
        <div className="flex min-w-0 flex-col gap-0.5">
          <div className="text-[17px] font-semibold">
            {site.code} — {site.name}
          </div>
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
          label={`${TERM[rankBy][face]}${leading ? (tied ? ' · joint best' : ' · best') : ''}`}
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
        <Mini label="Sun h" value={metrics.sun.upHours} tone="text-sun" />
        <Mini label="DTE h" value={metrics.earth.upHours} tone="text-earth" />
        <Mini
          label="Dark gap"
          value={metrics.sun.longestDownH}
          open={metrics.sun.longestDownOpen}
          tone={over ? 'text-alert' : 'text-ink'}
        />
        <Mini label="RF gap" value={metrics.earth.longestDownH} open={metrics.earth.longestDownOpen} tone="text-ink" />
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
