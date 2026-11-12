import { useId, useState, type ReactNode } from 'react'
import { useMotionClass } from '../hooks/useMotion'
import { Skeleton } from './States'
import { useOpenRow } from './ui'
import { bound, hoursSpoken, percent, plusMinus, termLabel } from '../lib/format'
import {
  againstLimitLead,
  andList,
  hoursWithMargin,
  limitHours,
  limitWords,
  longestNight,
  nightAgainstLimit,
  tallyAgainstLimit,
  type AgainstLimit,
  type BatteryLimit,
  type Night,
} from '../lib/geometry/metrics'
import { useBatteryLimit } from '../lib/api/lifecycleQueries'
import { useMission } from '../lib/store'
import { useSettingsTab } from '../lib/settingsTab'
import type { Arc, SiteMetrics } from '../lib/types'
import { Icon } from './Icon'
import { KindMark, type NumberKind } from './KindMark'

export type Tone = 'sun' | 'earth' | 'neutral' | 'alert'
export type TileState = 'ready' | 'computing' | 'uncertain' | 'blank'

const TONE_TEXT: Record<Tone, string> = {
  sun: 'text-sun',
  earth: 'text-earth',
  neutral: 'text-ink',
  alert: 'text-alert',
}
const TONE_BAR: Record<Tone, string> = {
  sun: 'bg-sun-fill',
  earth: 'bg-earth-fill',
  neutral: 'bg-terrain-high',
  alert: 'bg-alert',
}

/**
 * The key-number tile. Nothing sits within 96 px of the value but its own
 * label and unit, and the bar under it repeats the number as a length so the
 * figure is never carried by colour alone.
 *
 * With `means`, the label is a button: pressing it says in one sentence what
 * the number is, and its professional name where it has one. The tile itself
 * stays short until someone asks.
 */
