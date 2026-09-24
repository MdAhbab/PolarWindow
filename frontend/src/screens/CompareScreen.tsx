import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { useSiteMetricsMap } from '../lib/useMetricsMap'
import { useCompare, useWindowParams } from '../lib/mission'
import { useMission } from '../lib/store'
import { getSites, hasSite, siteById } from '../lib/sites'
import { useMissions } from '../lib/api/queries'
import type { CompareItemDTO } from '../lib/api/client'
import { rankLabel, type RankLabel } from '../lib/rank'
import { DateSlider } from '../components/DateSlider'
import { Ribbon } from '../components/Ribbon'
import { LoadingPanel, ProblemPanel } from '../components/States'
import { AdvisePanel } from '../components/Agents'
import { Speaker } from '../components/SummarySpeaker'
import { buildComparisonSummary } from '../lib/summaryScript'
import { Panel, SectionLabel, Segmented } from '../components/ui'
import { Icon } from '../components/Icon'
import { useReducedMotion } from '../hooks/useMotion'
import { metricValue, SURVIVAL_LIMIT_H } from '../lib/geometry/metrics'
import { bound, hoursWithUnit, termLabel } from '../lib/format'
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
  { value: 'sunHours', label: 'Time in sunlight' },
  { value: 'earthHours', label: 'Time in contact with Earth' },
  { value: 'longestDark', label: 'Longest night' },
  { value: 'longestBlackout', label: 'Longest time without contact' },
]

/** The window cut this site's value for `key` short: it is a lower bound. Totals never are. */
function isOpen(m: SiteMetrics, key: MetricKey): boolean {
  if (key === 'longestDark') return Boolean(m.sun.longestDownOpen)
  if (key === 'longestBlackout') return Boolean(m.earth.longestDownOpen)
  return false
}

const RANK_PARAM: Record<MetricKey, string> = {
  sunHours: 'sunlight',
  earthHours: 'earth',
  longestDark: 'night',
  longestBlackout: 'blackout',
}

/**
 * The comparison lives in the URL too (`?sites=a,b,c&rank=night`), so it can
 * be shared and the back button restores it. The URL wins when the screen
 * opens with one; after that the URL follows the store.
 */
