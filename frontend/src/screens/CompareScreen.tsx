import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useSiteMetricsMap } from '../lib/useMetricsMap'
import { useMission } from '../lib/store'
import { siteById } from '../lib/sites'
import { DateSlider } from '../components/DateSlider'
import { Ribbon } from '../components/Ribbon'
import { KeyNumberTile } from '../components/KeyNumbers'
import { LoadingPanel } from '../components/States'
import { Panel, SectionLabel, Segmented } from '../components/ui'
import { Icon } from '../components/Icon'
import { useReducedMotion } from '../hooks/useMotion'
import { metricValue, rankSites, SURVIVAL_LIMIT_H } from '../lib/geometry/metrics'
import { TERM, coords, hoursWithUnit } from '../lib/format'
import type { MetricKey, SiteMetrics } from '../lib/types'

const GAP = 24
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
  const { compareIds, rankBy, setRankBy, face, cursorH } = useMission()
  const { map: metrics, done, total, isPending } = useSiteMetricsMap(compareIds)
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

  const order = ready
    ? rankSites(
        compareIds.map((id) => ({ siteId: id, metrics: metrics[id] })),
        rankBy,
      )
    : compareIds

  const orderLabel = order.map((id) => siteById(id).code).join(' → ')

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
        Now ranked by {TERM[rankBy][face]}: {orderLabel}
      </p>

      <div className="grow p-4 lg:p-6">
        {wide ? (
          <div ref={ref} className="relative" style={{ height: colH }}>
            {compareIds.map((id) => {
              const rank = order.indexOf(id)
              return (
                <div
                  key={id}
                  ref={(el) => {
                    if (el) setColH((h) => Math.max(h, el.offsetHeight))
                  }}
                  className="absolute top-0 left-0"
                  style={{
                    width: colW,
                    transform: `translateX(${rank * (colW + GAP)}px)`,
                    transition: reduced ? 'none' : 'transform 460ms cubic-bezier(.2,.8,.2,1)',
                  }}
                >
                  <CompareCard siteId={id} rank={rank} metrics={metrics[id]} cursorH={cursorH} rankBy={rankBy} />
                </div>
              )
            })}
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {order.map((id, rank) => (
              <CompareCard key={id} siteId={id} rank={rank} metrics={metrics[id]} cursorH={cursorH} rankBy={rankBy} />
            ))}
          </div>
        )}
      </div>

      <footer className="flex flex-wrap items-center gap-x-8 gap-y-3 border-t border-line bg-panel px-4 py-5 lg:px-6">
        <SectionLabel className="shrink-0">The trade-off, stated</SectionLabel>
        <p className="max-w-4xl text-[15px] leading-6 text-ink">
          Ranked by {TERM[rankBy][face].toLowerCase()}, <strong>{siteById(best).code}</strong> leads.{' '}
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
  metrics,
  cursorH,
  rankBy,
}: {
  siteId: string
  rank: number
  metrics: SiteMetrics
  cursorH: number
  rankBy: MetricKey
}) {
  const site = siteById(siteId)
  const face = useMission((s) => s.face)
  const over = metrics.sun.longestDownH > SURVIVAL_LIMIT_H
  const leading = rank === 0

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
          {rank + 1}
        </span>
        <div className="flex min-w-0 flex-col gap-0.5">
          <div className="text-[17px] font-semibold">
            {site.code} — {site.name}
          </div>
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
          label={`${TERM[rankBy][face]}${leading ? ' · best' : ''}`}
          value={metricValue(metrics, rankBy)}
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
        <Mini label="Dark gap" value={metrics.sun.longestDownH} tone={over ? 'text-alert' : 'text-ink'} />
        <Mini label="RF gap" value={metrics.earth.longestDownH} tone="text-ink" />
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
            ? `${Math.round(metrics.sun.longestDownH - SURVIVAL_LIMIT_H)} h over the limit in a single block. ${site.note}`
            : `${hoursWithUnit(SURVIVAL_LIMIT_H - metrics.sun.longestDownH)} of margin on the night. ${site.note}`}
        </p>
      </div>
    </Panel>
  )
}

function Mini({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] font-semibold tracking-[0.08em] text-ink-3 uppercase">{label}</span>
      <span className={`text-[22px] leading-6 font-semibold tnum ${tone}`}>≈{Math.round(value)}</span>
    </div>
  )
}
