/**
 * Pure helpers for the lander tools: scales, ticks, number and margin words,
 * and the share wording. No React here, so each is tested on its own.
 */
import type { QuantityDTO, ProvenanceWord } from '../../lib/api/surface.types'

/** A linear map from a domain to a range; a zero-width domain maps to the range's middle. */
export function linear(d0: number, d1: number, r0: number, r1: number): (v: number) => number {
  const span = d1 - d0
  if (!Number.isFinite(span) || span === 0) return () => (r0 + r1) / 2
  return (v) => r0 + ((v - d0) / span) * (r1 - r0)
}

/** About `count` round ticks covering [min, max] (1, 2, 2.5 or 5 times a power of ten). */
export function niceTicks(min: number, max: number, count = 4): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return []
  if (min === max) return [min]
  const lo = Math.min(min, max)
  const hi = Math.max(min, max)
  const raw = (hi - lo) / Math.max(1, count)
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? 10 * mag
  const out: number[] = []
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(Math.abs(v) < step * 1e-9 ? 0 : v)
  return out
}

/** A domain padded to round ticks, so the data never touches the frame. */
export function niceDomain(values: number[], count = 4): [number, number] {
  const finite = values.filter((v) => Number.isFinite(v))
  if (finite.length === 0) return [0, 1]
  let lo = Math.min(...finite)
  let hi = Math.max(...finite)
  if (lo === hi) {
    lo -= 1
    hi += 1
  }
  const ticks = niceTicks(lo, hi, count)
  const step = ticks.length > 1 ? ticks[1] - ticks[0] : 1
  return [Math.floor(lo / step) * step, Math.ceil(hi / step) * step]
}

/** A number in a sensible number of digits, with a true minus sign. */
export function num(v: number, digits?: number): string {
  if (!Number.isFinite(v)) return 'not available'
  const a = Math.abs(v)
  const d = digits ?? (a >= 100 ? 0 : a >= 10 ? 1 : a >= 1 ? 2 : a === 0 ? 0 : 3)
  const s = v.toLocaleString('en-GB', { minimumFractionDigits: d, maximumFractionDigits: d })
  return s.replace(/^-/, '−')
}

const UNIT_WORDS: Record<string, string> = {
  degC: '°C',
  deg: '°',
  m2: 'm²',
  '1': '',
  fraction: '',
  h: 'h',
  K: 'K',
  Wh: 'Wh',
  W: 'W',
  'J/K': 'J/K',
}

export function unitWord(unit: string | undefined | null): string {
  if (!unit) return ''
  return UNIT_WORDS[unit] ?? unit
}

/** Energy in watt-hours read better as kilowatt-hours once they are large. */
export function scaled(q: QuantityDTO): QuantityDTO {
  if (q.unit !== 'Wh' || q.value === null || Math.abs(q.value) < 10_000) return q
  const k = (v: number | null | undefined) => (typeof v === 'number' ? v / 1000 : v)
  return { ...q, unit: 'kWh', value: k(q.value) as number, pm: k(q.pm), lo: k(q.lo), hi: k(q.hi) }
}

export interface QuantityWords {
  /** The number itself ("−104", "at least 12"), or a dash when there is none. */
  value: string
  unit: string
  /** The margin in words: "± 1.4", "range −107 to −101", "× ÷ 1.3", or the stated reason there is none. */
  margin: string
  /** True when `margin` is a reason (no number), so it reads as a sentence. */
  marginIsReason: boolean
  provenance: ProvenanceWord
}

/** A quantity's number, its margin (or the reason it has none) and where it came from. */
export function quantityWords(raw: QuantityDTO, digits?: number): QuantityWords {
  const q = scaled(raw)
  const unit = unitWord(q.unit)
  if (q.value === null || q.value === undefined) {
    return { value: 'not available', unit, margin: q.missing_reason ?? 'not worked out', marginIsReason: true, provenance: q.provenance }
  }
  const value = `${q.open ? 'at least ' : ''}${num(q.value, digits)}`
  let margin: string
  let marginIsReason = false
  if (typeof q.pm === 'number') margin = `± ${num(q.pm, digits)}`
  else if (typeof q.lo === 'number' && typeof q.hi === 'number') {
    const lo = num(q.lo, digits)
    const hi = num(q.hi, digits)
    margin = lo === hi ? `${lo} at both ends of the range` : `range ${lo} to ${hi}`
  } else if (typeof q.lo === 'number') margin = `from ${num(q.lo, digits)}; the upper end is unknown`
  else if (typeof q.hi === 'number') margin = `up to ${num(q.hi, digits)}; the lower end is unknown`
  else if (typeof q.factor === 'number') margin = `× ÷ ${num(q.factor, 2)}`
  else {
    margin = q.no_margin_reason ?? 'no margin stated'
    marginIsReason = true
  }
  return { value, unit, margin, marginIsReason, provenance: q.provenance }
}

/** A share as a percentage: one decimal under 10 %, whole numbers above. */
export function pct(fraction: number): string {
  const p = fraction * 100
  if (p === 0) return '0'
  return p < 10 ? p.toFixed(1) : p.toFixed(0)
}

export interface ShareDTO {
  k: number
  n: number
  lo: number
  hi: number
  checked?: boolean
}

/** "354 of 1000 points (32 to 38 %)": the count, then its exact 95 % interval. */
export function shareWords(s: ShareDTO): string {
  return `${s.k} of ${s.n} points (${pct(s.lo)} to ${pct(s.hi)} %)`
}

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const pad = (n: number) => String(n).padStart(2, '0')

/** A tick or readout time in UTC: "24 Jan", or "24 Jan 23:50" when asked for the time. */
export function utcWords(ms: number, withTime = false): string {
  const d = new Date(ms)
  const day = `${d.getUTCDate()} ${MON[d.getUTCMonth()]}`
  return withTime ? `${day} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}` : day
}

/** Runs of consecutive indices where `pred` holds, as [first, last] pairs. */
export function runs<T>(xs: T[], pred: (x: T) => boolean): [number, number][] {
  const out: [number, number][] = []
  let start = -1
  xs.forEach((x, i) => {
    if (pred(x)) {
      if (start < 0) start = i
    } else if (start >= 0) {
      out.push([start, i - 1])
      start = -1
    }
  })
  if (start >= 0) out.push([start, xs.length - 1])
  return out
}

/** A polyline path through the points that have a value; a gap breaks the line. */
export function linePath(xs: number[], ys: (number | null)[]): string {
  let d = ''
  let pen = false
  ys.forEach((y, i) => {
    if (y === null || !Number.isFinite(y)) {
      pen = false
      return
    }
    d += `${pen ? 'L' : 'M'}${xs[i].toFixed(1)} ${y.toFixed(1)}`
    pen = true
  })
  return d
}

/** A closed band between two edges, one polygon per stretch where both edges are known. */
export function bandPath(xs: number[], lo: (number | null)[], hi: (number | null)[]): string {
  const ok = xs.map((_, i) => lo[i] !== null && hi[i] !== null && Number.isFinite(lo[i]!) && Number.isFinite(hi[i]!))
  return runs(ok, (b) => b)
    .map(([a, b]) => {
      let d = ''
      for (let i = a; i <= b; i++) d += `${i === a ? 'M' : 'L'}${xs[i].toFixed(1)} ${(hi[i] as number).toFixed(1)}`
      for (let i = b; i >= a; i--) d += `L${xs[i].toFixed(1)} ${(lo[i] as number).toFixed(1)}`
      return `${d}Z`
    })
    .join('')
}
