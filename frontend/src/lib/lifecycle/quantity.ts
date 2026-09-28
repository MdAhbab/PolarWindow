/**
 * One number shape on screen (ADR-9, invariant 2).
 *
 * The API sends every lifecycle number as a `Quantity`: a value with exactly
 * one kind of margin (±, a low–high range, or a ×/÷ factor), or the reason it
 * has none, or no value and the reason why. This module turns one into what a
 * tile draws and what a screen reader says, in one place, so no screen
 * formats a margin its own way.
 */
import type { Provenance, QuantityDTO, ShareDTO } from '../api/lifecycle'
import { dateWords, monthWords, shortDate } from '../format'

export interface QuantityView {
  kind: 'number' | 'range' | 'time' | 'missing'
  /** The figure as drawn: "12", "12–31", "≥288", "4.1 × 10⁹", "00:16 UTC". */
  figure: string
  /** For a time: the date (and "UTC"), drawn above the figure. */
  figureAbove?: string
  /** The whole value in one line, for sentences and table cells: "27 Feb 2025, 01:06 UTC ±4 min". */
  sentence: string
  /** "±2", "×/÷2", "±4 min"; absent when there is no margin. */
  margin?: string
  /** The unit as drawn beside the figure ("h", "°", "m/s"); empty for none. */
  unit: string
  /** Why there is no margin, said on screen (invariant 2). */
  noMarginReason?: string
  /** Why there is no value. */
  missingReason?: string
  value: number | null
  lo?: number
  hi?: number
  open: boolean
  provenance: Provenance
  source: string | null
  /** One sentence for a screen reader, with the unit and the margin. */
  spoken: string
}

interface UnitWords {
  short: string
  spoken: string
  /** Drawn against the figure with no space ("12°"). */
  joined?: boolean
}

const UNITS: Record<string, UnitWords> = {
  h: { short: 'h', spoken: 'hours' },
  min: { short: 'min', spoken: 'minutes' },
  s: { short: 's', spoken: 'seconds' },
  d: { short: 'days', spoken: 'days' },
  deg: { short: '°', spoken: 'degrees', joined: true },
  km: { short: 'km', spoken: 'kilometres' },
  m: { short: 'm', spoken: 'metres' },
  'm/s': { short: 'm/s', spoken: 'metres a second' },
  'mm/h': { short: 'mm/h', spoken: 'millimetres an hour' },
  ft: { short: 'ft', spoken: 'feet' },
  nmi: { short: 'nautical miles', spoken: 'nautical miles' },
  kbps: { short: 'kbit/s', spoken: 'kilobits a second' },
  dB: { short: 'dB', spoken: 'decibels' },
  'mGy/day': { short: 'mGy a day', spoken: 'milligray a day' },
  'mGy/d': { short: 'mGy a day', spoken: 'milligray a day' },
  'km/s': { short: 'km/s', spoken: 'kilometres a second' },
  nT: { short: 'nT', spoken: 'nanotesla' },
  'cm^-2': { short: 'per cm²', spoken: 'per square centimetre' },
  pfu: { short: 'pfu', spoken: 'proton flux units' },
  '%': { short: '%', spoken: 'percent', joined: true },
  Kp: { short: '', spoken: '' },
  '': { short: '', spoken: '' },
}

export const TIME_UNIT = 's since epoch'

export function unitWords(unit: string): UnitWords {
  return UNITS[unit] ?? { short: unit, spoken: unit }
}

const SUPERSCRIPT: Record<string, string> = {
  '-': '⁻',
  '0': '⁰',
  '1': '¹',
  '2': '²',
  '3': '³',
  '4': '⁴',
  '5': '⁵',
  '6': '⁶',
  '7': '⁷',
  '8': '⁸',
  '9': '⁹',
}

/**
 * Decimals that show a margin's own size: ±6 → 0, ±0.4 → 1, ±0.02 → 2. A
 * margin between 1 and 3 keeps one decimal (±2.1, not ±2), because rounding
 * it away moves the value by a large part of its own margin.
 */
function decimalsFor(margin: number): number {
  if (!(margin > 0)) return 0
  if (margin >= 1 && margin < 3 && !Number.isInteger(margin)) return 1
  return Math.max(0, Math.min(3, Math.ceil(-Math.log10(margin) - 1e-9)))
}

