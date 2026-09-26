import { useId, useState, type ReactNode } from 'react'
import { useCountUp } from '../hooks/useCountUp'
import { bound, hoursSpoken, percent, plusMinus, termLabel } from '../lib/format'
import { SURVIVAL_LIMIT_H } from '../lib/geometry/metrics'
import type { Arc, SiteMetrics } from '../lib/types'
import { Icon } from './Icon'

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
  footnote?: string
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
}) {
  const shown = state === 'ready' || state === 'uncertain'
  // NaN while there is no value: the first real value is set directly, and
  // the roll (M4) only ever runs between two real values, never from zero.
  const rolled = useCountUp(shown ? value : Number.NaN)
  const [explained, setExplained] = useState(false)
  const explainId = useId()
  // One sentence with the final value, its unit and its margin. The visible
  // figure rolls through intermediate values (M4) and its ± sits in a separate
  // element, so reading the visuals aloud announced "±17.1" with no unit.
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
      ? // The four stay together as a 2×2 on a phone; at 64 px a three-digit
        // value is wider than its tile below 640 px, so it steps down to the
        // md size there rather than overflowing (WCAG 1.4.10).
        'text-figure-md leading-figure-md sm:text-figure-lg sm:leading-figure-lg'
      : size === 'md'
        ? 'text-figure-md leading-figure-md'
        : 'text-figure leading-figure'

  const explains = Boolean(means || source)
  const border =
    tone === 'alert'
      ? 'border-alert'
      : state === 'uncertain'
        ? 'border-dashed border-uncertain'
        : 'border-line'

  return (
    <div
      className={`border bg-panel px-5 py-5 ${border} ${
        inRow ? 'row-span-6 grid grid-rows-subgrid content-start gap-y-2' : 'flex flex-col gap-2'
      }`}
    >
      {/* Two lines tall even when the label fits on one, so the four values
          sit on one baseline when a neighbour's label wraps. */}
      <div
        className={`flex min-h-8 items-start gap-2 text-caption font-semibold tracking-caps uppercase ${
          tone === 'alert' ? 'text-alert' : state === 'uncertain' ? 'text-ink-2' : 'text-ink-3'
        }`}
      >
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
            className="-my-2 -mr-2 flex grow cursor-pointer items-start justify-between gap-2 py-2 pr-2 text-left uppercase hover:text-ink"
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
          <span className={`font-semibold tracking-figure text-line-strong ${numberClass}`}>—</span>
        ) : state === 'computing' ? (
          <span className={`font-semibold tracking-figure text-line-strong ${numberClass}`}>——</span>
        ) : display !== undefined ? (
          <span className={`font-semibold tracking-figure tnum ${numberClass} ${TONE_TEXT[tone]}`}>{display}</span>
        ) : (
          <span className={`font-semibold tracking-figure tnum ${numberClass} ${TONE_TEXT[tone]}`}>
            {bound(open)}
            {Math.round(rolled)}
          </span>
        )}
        <span className="flex items-baseline gap-2">
          {margin !== undefined && state !== 'blank' && state !== 'computing' ? (
            <span className="text-subhead text-uncertain tnum">{margin}</span>
          ) : (
            toleranceH !== undefined &&
            state !== 'blank' &&
            state !== 'computing' && <span className="text-subhead text-uncertain tnum">{plusMinus(toleranceH)}</span>
          )}
          {unit && <span className="text-large text-ink-2">{unit}</span>}
        </span>
      </div>

      {bar ? (
        <div className="relative flex h-1.5 bg-dark-fill">
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
              <div
                className={`${TONE_BAR[tone]} transition-[width] duration-[600ms]`}
                style={{ width: `${clampPct(fraction ?? 0)}%` }}
              />
            )
          ) : (
            <div className="w-1/3 bg-line-strong" />
          )}
        </div>
      ) : inRow ? (
        <div />
      ) : null}

      {footnote || age ? (
        <div className="flex flex-col gap-0.5 text-caption text-ink-3">
          {footnote && <span>{footnote}</span>}
          {age && <span className="text-ink-2">{age}</span>}
        </div>
      ) : inRow ? (
        <div />
      ) : null}
      {explains && (
        <p id={explainId} hidden={!explained} className="border-t border-line pt-2 text-small leading-5 text-ink-2">
          {means}
          {also && <span className="block pt-1 text-ink-3">Also called {also}.</span>}
          {source && <span className="block pt-1 text-ink-3">{source}</span>}
        </p>
      )}
    </div>
  )
}

const clampPct = (f: number) => Math.max(0, Math.min(100, f * 100))

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
   * modelled at this site (outside 80°S), so the skyline is a smooth sphere.
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
  // A lower bound over the limit is certainly over it; a lower bound under the
  // limit is not certainly under it -- the night continues past the window.
  const overLimit = dark > SURVIVAL_LIMIT_H
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
    <div className={`grid gap-4 ${grid}`}>
      <KeyNumberTile
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
        fraction={dark / SURVIVAL_LIMIT_H}
        footnote={
          computing
            ? undefined
            : noNight
              ? 'The Sun did not set on these dates'
              : overLimit
                ? `${darkOpen ? 'at least ' : ''}${Math.round(dark - SURVIVAL_LIMIT_H)} h over the ${SURVIVAL_LIMIT_H} h battery limit`
                : darkOpen
                  ? `these dates cut this night short; it may run past the ${SURVIVAL_LIMIT_H} h battery limit`
                  : `${Math.round(SURVIVAL_LIMIT_H - dark)} h inside the ${SURVIVAL_LIMIT_H} h battery limit`
        }
      />
      <KeyNumberTile
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