export function KeyNumberTile({
  label,
  value,
  unit = 'h',
  tone = 'neutral',
  state = 'ready',
  toleranceH,
  fraction,
  footnote,
  size = 'lg',
  icon,
  open = false,
  spoken,
  means,
  also,
  inRow = false,
  display,
  above,
  margin,
  range,
  bar = true,
  source,
  age,
  numberKind,
}: {
  label: string
  /**
   * Laid out by `KeyNumberRow`: the tile's label, value, bar and notes share
   * rows with its neighbours (subgrid), so a label that wraps to three lines
   * does not push its value below the others.
   */
  inRow?: boolean
  /** One sentence on what the number is, opened from the label. */
  means?: string
  /** The professional term for the same thing, shown with `means`. */
  also?: string
  value: number
  unit?: string
  tone?: Tone
  state?: TileState
  toleranceH?: number
  fraction?: number
  /** A short line under the bar: words, or words with the limit's phrase and its link (R2). */
  footnote?: ReactNode
  size?: 'lg' | 'md' | 'sm'
  icon?: Parameters<typeof Icon>[0]['name']
  /** The window cut this stretch short: show a lower bound (≥), not ≈. */
  open?: boolean
  /** What a screen reader hears for the value; defaults to a sentence from it. */
  spoken?: string
  /**
   * The figure, already written ("12–31", "00:16 UTC", "4.1 × 10⁹"). Drawn as
   * it is, without the roll (M4), which only runs between two plain numbers.
   */
  display?: string
  /** A short line above the figure: a launch time's date. */
  above?: string
  /** The margin, already written ("±2", "×/÷2", "±4 min"); replaces `toleranceH`. */
  margin?: string
  /** A range, as fractions of the bar: solid to `lo`, hatched from `lo` to `hi`. */
  range?: { lo: number; hi: number }
  /** No bar, for a value that is not an amount (a time of day). */
  bar?: boolean
  /** Where the number comes from (invariant 10), opened with `means` from the label. */
  source?: ReactNode
  /** How old a live number is (invariant 11), always on screen. */
  age?: string
  /** Where the number comes from, as a small mark and one word on the tile. */
  numberKind?: NumberKind
}) {
  const shown = state === 'ready' || state === 'uncertain'
  // M4: the figure is always the real value. When it changes it settles into
  // place (a short rise from 0.55 opacity), so no wrong value is ever drawn,
  // and under reduced motion it is simply replaced.
  const settle = useMotionClass('pw-number-in')
  const [explained, setExplained] = useState(false)
  const explainRow = useOpenRow(explained)
  const explainId = useId()
  // One sentence with the value, its unit and its margin: the ± sits in a
  // separate element, so reading the visuals aloud announced "±17.1" with no unit.
  const said =
    spoken ??
    (unit === 'h'
      ? `${hoursSpoken(value, open)}${
          toleranceH === undefined
            ? ''
            : toleranceH < 0.05
              ? ', timed to within a few minutes'
              : `, plus or minus ${toleranceH.toFixed(1)} hours`
        }${state === 'uncertain' ? ', uncertain' : ''}`
      : `${bound(open) === '≥' ? 'at least' : 'about'} ${Math.round(value)} ${unit}`)

  const numberClass =
    size === 'lg'
      ? // The four stay together as a 2×2 on a phone, where a three-digit
        // value and its unit must fit half the width (WCAG 1.4.10).
        'text-[34px] leading-[36px] sm:text-figure-md sm:leading-figure-md lg:text-figure-tile lg:leading-[52px]'
      : size === 'md'
        ? 'text-[34px] leading-[36px] sm:text-figure-md sm:leading-figure-md'
        : 'text-figure leading-figure'

  const explains = Boolean(means || source)
  // A card (globals.css .pw-card). Over the limit, the core's edge is magenta
  // beside the triangle and the words; uncertain, a dashed line inside it;
  // sunlight may glow, since the glow means sunlight.
  const kind =
    tone === 'alert'
      ? 'pw-card-alert'
      : state === 'uncertain'
        ? 'outline-1 outline-dashed outline-uncertain -outline-offset-1'
        : tone === 'sun' && state === 'ready'
          ? 'pw-card-sunlit'
          : ''

  return (
    <div
      className={`pw-card pw-tile p-4 sm:p-5 ${kind} ${
        inRow ? 'row-span-5 grid grid-rows-subgrid content-start gap-y-2.5' : 'flex flex-col gap-2.5'
      }`}
    >
      {/* Sentence case, so a long label wraps as words; the row keeps the
          four values on one baseline when one label wraps. */}
      <div className={`flex items-start gap-2 text-small leading-5 font-medium ${tone === 'alert' ? 'text-alert' : 'text-ink-2'}`}>
        {tone === 'alert' ? (
          <Icon name="alert" size={14} strokeWidth={2.2} />
        ) : state === 'uncertain' ? (
          <Icon name="uncertain" size={14} strokeWidth={2.2} />
        ) : icon ? (
          <Icon name={icon} size={14} strokeWidth={2} />
        ) : null}
        {explains ? (
          <button
            type="button"
            aria-expanded={explained}
            aria-controls={explainId}
            onClick={() => setExplained((v) => !v)}
            className="-my-3 -mr-2 flex min-h-11 grow cursor-pointer items-start justify-between gap-2 py-3 pr-2 text-left hover:text-ink"
          >
            <span>{label}</span>
            <Icon name="info" size={14} strokeWidth={2} className="mt-px shrink-0 opacity-70" />
            <span className="sr-only">{explained ? ', hide what this means' : ', what this means'}</span>
          </button>
        ) : (
          <span>{label}</span>
        )}
      </div>

      {(shown || (state === 'blank' && spoken)) && <span className="sr-only">{said}</span>}
      {/* Wraps rather than overflows: at `sm` in the map's two-column rail the
          value, its margin and the unit are wider than the tile. The margin and
          the unit wrap together, so a bare "h" never lands on its own line. */}
      <div
        className="flex flex-wrap items-baseline gap-x-2"
        aria-hidden={shown || (state === 'blank' && spoken) ? 'true' : undefined}
      >
        {above && state !== 'blank' && state !== 'computing' && (
          <span className="w-full text-small font-medium text-ink-2">{above}</span>
        )}
        {state === 'blank' ? (
          <span className={`pw-figure text-line-strong ${numberClass}`}>-</span>
        ) : state === 'computing' ? (
          <span className={`inline-flex items-center ${numberClass}`}>
            <Skeleton className="h-[0.8em] w-24" />
            <span className="sr-only">Loading</span>
          </span>
        ) : display !== undefined ? (
          <span key={display} className={`pw-figure ${numberClass} ${TONE_TEXT[tone]} ${settle}`}>
            {display}
          </span>
        ) : (
          <span key={value} className={`pw-figure ${numberClass} ${TONE_TEXT[tone]} ${settle}`}>
            {bound(open)}
            {Math.round(value)}
          </span>
        )}
        <span className="flex items-baseline gap-2">
          {margin !== undefined && state !== 'blank' && state !== 'computing' ? (
            <span className="text-title text-uncertain tnum sm:text-subhead">{margin}</span>
          ) : (
            toleranceH !== undefined &&
            state !== 'blank' &&
            state !== 'computing' && <span className="text-title text-uncertain tnum sm:text-subhead">{plusMinus(toleranceH)}</span>
          )}
          {unit && <span className="text-title text-ink-2 sm:text-large">{unit}</span>}
        </span>
      </div>

      {bar ? (
        <div className="relative flex h-1 overflow-hidden bg-line">
          {state === 'ready' || state === 'uncertain' ? (
            range ? (
              <>
                <div className={TONE_BAR[tone]} style={{ width: `${clampPct(range.lo)}%` }} />
                <div
                  className="hatch-uncertain border-y border-uncertain"
                  style={{ width: `${Math.max(0, clampPct(range.hi) - clampPct(range.lo))}%` }}
                />
              </>
            ) : (
              // Scaled, not resized: it moves on the compositor and shifts nothing.
              <div
                className={`pw-bar-grow absolute inset-0 origin-left ${TONE_BAR[tone]} transition-transform duration-[var(--pw-dur-slow)] ease-[var(--ease-settle)]`}
                style={{ transform: `scaleX(${clampPct(fraction ?? 0) / 100})` }}
              />
            )
          ) : (
            <div className="w-1/3 bg-line" />
          )}
        </div>
      ) : inRow ? (
        <div />
      ) : null}

      {footnote || age || (numberKind && shown) ? (
        <div className="flex flex-col gap-0.5 text-caption text-ink-3">
          {numberKind && shown && <KindMark kind={numberKind} />}
          {footnote && <span>{footnote}</span>}
          {age && <span className="text-ink-2">{age}</span>}
        </div>
      ) : inRow ? (
        <div />
      ) : null}
      {explains && (
        // "What this means" opens by its height and closes the same way (rule 3).
        <div ref={explainRow.ref} hidden={explainRow.hidden} className="pw-open-row">
          <p id={explainId} hidden={explainRow.hidden} className="border-t border-line pt-2 text-small leading-5 text-ink-2">
            <span className="block pb-1 font-semibold text-ink">About this number</span>
            {means}
            {also && <span className="block pt-1 text-ink-3">Also called {also}.</span>}
            {source && <span className="block pt-1 text-ink-3">{source}</span>}
          </p>
        </div>
      )}
    </div>
  )
}

