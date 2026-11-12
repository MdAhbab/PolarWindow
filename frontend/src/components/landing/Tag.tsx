/**
 * Where a figure comes from, drawn as the dashboard draws it
 * (components/surface/parts.tsx, ProvTag) and worded as the glossary has it:
 * worked out, published, entered by your team, assumed. The shape tells them
 * apart without colour: an assumed value wears the dashed scenario hatch
 * (.pw-scenario), an entered one an outline, a published one a dotted
 * underline, a worked-out one nothing extra.
 */
export type TagKind = 'worked out' | 'published' | 'entered by your team' | 'assumed'

export const TAGS: Record<TagKind, { shape: string; means: string }> = {
  'worked out': { shape: '', means: 'Worked out by this service from the data and the figures given' },
  published: { shape: 'underline decoration-dotted underline-offset-2', means: 'Published by the source linked beside it' },
  'entered by your team': { shape: 'rounded-sm border border-ink-2 px-1 text-ink-2', means: 'Typed in by your team' },
  assumed: { shape: 'pw-scenario rounded-sm px-1', means: 'Assumed: not a published or measured figure' },
}

export function Tag({ kind, className = '' }: { kind: TagKind; className?: string }) {
  return (
    <span
      title={TAGS[kind].means}
      className={`inline-block font-mono text-micro leading-4 tracking-caps-sm whitespace-nowrap text-ink-3 uppercase ${TAGS[kind].shape} ${className}`}
    >
      {kind}
    </span>
  )
}
