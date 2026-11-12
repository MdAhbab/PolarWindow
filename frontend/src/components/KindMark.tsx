import { ESTIMATES } from '../lib/format'
import { MarkLegend } from './StepStrip'

/** Where a number comes from: the four kinds every number is one of. */
export type NumberKind = 'computed' | 'published' | 'entered' | 'assumed'

export const KIND_WORDS: Record<NumberKind, string> = {
  computed: 'worked out',
  published: 'published',
  entered: 'entered',
  assumed: 'assumed',
}

/**
 * The kind as a small shape and one word: a filled square (worked out), an
 * open square (published), a square with a pencil stroke (entered) and a
 * hatched square (assumed, the same hatch as every assumed value). Shapes,
 * never a hue.
 */
export function KindMark({ kind, words = true }: { kind: NumberKind; words?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1 text-caption leading-caption text-ink-3">
      <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true" className="shrink-0">
        {kind === 'computed' && <rect x="1" y="1" width="8" height="8" rx="1" fill="var(--color-ink-2)" />}
        {kind === 'published' && <rect x="1.5" y="1.5" width="7" height="7" rx="1" fill="none" stroke="var(--color-ink-2)" strokeWidth="1.3" />}
        {kind === 'entered' && (
          <>
            <rect x="1.5" y="1.5" width="7" height="7" rx="1" fill="none" stroke="var(--color-ink-2)" strokeWidth="1.3" />
            <path d="M3 7 7 3" stroke="var(--color-ink-2)" strokeWidth="1.5" strokeLinecap="round" />
          </>
        )}
        {kind === 'assumed' && (
          <>
            <rect x="1.5" y="1.5" width="7" height="7" rx="1" fill="none" stroke="var(--color-ink-2)" strokeWidth="1.1" strokeDasharray="1.6 1" />
            <path d="M2 6 6 2M4 8 8 4" stroke="var(--color-ink-2)" strokeWidth="1" />
          </>
        )}
      </svg>
      {words ? KIND_WORDS[kind] : <span className="sr-only">{KIND_WORDS[kind]}</span>}
    </span>
  )
}

/** The four kinds in one row, for the legend. */
export function KindLegend() {
  return (
    <ul aria-label="What the number marks mean" className="flex flex-wrap gap-x-4 gap-y-1">
      {(Object.keys(KIND_WORDS) as NumberKind[]).map((k) => (
        <li key={k}>
          <KindMark kind={k} />
        </li>
      ))}
    </ul>
  )
}

/**
 * The foot of every page: one closed row with how the numbers are made and
 * what every mark means, in place of notes repeated under each card.
 */
export function SourcesAndMethod() {
  return (
    <details className="group">
      <summary className="inline-flex min-h-11 cursor-pointer list-none items-center gap-2 text-small font-semibold text-ink-2 hover:text-ink [&::-webkit-details-marker]:hidden">
        Sources, method and marks
        <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true" className="pw-turn group-open:rotate-180">
          <path d="M2 4l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </summary>
      <div className="flex flex-col gap-3 pt-2">
        <p>{ESTIMATES}</p>
        <div className="flex flex-col gap-1">
          <p className="font-semibold text-ink-2">Where each number comes from</p>
          <KindLegend />
        </div>
        <div className="flex flex-col gap-1">
          <p className="font-semibold text-ink-2">What each step has</p>
          <MarkLegend />
        </div>
      </div>
    </details>
  )
}
