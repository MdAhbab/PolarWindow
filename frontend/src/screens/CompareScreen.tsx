import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { useSiteMetricsMap } from '../lib/useMetricsMap'
import { useCompare, useWindowParams } from '../lib/mission'
import { useMission } from '../lib/store'
import { getSites, hasSite, siteById } from '../lib/sites'
import { useMissions } from '../lib/api/queries'
import type { CompareItemDTO } from '../lib/api/client'
import { firstEnd, ordinal, rankLabel, type RankLabel } from '../lib/rank'
import { useBatteryLimit } from '../lib/api/lifecycleQueries'
import { AgainstLimitWords, EnterLimit, LimitPhrase, LimitTally } from '../components/KeyNumbers'
import { DateSlider } from '../components/DateSlider'
import { Ribbon } from '../components/Ribbon'
import { LoadingPanel, ProblemPanel } from '../components/States'
import { AdvisePanel } from '../components/Agents'
import { Speaker } from '../components/SummarySpeaker'
import { buildComparisonSummary } from '../lib/summaryScript'
import { Eyebrow, Panel, Segmented, useOpenRow } from '../components/ui'
import { PageHeader } from '../components/Page'
import { Icon } from '../components/Icon'
import { Select } from '../components/Select'
import { useReducedMotion } from '../hooks/useMotion'
import {
  longestNight,
  metricValue,
  nightAgainstLimit,
  type AgainstLimit,
  type BatteryLimit,
  type Night,
} from '../lib/geometry/metrics'
import { bound, plusMinus, termLabel } from '../lib/format'
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

  // R2: the team's entered battery limit, or 120 h said to be assumed. The
  // cards wait for it, so none says "assumed" a moment before it knows.
  const limit = useBatteryLimit()
  const ready = compareIds.every((id) => metrics[id]) && !limit.pending

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

  // U11: what each site's place may be called, from the server's rank, range
  // and flags: "1st", "joint 2nd", or "too close to call" with why. A place
  // in the order by one number, never a verdict on the site (R5).
  const code = (id: string) => (hasSite(id) ? siteById(id).code : id)
  const labels: Record<string, RankLabel | undefined> = {}
  for (const id of compareIds) {
    const it = items[id]
    labels[id] = it
      ? rankLabel({
          rank: it.rank,
          rankRange: it.rank_range,
          tied: it.tied,
          censored: it.censored,
          grazing: it.grazing,
          incomparableWith: it.incomparable_with.map(code),
          places: ranking.data?.items.length,
          metric: rankBy,
        })
      : undefined
  }
  const metricName = termLabel(rankBy).label.toLowerCase()
  const orderOf = `order of ${metricName}, ${firstEnd(rankBy)}`
  // Each site's longest night against the limit, with the night's margin (R2).
  const nights: Record<string, Night> = {}
  const against: Record<string, AgainstLimit> = {}
  for (const id of compareIds) {
    if (!metrics[id]) continue
    nights[id] = longestNight(metrics[id], hasSite(id) ? siteById(id).terrainModelled : true)
    against[id] = nightAgainstLimit(nights[id], limit.h)
  }

  const orderLabel = order
    .map((id) => `${code(id)}${labels[id] ? ` (${labels[id]!.text})` : ''}`)
    .join(' → ')
  const tieSentence = (ranking.data?.ties ?? [])
    .map((g) => `${g.map((id) => siteById(id).code).join(' and ')} are tied: the data cannot tell them apart`)
    .join('. ')

  if (!ready) {
    return (
      <div className="pw-page flex grow flex-col gap-6 pt-6 pb-8 lg:pt-8">
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
        firstEnd: firstEnd(rankBy),
        windowStartIso: w.start,
        windowHours: metrics[order[0]].windowHours,
        batteryLimit: limit,
        sites: order.flatMap((id) => {
          const label = labels[id]
          return label
            ? [
                {
                  name: siteById(id).name,
                  label,
                  valueH: metricValue(metrics[id], rankBy),
                  open: isOpen(metrics[id], rankBy),
                  against: against[id].kind,
                },
              ]
            : []
        }),
      })
    : null

  const first = order[0]
  const firstLabel = labels[first]
  const sharing = firstLabel?.kind === 'joint' && items[first]?.rank === 1 ? [first, ...(tiedWith[first] ?? [])] : []
  const unavailable = ranking.data?.unavailable ?? []

  return (
    <div className="pw-page flex grow flex-col gap-6 pt-6 pb-8 lg:gap-8 lg:pt-8">
      <PageHeader
        compact
        title="Compare sites"
        lede="The same dates at each site, side by side, put in order by one number at a time. Nothing is added up into one figure."
      />
      <DateSlider />
      <div className="flex flex-wrap items-end gap-x-6 gap-y-4">
        <div data-guide="rank-by" className="flex min-w-0 max-w-full flex-col gap-2">
          <label htmlFor="pw-rank" className="pw-eyebrow xl:hidden">
            Rank by
          </label>
          <Select
            id="pw-rank"
            look="pill"
            value={rankBy}
            onChange={setRankBy}
            options={RANKS}
            className="xl:hidden"
          />
          <div className="hidden flex-col gap-2 xl:flex">
            <Eyebrow as="div">Rank by</Eyebrow>
            <Segmented options={RANKS} value={rankBy} onChange={setRankBy} label="Rank by" />
          </div>
        </div>
        <AddSite compareIds={compareIds} />
        <Speaker summary={spoken} what="this comparison" resetKey={`${compareIds.join('|')}|${rankBy}|${w.start}`} />
      </div>

      <p aria-live="polite" className="sr-only">
        Now in {orderOf}: {orderLabel}.{tieSentence ? ` ${tieSentence}.` : ''}
      </p>

      {(seeded || unavailable.length > 0 || ranking.error) && (
        <div className="-mt-2 flex flex-col gap-1 text-small leading-5 text-ink-2">
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
              The order did not load ({(ranking.error as { title?: string }).title ?? 'request failed'}), so the
              columns are in the order you chose them, with no places given.
            </p>
          ) : null}
        </div>
      )}

      <div className="grow">
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
                    // M3: a column crossing the table moves as far as a sheet does, on the move curve.
                    transition: reduced ? 'none' : 'transform var(--pw-dur-sheet) var(--ease-move)',
                  }}
                >
                  <CompareCard
                    siteId={id}
                    item={items[id]}
                    label={labels[id]}
                    metrics={metrics[id]}
                    cursorH={cursorH}
                    rankBy={rankBy}
                    night={nights[id]}
                    against={against[id]}
                    limit={limit}
                    rankedBy={ranking.data?.rank_by}
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
                night={nights[id]}
                against={against[id]}
                limit={limit}
                rankedBy={ranking.data?.rank_by}
              />
            ))}
          </div>
        )}
      </div>

      {/* The order, by which number and which end is 1st, then the nights
          against the battery limit, counted. No verdict (R5, R6); site names
          in the body colour, never the alert one (V129). */}
      <footer className="pw-card pw-card-quiet px-5 py-4 sm:px-6">
        <p className="max-w-4xl text-lede leading-7 text-ink">
          {ranking.error ? (
            <>No order by {metricName}: it did not load.</>
          ) : !firstLabel ? (
            <>The order by {metricName} has not arrived yet.</>
          ) : sharing.length > 1 ? (
            <>
              In {orderOf}, <strong>{sharing.map((id) => siteById(id).name).join(' and ')}</strong> are joint 1st: the
              data cannot separate them.
            </>
          ) : firstLabel.kind === 'first' ? (
            <>
              In {orderOf}, <strong>{siteById(first).name}</strong> is 1st.
            </>
          ) : (
            <>In {orderOf}, 1st place is too close to call.</>
          )}{' '}
          <LimitTally
            sites={order.map((id) => ({ name: siteById(id).name, night: nights[id], against: against[id] }))}
            limit={limit}
          />{' '}
          {order.some((id) => against[id].kind !== 'inside' && against[id].kind !== 'no-night') && 'Other months can change that. '}
          <EnterLimit limit={limit} />
        </p>
      </footer>

      <AdvisePanel start={w.start} end={w.end} />
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
  night,
  against,
  limit,
  rankedBy,
}: {
  /** The number the server's order on screen is by (`rank_by`), as the API spells it. */
  rankedBy: string | undefined
  siteId: string
  /** The server's ranking of this site; undefined until it arrives. */
  item: CompareItemDTO | undefined
  /** What the site's place may be called (U11); undefined until the ranking arrives. */
  label: RankLabel | undefined
  metrics: SiteMetrics
  cursorH: number
  rankBy: MetricKey
  /** Its longest night, with the margin the comparison uses. */
  night: Night
  /** Where that night stands against the battery limit (R2). */
  against: AgainstLimit
  limit: BatteryLimit
}) {
  const site = siteById(siteId)
  // Magenta means past the limit by more than the night's margin, nothing else.
  const over = against.kind === 'past'
  const rank = item?.rank ?? null
  const metricName = termLabel(rankBy).label.toLowerCase()
  const [why, setWhy] = useState(false)
  const whyRow = useOpenRow(why)
  const whyId = useId()
  // The ranked figure's own margin, as the server ordered it (none when an
  // edge cannot be timed), and only from the order for this number: while a
  // new order loads the previous one is still on screen.
  const heroMarginH =
    item?.uncertainty_s != null && item.uncertainty_s > 0 && rankedBy === API_METRIC[rankBy] ? item.uncertainty_s / 3600 : undefined
  const cells = [
    ['sunHours', 'Time in sunlight', metrics.sun.upHours, false, 'text-sun', 'Time in sunlight'],
    ['earthHours', 'Time in contact with Earth', metrics.earth.upHours, false, 'text-earth', 'Time in contact with Earth'],
    ['longestDark', 'Longest night', metrics.sun.longestDownH, Boolean(metrics.sun.longestDownOpen), over ? 'text-alert' : 'text-ink', 'Longest night'],
    ['longestBlackout', 'Longest time without contact', metrics.earth.longestDownH, Boolean(metrics.earth.longestDownOpen), 'text-ink', 'Longest without contact'],
  ] as const
  const hero = cells.find(([key]) => key === rankBy)!
  const rest = cells.filter(([key]) => key !== rankBy)

  return (
    <Panel as="section" alert={over} className="flex flex-col">
      <div className="flex items-start gap-3 p-4 pb-3 sm:px-5">
        <span
          className={`inline-flex size-8 shrink-0 items-center justify-center rounded-pill font-mono text-body font-semibold ${
            rank === null
              ? 'border border-dashed border-uncertain text-uncertain'
              : rank === 1
                ? 'bg-ink text-canvas'
                : 'bg-inset text-ink shadow-[inset_0_0_0_1px_var(--color-line-strong)]'
          }`}
          role="img"
          aria-label={rank === null ? 'No place stated' : `${ordinal(rank)} by ${metricName}`}
        >
          {/* No place: the dashed ring alone, no dash standing in for a number. */}
          {rank ?? ''}
        </span>
        <div className="flex min-w-0 flex-col gap-0.5">
          <h2 className="text-title leading-6 font-semibold">
            <span className="mr-1.5 font-mono text-body font-normal text-ink-3">{site.code}</span>
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
                {/* Opens by its height and closes the same way (rule 3). */}
                <div ref={whyRow.ref} hidden={whyRow.hidden} className="pw-open-row">
                  <p id={whyId} hidden={whyRow.hidden} className="text-caption leading-caption text-ink-2">
                    {label.why ? `Because ${label.why}` : 'No place can be stated'}
                    {label.title ? `; it ${label.title}.` : '.'}
                  </p>
                </div>
              </>
            ) : (
              <div className="text-small font-semibold text-ink-2">
                {label.text} by {metricName}
                {label.kind === 'joint' ? ': the data can’t separate them' : ''}
              </div>
            ))}
        </div>
        <div className="ml-auto shrink-0">
          <RemoveSite siteId={siteId} name={site.name} />
        </div>
      </div>

      <div className="flex flex-col gap-4 px-4 pb-4 sm:px-5">
        {/* The measure the sites are ranked by is the card's hero; the other three step back. */}
        <dl className="flex flex-col gap-1">
          <dt className="flex items-center gap-1.5 text-small font-medium text-ink-2">
            {hero[0] === 'longestDark' && over && <Icon name="alert" size={14} strokeWidth={2.2} className="text-alert" />}
            {hero[1]}
            <span className="sr-only"> (ranked by this)</span>
          </dt>
          <dd className={`pw-figure text-[44px] leading-[46px] xl:text-[52px] xl:leading-[54px] ${hero[4]}`}>
            {bound(hero[3])}
            {Math.round(hero[2])}
            {heroMarginH !== undefined && (
              <span className="ml-1.5 text-title font-normal tracking-normal text-uncertain tnum [font-stretch:100%] sm:text-subhead">
                {plusMinus(heroMarginH)}
              </span>
            )}
            <span className="ml-1.5 text-large font-normal tracking-normal text-ink-2 [font-stretch:100%]">h</span>
          </dd>
        </dl>
        {/* A subgrid, so a label that wraps does not push its figure below the others. */}
        <dl className="grid grid-cols-3 gap-x-3 gap-y-1 border-t border-line pt-3">
          {rest.map(([key, name, value, open, tone, short]) => (
            <div key={key} className="row-span-2 grid min-w-0 grid-rows-subgrid">
              <dt className="text-caption leading-4 text-ink-3" title={name}>
                {short}
              </dt>
              <dd className={`pw-figure text-figure-sm leading-7 ${tone}`}>
                {bound(open)}
                {Math.round(value)}
                <span className="ml-1 text-small font-normal tracking-normal text-ink-3 [font-stretch:100%]">h</span>
              </dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="flex flex-col gap-3 px-4 pb-4 sm:px-5">
        <div className="flex flex-col gap-1.5">
          <span className="text-caption font-semibold text-sun">Sunlight over these dates</span>
          <Ribbon
            arcs={metrics.sun.arcs}
            windowStartIso={metrics.windowStartIso}
            windowHours={metrics.windowHours}
            tone="sun"
            cursorH={cursorH}
            alertOverH={limit.h}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <span className="text-caption font-semibold text-earth">Contact with Earth over these dates</span>
          <Ribbon
            arcs={metrics.earth.arcs}
            windowStartIso={metrics.windowStartIso}
            windowHours={metrics.windowHours}
            tone="earth"
            cursorH={cursorH}
          />
        </div>
      </div>

      <div className="mt-auto flex flex-col gap-1 border-t border-line p-4 sm:px-5">
        {/* The longest night against the battery limit, with its margin (R2):
            magenta only past it by more than the margin. */}
        <p className={`flex items-start gap-1.5 text-small font-semibold ${over ? 'text-alert' : 'text-ink'}`}>
          {over ? (
            <Icon name="alert" size={14} strokeWidth={2.2} className="mt-0.5 shrink-0" />
          ) : against.kind === 'within-margin' ? (
            <Icon name="uncertain" size={14} strokeWidth={2.2} className="mt-0.5 shrink-0 text-uncertain" />
          ) : null}
          <span>
            {against.kind === 'no-night' ? (
              'The Sun did not set on these dates'
            ) : against.kind === 'cut-short' ? (
              <>
                These dates cut the night short at {bound(night.open)}
                {Math.round(night.h)} h; it may run past <LimitPhrase limit={limit} />
              </>
            ) : (
              <AgainstLimitWords a={against} limit={limit} capital />
            )}
          </span>
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
      <label htmlFor={id} className="pw-eyebrow">
        {full ? 'Eight sites is the most' : 'Add a site'}
      </label>
      <Select
        id={id}
        look="pill"
        value=""
        placeholder={rest.length === 0 ? 'No more sites' : 'Choose a site…'}
        disabled={full || rest.length === 0}
        onChange={toggle}
        options={rest.map((s) => ({ value: s.id, label: s.name }))}
        className="w-full sm:min-w-56"
      />
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
      className="pw-press -mt-2 -mr-2 inline-flex size-12 items-center justify-center rounded-pill text-ink-3 hover:bg-inset hover:text-ink"
    >
      <Icon name="close" size={16} />
    </button>
  )
}