/**
 * A value as a person writes it: at most three significant figures unless
 * the margin asks for more, thousands separated, and a power of ten for very
 * large or very small numbers ("4.1 × 10⁹").
 */
export function formatValue(v: number, margin?: number | null): string {
  if (!Number.isFinite(v)) return '—'
  const a = Math.abs(v)
  if (a !== 0 && (a >= 1e6 || a < 1e-3)) {
    const exp = Math.floor(Math.log10(a))
    const mant = v / 10 ** exp
    const sup = String(exp)
      .split('')
      .map((c) => SUPERSCRIPT[c] ?? c)
      .join('')
    return `${trim(mant.toFixed(1))} × 10${sup}`
  }
  let digits: number
  if (margin !== undefined && margin !== null && margin > 0) digits = decimalsFor(margin)
  else digits = a >= 100 ? 0 : a >= 10 ? 1 : a >= 1 ? 1 : 2
  const fixed = v.toFixed(digits)
  const shown = margin ? fixed : trim(fixed)
  const [int, frac] = shown.split('.')
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return frac ? `${grouped}.${frac}` : grouped
}

function trim(s: string): string {
  return s.includes('.') ? s.replace(/\.?0+$/, '') : s
}

/** "±4 min", "±30 s", "±3 days": a time margin in the unit that reads best. */
export function durationMargin(seconds: number): string {
  const s = Math.abs(seconds)
  if (s < 60) return `±${Math.round(s)} s`
  if (s < 2 * 3600) return `±${Math.round(s / 60)} min`
  if (s < 2 * 86400) return `±${formatValue(s / 3600, 0.1)} h`
  if (s < 60 * 86400) return `±${Math.round(s / 86400)} days`
  return `±${Math.round(s / (30.44 * 86400))} months`
}

function durationSpoken(seconds: number): string {
  const s = Math.abs(seconds)
  if (s < 60) return `${Math.round(s)} seconds`
  if (s < 2 * 3600) return `${Math.round(s / 60)} minutes`
  if (s < 2 * 86400) return `${formatValue(s / 3600, 0.1)} hours`
  if (s < 60 * 86400) return `${Math.round(s / 86400)} days`
  return `${Math.round(s / (30.44 * 86400))} months`
}

const pad2 = (n: number) => String(n).padStart(2, '0')

/** "00:16 UTC" for an instant in epoch seconds. */
export function clockWords(epochS: number): string {
  const d = new Date(epochS * 1000)
  return `${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())} UTC`
}

const MONTH_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** "8 Oct": a day and month, the figure of a date whose year sits above it. */
function dayMonth(ms: number): string {
  const d = new Date(ms)
  return `${d.getUTCDate()} ${MONTH_SHORT[d.getUTCMonth()]}`
}

/**
 * A moment. Known to the minute, the figure is the clock time and the date
 * sits above it ("27 Feb 2025 · UTC" over "01:06"); known only to a day or
 * worse, the figure is the day and month and the year sits above it.
 */