function useCompareUrl(
  params: URLSearchParams,
  setParams: ReturnType<typeof useSearchParams>[1],
  compareIds: string[],
  rankBy: MetricKey,
  setRankBy: (k: MetricKey) => void,
) {
  // Read once, on arrival; the store and this flag update in one render, so
  // the write-back below never sees the pre-URL selection.
  const [read, setRead] = useState(false)
  useEffect(() => {
    if (read) return
    const ids = (params.get('sites') ?? '').split(',').filter(hasSite)
    if (ids.length >= 2) useMission.setState({ compareIds: [...new Set(ids)].slice(0, 8) })
    const rank = (Object.keys(RANK_PARAM) as MetricKey[]).find((k) => RANK_PARAM[k] === params.get('rank'))
    if (rank) setRankBy(rank)
    setRead(true)
  }, [read, params, setRankBy])
  useEffect(() => {
    if (!read) return
    const sites = compareIds.join(',')
    const rank = RANK_PARAM[rankBy]
    if (params.get('sites') === sites && params.get('rank') === rank) return
    const next = new URLSearchParams(params)
    next.set('sites', sites)
    next.set('rank', rank)
    setParams(next, { replace: true })
  }, [read, compareIds, rankBy, params, setParams])
}

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
  const { compareIds, rankBy, setRankBy, cursorH } = useMission(
    useShallow((s) => ({
      compareIds: s.compareIds,
      rankBy: s.rankBy,
      setRankBy: s.setRankBy,
      cursorH: s.cursorH,
    })),
  )
  const { map: metrics, done, total, error } = useSiteMetricsMap(compareIds)
  const w = useWindowParams()
  const ranking = useCompare(compareIds, w, API_METRIC[rankBy])
  const [params, setParams] = useSearchParams()
  const fromId = params.get('from')
  useCompareUrl(params, setParams, compareIds, rankBy, setRankBy)
  const fromMission = useMissions({}).data?.items.find((m) => m.id === fromId)
  const seeded = fromMission?.siteId && compareIds[0] === fromMission.siteId ? fromMission : undefined
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
    .map((g) => `${g.map((id) => siteById(id).code).join(' and ')} are tied: the data cannot tell them apart`)
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

  // Only once the server's ranking is in: the words a site may be called
  // come from it, never from the client's own order.
  const spoken = ranking.data
    ? buildComparisonSummary({
        rankedBy: termLabel(rankBy).label,
        windowStartIso: w.start,
        windowHours: metrics[order[0]].windowHours,
        survivalLimitH: SURVIVAL_LIMIT_H,
        sites: order.flatMap((id) => {
          const label = labels[id]
          return label
            ? [
                {
                  name: siteById(id).name,
                  label,
                  valueH: metricValue(metrics[id], rankBy),
                  open: isOpen(metrics[id], rankBy),
                  overLimit: metrics[id].sun.longestDownH > SURVIVAL_LIMIT_H,
                },
              ]
            : []
        }),
      })
    : null

  const best = order[0]
  const bestLabel = labels[best]
  const leads = bestLabel?.kind === 'best' || (bestLabel?.kind === 'joint' && items[best]?.rank === 1)
  const disqualified = order.filter((id) => metrics[id].sun.longestDownH > SURVIVAL_LIMIT_H)
  const unavailable = ranking.data?.unavailable ?? []

  return (
    <div className="flex grow flex-col">
      <h1 className="sr-only">Compare sites</h1>
      <div className="flex flex-wrap items-end gap-x-8 gap-y-4 border-b border-line px-4 py-4 lg:px-6">
        <DateSlider />
        <div data-guide="rank-by" className="flex min-w-0 max-w-full flex-col gap-2">
          <label htmlFor="pw-rank" className="text-caption font-semibold tracking-caps text-ink-3 uppercase xl:hidden">
            Rank by
          </label>
          <select
            id="pw-rank"
            value={rankBy}
            onChange={(e) => setRankBy(e.target.value as MetricKey)}
            className="h-12 rounded-control border border-line-strong bg-canvas px-3 text-control text-ink xl:hidden"
          >
            {RANKS.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
          <div className="hidden flex-col gap-2 xl:flex">
            <SectionLabel as="div">Rank by</SectionLabel>
            <Segmented options={RANKS} value={rankBy} onChange={setRankBy} label="Rank by" />
          </div>
        </div>
        <AddSite compareIds={compareIds} />
        <Speaker summary={spoken} what="this comparison" resetKey={`${compareIds.join('|')}|${rankBy}|${w.start}`} />
      </div>

      <p aria-live="polite" className="sr-only">
        Now ranked by {termLabel(rankBy).label}: {orderLabel}.{tieSentence ? ` ${tieSentence}.` : ''}
      </p>

      {(seeded || unavailable.length > 0 || ranking.error) && (
        <div className="flex flex-col gap-1 border-b border-line px-4 py-3 text-small leading-5 text-ink-2 lg:px-6">
          {seeded && (
            <p>
              Started from {seeded.name}: its landing spot and the three candidate sites nearest to it by distance.
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

      <footer className="border-t border-line bg-panel px-4 py-4 lg:px-6">
        <p className="max-w-4xl text-control leading-6 text-ink">
          {!leads ? (
            <>No clear leader on {termLabel(rankBy).label.toLowerCase()}{bestLabel ? '' : ' yet'}.</>
          ) : tiedWith[best]?.length ? (
            <>
              <strong>{[best, ...tiedWith[best]].map((id) => siteById(id).name).join(' and ')}</strong> share the lead on{' '}
              {termLabel(rankBy).label.toLowerCase()}.
            </>
          ) : (
            <>
              <strong>{siteById(best).name}</strong> leads on {termLabel(rankBy).label.toLowerCase()}.
            </>
          )}{' '}
          {disqualified.length > 0 ? (
            <>
              <span className="text-alert">
                {disqualified.map((id) => siteById(id).name).join(', ').replace(/, ([^,]*)$/, ' and $1')}{' '}
                {disqualified.length > 1 ? 'run' : 'runs'} past the {SURVIVAL_LIMIT_H} h battery limit
              </span>{' '}
              on these dates; other months can change that.
            </>
          ) : (
            'Every site here stays inside the battery limit, so the choice comes down to what the payload needs.'
          )}
        </p>
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
  const over = metrics.sun.longestDownH > SURVIVAL_LIMIT_H
  const rank = item?.rank ?? null
  const leading = label?.kind === 'best' || (label?.kind === 'joint' && rank === 1)
  const [why, setWhy] = useState(false)
  const whyId = useId()
  const margin = SURVIVAL_LIMIT_H - metrics.sun.longestDownH
  const cells = [
    ['sunHours', 'Sunlight', metrics.sun.upHours, false, 'text-sun'],
    ['earthHours', 'Contact with Earth', metrics.earth.upHours, false, 'text-earth'],
    ['longestDark', 'Longest night', metrics.sun.longestDownH, Boolean(metrics.sun.longestDownOpen), over ? 'text-alert' : 'text-ink'],
    ['longestBlackout', 'Without contact', metrics.earth.longestDownH, Boolean(metrics.earth.longestDownOpen), 'text-ink'],
  ] as const

  return (
    <Panel className={`flex flex-col ${over ? 'border-alert!' : leading ? 'border-ink!' : ''}`} as="section">
      <div className="flex items-start gap-3 border-b border-line p-4">
        <span
          className={`inline-flex size-7 shrink-0 items-center justify-center text-body font-bold ${
            rank === null
              ? 'border border-dashed border-uncertain text-uncertain'
              : leading
                ? 'bg-ink text-canvas'
                : 'bg-line-strong text-ink'
          }`}
          aria-label={rank === null ? 'No place stated' : `Rank ${rank}`}
        >
          {rank ?? '–'}
        </span>
        <div className="flex min-w-0 flex-col gap-0.5">
          <h2 className="text-title font-semibold">
            <span className="mr-1.5 font-mono text-body text-ink-3">{site.code}</span>
            {site.name}
          </h2>
          {label &&
            (label.kind === 'unranked' ? (
              <>
                <button
                  type="button"
                  aria-expanded={why}
                  aria-controls={whyId}
                  onClick={() => setWhy((v) => !v)}
                  className="flex min-h-8 items-center gap-1 self-start text-small font-semibold text-uncertain hover:text-ink"
                >
                  Too close to call
                  <Icon name="info" size={14} strokeWidth={2} />
                </button>
                <p id={whyId} hidden={!why} className="text-caption leading-caption text-ink-2">
                  {label.why ? `Because ${label.why}` : 'No place can be stated'}
                  {label.title ? `; it ${label.title}.` : '.'}
                </p>
              </>
            ) : (
              <div className="text-small font-semibold text-ink">
                {label.kind === 'joint' ? `${label.text}: the data can’t separate them` : label.text}
              </div>
            ))}
        </div>
        <div className="ml-auto shrink-0">
          <RemoveSite siteId={siteId} name={site.name} />
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-2 p-4">
        {cells.map(([key, name, value, open, tone]) => (
          <div
            key={key}
            className={`flex flex-col gap-0.5 px-3 py-2 ${key === rankBy ? 'bg-inset shadow-[inset_0_-2px_0_var(--color-ink-3)]' : ''}`}
          >
            <dt className="text-caption text-ink-3">
              {name}
              {key === rankBy && <span className="sr-only"> (ranked by this)</span>}
            </dt>
            <dd className={`text-figure-sm leading-7 font-semibold tnum ${tone}`}>
              {bound(open)}
              {Math.round(value)}
              <span className="ml-1 text-body font-normal text-ink-3">h</span>
            </dd>
          </div>
        ))}
      </dl>

      <div className="flex flex-col gap-3 px-4 pb-4">
        <div className="flex flex-col gap-1.5">
          <span className="text-caption font-semibold text-sun">Sunlight over these dates</span>
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
          <span className="text-caption font-semibold text-earth">Contact with Earth over these dates</span>
          <Ribbon
            arcs={metrics.earth.arcs}
            windowStartH={metrics.windowStartH}
            windowHours={metrics.windowHours}
            tone="earth"
            cursorH={cursorH}
          />
        </div>
      </div>

      <div className="mt-auto flex flex-col gap-1 border-t border-line p-4">
        <p className={`text-small font-semibold ${over ? 'text-alert' : 'text-ink'}`}>
          {over
            ? `${metrics.sun.longestDownOpen ? 'At least ' : ''}${Math.round(-margin)} h past the ${SURVIVAL_LIMIT_H} h battery limit`
            : metrics.sun.longestDownOpen
              ? `At most ${hoursWithUnit(margin)} inside the battery limit: these dates cut the night short`
              : `${hoursWithUnit(margin)} inside the ${SURVIVAL_LIMIT_H} h battery limit`}
        </p>
        <p className="text-small leading-5 text-ink-2">{site.note}</p>
      </div>
    </Panel>
  )
}

/** Add a site to the comparison, up to eight, without going back to the map. */
function AddSite({ compareIds }: { compareIds: string[] }) {
  const id = useId()
  const toggle = useMission((s) => s.toggleCompare)
  const rest = getSites().filter((s) => !compareIds.includes(s.id))
  const full = compareIds.length >= 8
  return (
    <div className="flex w-full min-w-0 flex-col gap-2 sm:w-auto">
      <label htmlFor={id} className="text-small font-medium text-ink-3">
        {full ? 'Eight sites is the most' : 'Add a site'}
      </label>
      <select
        id={id}
        value=""
        disabled={full || rest.length === 0}
        onChange={(e) => e.target.value && toggle(e.target.value)}
        className="h-12 w-full max-w-full rounded-control border border-line-strong bg-canvas px-3 text-control text-ink hover:border-ink-3 disabled:text-ink-3"
      >
        <option value="">Choose a site…</option>
        {rest.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
      </select>
    </div>
  )
}

/** Take a site out; a comparison keeps at least two. */
function RemoveSite({ siteId, name }: { siteId: string; name: string }) {
  const count = useMission((s) => s.compareIds.length)
  const toggle = useMission((s) => s.toggleCompare)
  if (count <= 2) return null
  return (
    <button
      type="button"
      onClick={() => toggle(siteId)}
      aria-label={`Remove ${name} from the comparison`}
      title="Remove from the comparison"
      className="-mt-2 -mr-2 inline-flex size-12 items-center justify-center rounded-control text-ink-3 hover:bg-inset hover:text-ink"
    >
      <Icon name="close" size={16} />
    </button>
  )
}
