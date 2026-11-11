import type { AssumptionBasis, AssumptionDTO } from '../../lib/api/experience.types'
import { dateTimeWords } from '../../lib/format'
import { ageWords } from '../../lib/lifecycle/quantity'
import { Icon } from '../Icon'
import { BASIS } from './words'

const LINE = { solid: 'border-solid', dashed: 'border-dashed', dotted: 'border-dotted', double: 'border-double border-[3px]' } as const

/**
 * Where a value came from: You, Published, Live or Default. Said in words,
 * with its own glyph and its own border style, so it never rests on colour.
 */
export function BasisTag({ basis }: { basis: AssumptionBasis }) {
  const b = BASIS[basis]
  return (
    <span
      title={b.means}
      data-basis={basis}
      className={`inline-flex h-6 shrink-0 items-center gap-1 rounded-pill border border-ink-3 px-2 text-tag font-semibold tracking-caps-md text-ink uppercase ${LINE[b.line]}`}
    >
      <Icon name={b.icon} size={12} strokeWidth={2.2} />
      <span>{b.word}</span>
    </span>
  )
}

/** A live value's source and when it was fetched; a default's precedent. */
export function AssumptionBasisNote({ a }: { a: AssumptionDTO }) {
  const fetched = a.source?.fetched_at ? Date.parse(a.source.fetched_at) : null
  const hasFetched = fetched !== null && !Number.isNaN(fetched)
  if (!a.note && !a.source) return null
  return (
    <span className="flex flex-col gap-0.5 text-caption leading-caption text-ink-3">
      {a.note && <span>{a.note}</span>}
      {a.source && (
        <span>
          Source:{' '}
          {a.source.url ? (
            <a href={a.source.url} target="_blank" rel="noreferrer">
              {a.source.name}
            </a>
          ) : (
            a.source.name
          )}
          {hasFetched && (
            <>
              , fetched <span title={dateTimeWords(fetched as number)}>{ageWords(fetched as number)}</span>
            </>
          )}
        </span>
      )}
    </span>
  )
}

/** The assumptions as a list: label, value, basis, and the basis in words. */
export function AssumptionList({ items, className = '' }: { items: AssumptionDTO[]; className?: string }) {
  return (
    <ul className={`flex flex-col divide-y divide-line border-y border-line ${className}`}>
      {items.map((a) => (
        <li key={a.field} className="flex flex-col gap-1 py-2.5 sm:grid sm:grid-cols-[minmax(0,12rem)_1fr] sm:gap-x-4">
          <span className="text-small text-ink-3">{a.label}</span>
          <span className="flex min-w-0 flex-col gap-1">
            <span className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
              <span className="text-body font-semibold text-ink">{a.display}</span>
              <BasisTag basis={a.basis} />
            </span>
            <AssumptionBasisNote a={a} />
          </span>
        </li>
      ))}
    </ul>
  )
}