function timeView(q: QuantityDTO): QuantityView {
  const base = { open: q.open, provenance: q.provenance, source: q.source, unit: '' }
  // Known to a day or worse, or a bare date (midnight, no margin): the date is the figure.
  const coarse =
    (q.pm ?? 0) >= 86400 ||
    (q.lo !== null && q.hi !== null && q.hi - q.lo >= 2 * 86400) ||
    (q.pm === null && q.value !== null && q.value % 86400 === 0)
  const clock = (sec: number) => clockWords(sec).replace(' UTC', '')
  if (q.lo !== null && q.hi !== null && q.pm === null) {
    const lo = q.lo
    const hi = q.hi
    return {
      ...base,
      kind: 'time',
      value: q.value,
      lo,
      hi,
      figure: coarse ? `${dayMonth(lo * 1000)}–${dayMonth(hi * 1000)}` : `${clock(lo)}–${clock(hi)}`,
      figureAbove: coarse ? String(new Date(lo * 1000).getUTCFullYear()) : `${shortDate(lo * 1000)} · UTC`,
      sentence: coarse
        ? `${shortDate(lo * 1000)} to ${shortDate(hi * 1000)}`
        : `${shortDate(lo * 1000)}, ${clock(lo)} to ${clockWords(hi)}`,
      spoken: coarse
        ? `between ${dateWords(lo * 1000)} and ${dateWords(hi * 1000)}`
        : `between ${clockWords(lo)} and ${clockWords(hi)} on ${dateWords(lo * 1000)}`,
    }
  }
  const v = q.value as number
  const ms = v * 1000
  // Known only to months: a day would be false precision, so the figure is
  // the span of months it could fall in ("Jan–Dec" over "2026").
  if (q.pm !== null && q.pm >= 45 * 86400) {
    const lo = (v - q.pm) * 1000
    const hi = (v + q.pm) * 1000
    const y1 = new Date(lo).getUTCFullYear()
    const y2 = new Date(hi).getUTCFullYear()
    const mon = (t: number) => MONTH_SHORT[new Date(t).getUTCMonth()]
    return {
      ...base,
      kind: 'time',
      value: v,
      lo: v - q.pm,
      hi: v + q.pm,
      figure: mon(lo) === mon(hi) && y1 === y2 ? mon(lo) : `${mon(lo)}–${mon(hi)}`,
      figureAbove: y1 === y2 ? String(y1) : `${y1}–${y2}`,
      sentence: `between ${monthWords(lo)} and ${monthWords(hi)}`,
      spoken: `between ${monthWords(lo)} and ${monthWords(hi)}`,
    }
  }
  const margin = q.pm !== null ? durationMargin(q.pm) : undefined
  return {
    ...base,
    kind: 'time',
    value: v,
    figure: coarse ? dayMonth(ms) : clock(v),
    figureAbove: coarse ? String(new Date(ms).getUTCFullYear()) : `${shortDate(ms)} · UTC`,
    margin,
    noMarginReason: q.pm === null ? (q.no_margin_reason ?? undefined) : undefined,
    sentence: `${coarse ? shortDate(ms) : `${shortDate(ms)}, ${clockWords(v)}`}${margin ? ` ${margin}` : ''}`,
    spoken: `${coarse ? dateWords(ms) : `${dateWords(ms)}, ${clockWords(v)}`}${
      q.pm !== null ? `, plus or minus ${durationSpoken(q.pm)}` : ''
    }`,
  }
}

/** A `Quantity` as a tile draws it and a screen reader says it. */
export function quantityView(q: QuantityDTO): QuantityView {
  const u = unitWords(q.unit)
  const unitSpoken = u.spoken ? ` ${u.spoken}` : ''
  const hasRange = q.lo !== null && q.hi !== null
  if (q.value === null && !hasRange) {
    const reason = q.missing_reason ?? 'no value was given'
    return {
      kind: 'missing',
      figure: '—',
      unit: u.short,
      value: null,
      open: false,
      provenance: q.provenance,
      source: q.source,
      missingReason: reason,
      sentence: 'not available',
      spoken: `Not available: ${reason}`,
    }
  }
  if (q.unit === TIME_UNIT) return timeView(q)
  // "At least zero" says nothing: a zero is shown as a plain zero.
  if (q.open && q.value === 0 && q.lo === null) return quantityView({ ...q, open: false })
  // Under a minute, a wait reads better in seconds ("1.2 s", not "0.02 min").
  if (q.unit === 'min' && q.value !== null && Math.abs(q.value) < 1 && q.lo === null) {
    const s60 = (x: number | null) => (x === null ? null : x * 60)
    return quantityView({ ...q, unit: 's', value: s60(q.value), pm: s60(q.pm) })
  }
  // Two hours or more reads better in hours ("286 h", not "17,167 min").
  if (q.unit === 'min' && q.value !== null && Math.abs(q.value) >= 120 && q.lo === null) {
    const h = (x: number | null) => (x === null ? null : x / 60)
    return quantityView({ ...q, unit: 'h', value: h(q.value), pm: h(q.pm) })
  }

  const bound = q.open ? '≥' : ''
  const common = {
    unit: u.short,
    open: q.open,
    provenance: q.provenance,
    source: q.source,
  }
  // "12 ±2 h", and for a unit written against the number, "4.1° ±0.3°".
  const line = (figure: string, margin?: string) =>
    u.joined
      ? `${figure}${u.short}${margin ? ` ${margin}${margin.startsWith('±') ? u.short : ''}` : ''}`
      : `${figure}${margin ? ` ${margin}` : ''}${u.short ? ` ${u.short}` : ''}`

  if (hasRange && q.pm === null && q.factor === null) {
    const lo = q.lo as number
    const hi = q.hi as number
    const same = formatValue(lo) === formatValue(hi)
    const figure = same ? `${bound}${formatValue(lo)}` : `${bound}${formatValue(lo)}–${formatValue(hi)}`
    return {
      ...common,
      kind: 'range',
      figure,
      sentence: line(figure),
      value: q.value,
      lo,
      hi,
      spoken: same ? `about ${formatValue(lo)}${unitSpoken}` : `${formatValue(lo)} to ${formatValue(hi)}${unitSpoken}`,
    }
  }

  const v = q.value as number
  if (q.factor !== null) {
    const f = formatValue(q.factor)
    return {
      ...common,
      kind: 'number',
      figure: `${bound}${formatValue(v)}`,
      margin: `×/÷${f}`,
      sentence: line(`${bound}${formatValue(v)}`, `×/÷${f}`),
      value: v,
      spoken: `${q.open ? 'at least' : 'about'} ${formatValue(v).replace(' × 10', ' times 10 to the ')}${unitSpoken}, good to a factor of ${f}`,
    }
  }
  if (q.pm !== null) {
    return {
      ...common,
      kind: 'number',
      figure: `${bound}${formatValue(v, q.pm)}`,
      margin: `±${formatValue(q.pm, q.pm)}`,
      sentence: line(`${bound}${formatValue(v, q.pm)}`, `±${formatValue(q.pm, q.pm)}`),
      value: v,
      spoken: `${q.open ? 'at least' : 'about'} ${formatValue(v, q.pm)}${unitSpoken}, plus or minus ${formatValue(q.pm, q.pm)}${unitSpoken}`,
    }
  }
  return {
    ...common,
    kind: 'number',
    figure: `${bound}${formatValue(v)}`,
    sentence: line(`${bound}${formatValue(v)}`),
    value: v,
    noMarginReason: q.no_margin_reason ?? 'none was given',
    spoken: `${q.open ? 'at least' : ''}${q.open ? ' ' : ''}${formatValue(v)}${unitSpoken}`,
  }
}