const clampPct = (f: number) => Math.max(0, Math.min(100, f * 100))

/**
 * The battery limit as a phrase in a sentence (R2): "the 96 h battery limit
 * your team entered", or, with none entered, "the 120 h battery limit
 * (assumed)" with the scenario hatch on the assumed words, so it is told
 * apart from a published or entered figure without colour, and in print.
 */
export function LimitPhrase({ limit }: { limit: BatteryLimit }) {
  if (limit.basis === 'entered') return <>{limitWords(limit)}</>
  return (
    <>
      the{' '}
      <span className="pw-scenario rounded-sm px-1 box-decoration-clone" title={limit.why}>
        {limitHours(limit.h)}{' '}h battery limit (assumed)
      </span>
    </>
  )
}

/**
 * "Enter yours": opens Settings on Parameters, where the team enters its
 * battery limit. Shown only beside an assumed limit; hidden in print.
 */
export function EnterLimit({ limit, className = '' }: { limit: BatteryLimit; className?: string }) {
  const setSettingsOpen = useMission((s) => s.setSettingsOpen)
  if (limit.basis === 'entered' || limit.pending) return null
  return (
    <button
      type="button"
      onClick={() => {
        useSettingsTab.getState().setTab('parameters')
        setSettingsOpen(true)
      }}
      className={`font-semibold text-ink underline underline-offset-2 hover:text-ink-2 print:hidden ${className}`}
    >
      Enter yours<span className="sr-only">: your team’s battery limit, in Settings</span>
    </button>
  )
}

/**
 * One night against the limit, in words, with the night's margin: "56 ±2.3 h
 * inside the …", "within the margin of the …", "at least 168 h past the …".
 * `capital` starts it with a capital letter, for a line of its own.
 */
export function AgainstLimitWords({ a, limit, capital = false }: { a: AgainstLimit; limit: BatteryLimit; capital?: boolean }) {
  const lead = againstLimitLead(a)
  if (lead === null) return null
  return (
    <>
      {capital ? lead.charAt(0).toUpperCase() + lead.slice(1) : lead}
      <LimitPhrase limit={limit} />
    </>
  )
}

