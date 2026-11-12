import type { SectionId } from '../lib/api/lifecycle'
import type { StepMark, StepMarkKind } from '../lib/api/adapters'
import { useMissions } from '../lib/api/queries'

export const MARK_WORDS: Record<StepMarkKind, string> = {
  record: 'from the record',
  example: 'worked example',
  input: 'needs your input',
  none: 'does not apply',
}

/** Three short chords at -45 degrees inside a circle of radius 4.5: the hatch. */
const HATCH = [-2.6, 0, 2.6].map((d) => {
  const h = Math.sqrt(4.5 * 4.5 - d * d)
  const k = Math.SQRT1_2
  // Centre of the chord, offset along (1, 1); the chord runs along (1, -1).
  const cx = d * k
  const cy = d * k
  return { x1: cx - h * k, y1: cy + h * k, x2: cx + h * k, y2: cy - h * k }
})

export function MarkIcon({ kind, size = 14 }: { kind: StepMarkKind; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="-7 -7 14 14" aria-hidden="true" className="shrink-0">
      {kind === 'record' && <circle r="5.5" fill="var(--color-ink)" />}
      {kind === 'example' && (
        <>
          <circle r="5.5" fill="none" stroke="var(--color-ink-2)" strokeWidth="1.3" strokeDasharray="2.2 1.4" />
          {HATCH.map((l, i) => (
            <line key={i} {...l} stroke="var(--color-ink-2)" strokeWidth="1.1" strokeLinecap="round" />
          ))}
        </>
      )}
      {kind === 'input' && <circle r="5" fill="none" stroke="var(--color-ink-2)" strokeWidth="1.5" />}
      {kind === 'none' && <line x1="-4" y1="0" x2="4" y2="0" stroke="var(--color-ink-3)" strokeWidth="1.5" />}
    </svg>
  )
}

/** A mission's six step marks from the mission list (shared cache), by step; empty until it arrives. */
export function useStepMarks(missionId: string): Map<SectionId, StepMark> {
  const list = useMissions({})
  const steps = list.data?.items.find((m) => m.id === missionId)?.steps ?? []
  return new Map(steps.map((s) => [s.section, s]))
}
