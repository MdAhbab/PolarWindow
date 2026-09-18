import { useCountUp } from '../hooks/useCountUp'
import { APPROX, TERM, plusMinus } from '../lib/format'
import { SURVIVAL_LIMIT_H } from '../lib/geometry/metrics'
import type { Face, SiteMetrics } from '../lib/types'
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
}: {
  label: string
  value: number
  unit?: string
  tone?: Tone
  state?: TileState
  toleranceH?: number
  fraction?: number
  footnote?: string
  size?: 'lg' | 'md' | 'sm'
  icon?: Parameters<typeof Icon>[0]['name']
}) {
  const rolled = useCountUp(state === 'ready' || state === 'uncertain' ? value : 0)

  const numberClass =
    size === 'lg'
      ? 'text-[64px] leading-[58px]'
      : size === 'md'
        ? 'text-[44px] leading-[42px]'
        : 'text-[30px] leading-[30px]'

  const border =
    tone === 'alert'
      ? 'border-alert'
      : state === 'uncertain'
        ? 'border-dashed border-uncertain'
        : 'border-line'

  return (
    <div className={`flex flex-col gap-2 border bg-panel px-5 py-5 ${border}`}>
      <div
        className={`flex items-center gap-2 text-[12px] font-semibold tracking-[0.12em] uppercase ${
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
        <span>{label}</span>
      </div>

      <div className="flex items-baseline gap-2">
        {state === 'blank' ? (
          <span className={`font-semibold tracking-[-0.025em] text-line-strong ${numberClass}`}>—</span>
        ) : state === 'computing' ? (
          <span className={`font-semibold tracking-[-0.025em] text-line-strong ${numberClass}`}>——</span>
        ) : (
          <span className={`font-semibold tracking-[-0.025em] tnum ${numberClass} ${TONE_TEXT[tone]}`}>
            {APPROX}
            {Math.round(rolled)}
          </span>
        )}
        {toleranceH !== undefined && state !== 'blank' && state !== 'computing' && (
          <span className="text-[20px] text-uncertain tnum">{plusMinus(toleranceH)}</span>
        )}
        <span className="text-[19px] text-ink-2">{unit}</span>
      </div>

      <div className="flex h-1.5 bg-dark-fill">
        {state === 'ready' || state === 'uncertain' ? (
          <div
            className={`${TONE_BAR[tone]} transition-[width] duration-[600ms]`}
            style={{ width: `${Math.max(0, Math.min(100, (fraction ?? 0) * 100))}%` }}
          />
        ) : (
          <div className="w-1/3 bg-line-strong" />
        )}
      </div>

      {footnote && <div className="text-[12px] text-ink-3">{footnote}</div>}
    </div>
  )
}

/**
 * The four numbers that decide a mission, always together and always in this
 * order: two totals, then the two worst-case gaps.
 */
export function KeyNumberRow({
  metrics,
  face,
  size = 'lg',
  columns = 4,
}: {
  metrics?: SiteMetrics
  face: Face
  size?: 'lg' | 'md' | 'sm'
  columns?: 2 | 4
}) {
  const earthDown = false
  const computing = !metrics

  const win = metrics?.windowHours ?? 1
  const sunH = metrics?.sun.upHours ?? 0
  const earthH = metrics?.earth.upHours ?? 0
  const dark = metrics?.sun.longestDownH ?? 0
  const darkTol = metrics?.sun.longestDownToleranceH
  const darkGrazing = metrics?.sun.longestDownArc?.grazing
  const rf = metrics?.earth.longestDownH ?? 0
  const overLimit = dark > SURVIVAL_LIMIT_H

  const grid = columns === 4 ? 'grid-cols-2 lg:grid-cols-4' : 'grid-cols-2'
  const short = columns === 2
  const L = {
    sun: short ? 'Sunlight' : TERM.sunHours[face],
    earth: short ? 'Earth contact' : TERM.earthHours[face],
    dark: short ? 'Dark gap' : TERM.longestDark[face],
    rf: short ? 'RF blackout' : TERM.longestBlackout[face],
  }

  return (
    <div className={`grid gap-4 ${grid}`}>
      <KeyNumberTile
        label={L.sun}
        value={sunH}
        tone="sun"
        icon="sun"
        size={size}
        state={computing ? 'computing' : 'ready'}
        fraction={sunH / win}
        footnote={metrics ? `${Math.round((sunH / win) * 100)}% of the window` : 'ray-casting the skyline'}
      />
      <KeyNumberTile
        label={L.earth}
        value={earthH}
        tone="earth"
        icon="earth"
        size={size}
        state={earthDown ? 'blank' : computing ? 'computing' : 'ready'}
        fraction={earthH / win}
        footnote={
          earthDown
            ? 'ephemeris unavailable — blank, not zero'
            : metrics
              ? `${Math.round((earthH / win) * 100)}% of the window`
              : undefined
        }
      />
      <KeyNumberTile
        label={L.dark}
        value={dark}
        tone={overLimit ? 'alert' : 'neutral'}
        size={size}
        state={computing ? 'computing' : darkGrazing ? 'uncertain' : 'ready'}
        toleranceH={darkTol}
        fraction={dark / SURVIVAL_LIMIT_H}
        footnote={
          computing
            ? undefined
            : overLimit
              ? `${Math.round(dark - SURVIVAL_LIMIT_H)} h over the ${SURVIVAL_LIMIT_H} h limit`
              : `${Math.round(SURVIVAL_LIMIT_H - dark)} h of margin on ${SURVIVAL_LIMIT_H} h`
        }
      />
      <KeyNumberTile
        label={L.rf}
        value={rf}
        tone="neutral"
        size={size}
        state={earthDown ? 'blank' : computing ? 'computing' : 'ready'}
        fraction={rf / win}
        footnote={earthDown ? 'ephemeris unavailable' : computing ? undefined : 'autonomy must cover this'}
      />
    </div>
  )
}