/** One compared site, for `LimitTally`. */
export interface TallySite {
  name: string
  night: Night
  against: AgainstLimit
}

/**
 * The compared sites against the battery limit, counted and named, with no
 * verdict (R6): "2 of 3 sites have a longest night past the 120 h battery
 * limit (assumed) on these dates: A and B. The longest night at C is within
 * the margin of the limit." The limit's phrase is given once; later
 * sentences say "the limit". With `figures`, each name carries its night and
 * margin (the Report, which has no cards to read them from).
 */
export function LimitTally({ sites, limit, figures = false }: { sites: TallySite[]; limit: BatteryLimit; figures?: boolean }) {
  const t = tallyAgainstLimit(sites, (s) => s.against)
  const n = sites.length
  let named = false
  const phrase = (): ReactNode => {
    if (named) return 'the limit'
    named = true
    return <LimitPhrase limit={limit} />
  }
  const one = (s: TallySite) =>
    figures ? `${s.name} (${s.night.open ? 'at least ' : ''}${hoursWithMargin(s.night.h, s.night.marginH)})` : s.name
  const list = (xs: TallySite[]) => andList(xs.map(one))
  const nightAt = (xs: TallySite[]) => (xs.length === 1 ? 'The longest night at' : 'The longest nights at')
  const isAre = (xs: TallySite[]) => (xs.length === 1 ? 'is' : 'are')
  const out: ReactNode[] = []
  if (t.past.length) {
    out.push(
      t.past.length === n ? (
        <span key="past">
          All {n} sites have a longest night past {phrase()} on these dates{figures ? `: ${list(t.past)}` : ''}.
        </span>
      ) : (
        <span key="past">
          {t.past.length} of {n} sites {t.past.length === 1 ? 'has' : 'have'} a longest night past {phrase()} on these dates:{' '}
          {list(t.past)}.
        </span>
      ),
    )
  }
  if (t.withinMargin.length) {
    out.push(
      <span key="within">
        {nightAt(t.withinMargin)} {list(t.withinMargin)} {isAre(t.withinMargin)} within the margin of {phrase()}.
      </span>,
    )
  }
  if (t.cutShort.length) {
    out.push(
      <span key="cut">
        {nightAt(t.cutShort)} {list(t.cutShort)} {isAre(t.cutShort)} cut short by these dates, so{' '}
        {t.cutShort.length === 1 ? 'it' : 'they'} may run past {phrase()}.
      </span>,
    )
  }
  if (t.inside.length) {
    out.push(
      t.inside.length === n ? (
        <span key="inside">
          All {n} sites have a longest night inside {phrase()} on these dates{figures ? `: ${list(t.inside)}` : ''}.
        </span>
      ) : (
        <span key="inside">
          {nightAt(t.inside)} {list(t.inside)} {isAre(t.inside)} inside {phrase()}.
        </span>
      ),
    )
  }
  if (t.noNight.length) {
    out.push(<span key="none">The Sun did not set at {andList(t.noNight.map((s) => s.name))} on these dates.</span>)
  }
  return <>{out.flatMap((node, i) => (i ? [' ', node] : [node]))}</>
}

/** The gap has at least one edge that is a real crossing, so its ± means something. */
function hasTimedEdge(arc: Arc | undefined): boolean {
  return Boolean(arc && (arc.startToleranceH !== undefined || arc.endToleranceH !== undefined))
}

/**
 * The four numbers that decide a mission, always together and always in this
 * order: two totals, then the two worst-case gaps.
 */