/** The figure, margin and unit on one line, for sentences and table cells: "12 ±2 h", "12–31 h". */
export function quantityText(q: QuantityDTO | null | undefined): string {
  if (!q) return 'not given'
  return quantityView(q).sentence
}

/** Invariant 10, in words: where a number comes from. */
export function provenanceWords(p: Provenance, source: string | null): { lead: string; source: string | null } {
  switch (p) {
    case 'computed':
      return { lead: 'Worked out by POLAR WINDOW', source }
    case 'published':
      return { lead: 'Published', source }
    case 'entered':
      return { lead: source ? `Entered by ${source}` : 'Entered by the team', source: null }
    case 'assumed':
      return { lead: 'Assumed', source }
  }
}

export function isUrl(s: string | null | undefined): s is string {
  return Boolean(s && /^https?:\/\//.test(s))
}

/** The host of a source URL, as a link's words ("nasa.gov"). */
export function hostWords(url: string): string {
  try {
    return new URL(url).host.replace(/^www\./, '')
  } catch {
    return url
  }
}

// ---------------------------------------------------------------------------
// Shares of model runs (invariant 12)
// ---------------------------------------------------------------------------

const pct = (f: number) => `${Math.round(f * 100)}%`

export interface ShareView {
  /** "3 of 31 model runs" */
  count: string
  /** "95% range 2 to 26%" */
  range: string
  checked: string
  spoken: string
}

export function shareView(s: ShareDTO): ShareView {
  const count = `${s.k} of ${s.n} model runs`
  const range = `95% range ${Math.round(s.lo * 100)} to ${pct(s.hi)}`
  const checked = s.checked ? 'checked against observations' : 'not yet checked against observations'
  return { count, range, checked, spoken: `${count} break the rule, ${range}, ${checked}` }
}

// ---------------------------------------------------------------------------
// Age (invariant 11)
// ---------------------------------------------------------------------------

/**
 * How old something is, in words. Uses the viewer's clock, which is the only
 * way to say how old a live number is now; the exact time goes in the title.
 */
export function ageWords(fromMs: number, nowMs: number = Date.now()): string {
  const s = Math.max(0, (nowMs - fromMs) / 1000)
  if (s < 90) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 48 * 3600) return `${Math.round(s / 3600)} h ago`
  return `${Math.round(s / 86400)} days ago`
}

/** An age given in seconds by the server ("age_s"). */
export function ageFromSeconds(s: number | null): string {
  if (s === null) return 'never'
  return ageWords(0, s * 1000)
}
