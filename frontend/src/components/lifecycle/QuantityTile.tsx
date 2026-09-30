import { Children, cloneElement, Fragment, isValidElement, type ReactNode } from 'react'
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
/** The tile's lines as one footnote: a line that runs into the next ends with a full stop. */
function sentences(lines: string[]): string {
  return lines.map((l, i) => (i < lines.length - 1 && !/[.!?:]$/.test(l) ? `${l}.` : l)).join(' ')
}

export function QuantityTile({
  term,
  q,
  tone = 'neutral',
  scale,
  note,
  age,
  inRow = true,
  icon,
  sameReasonAs,
}: {
  /**
   * Set by `NumberRow` when a tile before this one in the row gives the same
   * reason for having no margin: the reason is said once, and this tile points
   * to it instead of repeating it.
   */
  sameReasonAs?: string
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
  // "From TLI …" becomes "from TLI …", but an acronym that opens the reason ("TLI to …") keeps its case.
  const lower = (t: string) => (/^[A-Z]{2}/.test(t) ? t : t.charAt(0).toLowerCase() + t.slice(1))
  const as = sameReasonAs ? `${sameReasonAs.charAt(0).toLowerCase()}${sameReasonAs.slice(1)}` : ''
  const noMargin = v.noMarginReason
    ? sameReasonAs
      ? `No margin, for the same reason as ${as}`
      : `No margin: ${lower(v.noMarginReason)}`
    : undefined
  const missingLine = v.missingReason && sameReasonAs ? `Not known, for the same reason as ${as}` : v.missingReason
  const lines = [note, noMargin, missingLine].filter(Boolean)
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
      footnote={lines.length ? sentences(lines as string[]) : undefined}
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

/**
 * The fixed row of at most four key numbers: 2 × 2 on a phone, four across
 * from 1024 px. A reason for having no margin, or no number, that two tiles
 * share is said once, under the first.
 */
export function NumberRow({ children }: { children: ReactNode }) {
  const seen = new Map<string, string>()
  // Tiles often come in fragments (`<>{a}{b}</>`): flatten them so each is seen.
  const flat = (nodes: ReactNode): ReactNode[] =>
    Children.toArray(nodes).flatMap((n) =>
      isValidElement<{ children?: ReactNode }>(n) && n.type === Fragment ? flat(n.props.children) : [n],
    )
  const tiles = flat(children).map((child) => {
    if (!isValidElement<Parameters<typeof QuantityTile>[0]>(child) || child.type !== QuantityTile) return child
    const q = child.props.q
    const reason = q?.no_margin_reason ?? (q && q.value === null ? q.missing_reason : null)
    if (!reason) return child
    const first = seen.get(reason)
    if (first === undefined) {
      seen.set(reason, termLabel(child.props.term).label)
      return child
    }
    return cloneElement(child, { sameReasonAs: first })
  })
  // Keys by place: a flattened fragment's own keys can repeat another's.
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {tiles.map((t, i) => (isValidElement(t) ? cloneElement(t, { key: i }) : t))}
    </div>
  )
}