export function KeyNumberRow({
  metrics,
  size = 'lg',
  columns = 4,
  uncertain = false,
}: {
  metrics?: SiteMetrics
  size?: 'lg' | 'md' | 'sm'
  columns?: 2 | 4
  /**
   * Every tile in its uncertain variant, numbers still shown: terrain is not
   * modelled at this site, so the skyline is a smooth sphere.
   */
  uncertain?: boolean
}) {
  const computing = !metrics
  const ready = uncertain ? 'uncertain' : 'ready'

  const win = metrics?.windowHours ?? 1
  const sunH = metrics?.sun.upHours ?? 0
  const earthH = metrics?.earth.upHours ?? 0
  // The server's own fractions, not upHours/windowHours recomputed here: one
  // number, one source, and the bar and the footnote cannot disagree.
  const sunFrac = metrics?.sun.fractionUp ?? 0
  const earthFrac = metrics?.earth.fractionUp ?? 0
  const dark = metrics?.sun.longestDownH ?? 0
  const darkArc = metrics?.sun.longestDownArc
  const darkGrazing = darkArc?.grazing
  const darkOpen = Boolean(metrics?.sun.longestDownOpen)
  // A ± times the edges of a gap. With no gap in the window, or a gap whose
  // both ends are the window's own edges, there is no crossing to time, so no
  // ± is shown at all rather than "±0.0".
  // Outside the terrain model the skyline is a smooth sphere with no height
  // error, so its tolerance is zero by construction, not a measured margin:
  // the uncertain state says why, and no ± is printed.
  const darkTol = hasTimedEdge(darkArc) && !uncertain ? metrics?.sun.longestDownToleranceH : undefined
  const rf = metrics?.earth.longestDownH ?? 0
  const rfArc = metrics?.earth.longestDownArc
  const rfGrazing = rfArc?.grazing
  const rfOpen = Boolean(metrics?.earth.longestDownOpen)
  const rfTol = hasTimedEdge(rfArc) && !uncertain ? metrics?.earth.longestDownToleranceH : undefined
  // R2: the team's entered limit, or 120 h said to be assumed. The night is
  // compared with it using the night's own margin: past it or inside it only
  // by more than the margin, "within the margin" otherwise. A lower bound
  // under the limit is not certainly under it: the night continues past the
  // dates.
  const limit = useBatteryLimit()
  // The same margin the tile prints (none when grazing or uncertain).
  const against: AgainstLimit | undefined = metrics ? nightAgainstLimit(longestNight(metrics, !uncertain), limit.h) : undefined
  const overLimit = !limit.pending && against?.kind === 'past'
  const noNight = Boolean(metrics) && !darkArc
  const noBlackout = Boolean(metrics) && !rfArc

  const grid = columns === 4 ? 'grid-cols-2 lg:grid-cols-4' : 'grid-cols-2'
  const t = {
    sun: termLabel('sunHours'),
    earth: termLabel('earthHours'),
    dark: termLabel('longestDark'),
    rf: termLabel('longestBlackout'),
  }

  return (
    <div className={`grid gap-4 lg:gap-5 ${grid}`}>
      <KeyNumberTile
        numberKind="computed"
        label={t.sun.label}
        means={t.sun.means}
        also={t.sun.also}
        inRow
        value={sunH}
        tone="sun"
        icon="sun"
        size={size}
        state={computing ? 'computing' : ready}
        fraction={sunFrac}
        footnote={metrics ? `${percent(sunFrac)} of the time` : 'measuring the skyline'}
      />
      <KeyNumberTile
        numberKind="computed"
        label={t.earth.label}
        means={t.earth.means}
        also={t.earth.also}
        inRow
        value={earthH}
        tone="earth"
        icon="earth"
        size={size}
        state={computing ? 'computing' : ready}
        fraction={earthFrac}
        footnote={metrics ? `${percent(earthFrac)} of the time` : undefined}
      />
      <KeyNumberTile
        numberKind="computed"
        label={t.dark.label}
        means={t.dark.means}
        also={t.dark.also}
        inRow
        value={dark}
        tone={overLimit ? 'alert' : 'neutral'}
        size={size}
        state={computing ? 'computing' : darkGrazing ? 'uncertain' : ready}
        toleranceH={darkGrazing ? undefined : darkTol}
        open={darkOpen}
        fraction={dark / limit.h}
        footnote={
          computing
            ? undefined
            : noNight
              ? 'The Sun did not set on these dates'
              : limit.pending || !against
                ? undefined
                : (
                    <>
                      <AgainstLimitWords a={against} limit={limit} />
                      {limit.basis === 'assumed' && (
                        <>
                          . <EnterLimit limit={limit} />
                        </>
                      )}
                    </>
                  )
        }
      />
      <KeyNumberTile
        numberKind="computed"
        label={t.rf.label}
        means={t.rf.means}
        also={t.rf.also}
        inRow
        value={rf}
        tone="neutral"
        size={size}
        state={computing ? 'computing' : rfGrazing ? 'uncertain' : ready}
        toleranceH={rfGrazing ? undefined : rfTol}
        open={rfOpen}
        fraction={rf / win}
        footnote={
          computing
            ? undefined
            : noBlackout
              ? 'Earth stayed in view on all of these dates'
              : rfOpen
                ? 'these dates cut this short; the lander must work alone at least this long'
                : 'the lander must work alone this long'
        }
      />
    </div>
  )
}
