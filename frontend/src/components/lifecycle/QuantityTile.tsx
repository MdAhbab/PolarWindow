import type { ReactNode } from 'react'
import type { QuantityDTO } from '../../lib/api/lifecycle'
import { hostWords, isUrl, provenanceWords, quantityView, unitWords } from '../../lib/lifecycle/quantity'
import { termLabel } from '../../lib/format'
import { KeyNumberTile, type Tone } from '../KeyNumbers'

/**
 * A lifecycle key number: `KeyNumberTile` fed a `Quantity` (ADR-9).
 *
 * Every margin form draws the same way everywhere: ± beside the figure, a
 * range as "12–31" with the bar hatched between its ends, a factor as ×/÷, a
 * lower bound with ≥. A number without a margin says why under it; a missing
 * number is a dash and the reason. Where it comes from opens from the label.
 */
export function QuantityTile({
  term,
  q,
  tone = 'neutral',
  scale,
  note,
  age,
  inRow = true,
  icon,
}: {
  /** A key of `TERM` in `format.ts`: the label, its meaning and its other name. */
  term: string
  q: QuantityDTO | null | undefined
  tone?: Tone
  /** The value that fills the bar; no bar without one. */
  scale?: number
  /** A caller's line under the number ("if it flies as planned"). */
  note?: string
  /** How old a live number is, always on screen (invariant 11). */
  age?: string
  inRow?: boolean
  icon?: Parameters<typeof KeyNumberTile>[0]['icon']
}) {
  const t = termLabel(term)
  if (!q) {
    return <KeyNumberTile label={t.label} means={t.means} also={t.also} value={0} unit="" state="computing" inRow={inRow} tone={tone} icon={icon} />
  }
  const v = quantityView(q)
  const joined = unitWords(q.unit).joined
  const display = joined && v.kind !== 'missing' ? `${v.figure}${v.unit}` : v.figure
  // A missing number has no unit to show beside its dash.
  const unit = joined || v.kind === 'missing' ? '' : v.unit
  const lower = (t: string) => t.charAt(0).toLowerCase() + t.slice(1)
  const lines = [note, v.noMarginReason ? `No margin: ${lower(v.noMarginReason)}` : undefined, v.missingReason].filter(Boolean)
  const fraction = scale && v.value !== null ? v.value / scale : undefined
  const range = scale && v.kind === 'range' && v.lo !== undefined && v.hi !== undefined ? { lo: v.lo / scale, hi: v.hi / scale } : undefined
  return (
    <KeyNumberTile
      label={t.label}
      means={t.means}
      also={t.also}
      inRow={inRow}
      icon={icon}
      tone={tone}
      value={v.value ?? 0}
      display={display}
      above={v.figureAbove}
      margin={joined && v.margin?.startsWith('±') ? `${v.margin}${v.unit}` : v.margin}
      unit={unit}
      state={v.kind === 'missing' ? 'blank' : 'ready'}
      open={v.open}
      fraction={fraction}
      range={range}
      bar={Boolean(scale) && v.kind !== 'time' && v.kind !== 'missing'}
      footnote={lines.length ? lines.join(' ') : undefined}
      spoken={v.spoken}
      age={age}
      source={<SourceLine provenance={q.provenance} source={q.source} />}
    />
  )
}

/** Invariant 10: computed, published (with its source), entered (by whom) or assumed. */
export function SourceLine({ provenance, source }: { provenance: QuantityDTO['provenance']; source: string | null }) {
  const p = provenanceWords(provenance, source)
  return (
    <>
      {p.lead}
      {p.source &&
        (isUrl(p.source) ? (
          <>
            {': '}
            <a href={p.source} target="_blank" rel="noreferrer">
              {hostWords(p.source)}
            </a>
          </>
        ) : (
          `: ${p.source}`
        ))}
      .
    </>
  )
}

/** A count: exact, so it carries no margin, and says it is a count. */
export function CountTile({
  term,
  value,
  of,
  note,
  tone = 'neutral',
  inRow = true,
  icon,
}: {
  term: string
  value: number | null
  of?: number
  note?: string
  tone?: Tone
  inRow?: boolean
  icon?: Parameters<typeof KeyNumberTile>[0]['icon']
}) {
  const t = termLabel(term)
  if (value === null) {
    return <KeyNumberTile label={t.label} means={t.means} value={0} unit="" state="computing" inRow={inRow} />
  }
  return (
    <KeyNumberTile
      label={t.label}
      means={t.means}
      inRow={inRow}
      tone={tone}
      icon={icon}
      value={value}
      display={String(value)}
      unit={of !== undefined ? `of ${of}` : ''}
      bar={false}
      footnote={note}
      spoken={`${value}${of !== undefined ? ` of ${of}` : ''}, a count`}
    />
  )
}

/** The fixed row of at most four key numbers: 2 × 2 on a phone, four across from 1024 px. */
export function NumberRow({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">{children}</div>
}
