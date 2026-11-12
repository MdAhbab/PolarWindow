import { Link } from 'react-router-dom'
import type { Mission, StepMark, StepMarkKind } from '../lib/api/adapters'
import { SECTIONS, stepHref } from './lifecycle/JourneyBar'
import { MARK_WORDS, MarkIcon } from './MarkIcon'

export { MARK_WORDS, MarkIcon }

/**
 * What each of a mission's six steps has, as six marks in journey order:
 * solid (the mission's own record), hatched (a worked example from assumed
 * values, the same hatch as every assumed value) and hollow (needs input).
 * Shapes, never colours: this is not a traffic light or a score. Each mark
 * opens its step, in the worked example when that is what answers it.
 */

export function StepStrip({ mission }: { mission: Mission }) {
  const steps: StepMark[] = mission.steps ?? []
  if (!steps.length || steps.every((s) => s.mark === 'none')) return null
  return (
    <ul aria-label={`${mission.name}, what each step has`} className="grid max-w-[440px] grid-cols-6">
      {steps.map((s) => {
        const name = SECTIONS.find((x) => x.id === s.section)?.name ?? s.section
        return (
          <li key={s.section} className="min-w-0">
            <Link
              to={stepHref(mission.id, s.section, s.scenarioId)}
              aria-label={`${name}: ${MARK_WORDS[s.mark]}`}
              title={`${name}: ${MARK_WORDS[s.mark]}`}
              className="flex min-h-11 flex-col items-center justify-center gap-1 rounded-control px-0.5 text-tag leading-none text-ink-2 no-underline hover:bg-tray hover:text-ink focus-visible:-outline-offset-2"
            >
              <MarkIcon kind={s.mark} />
              <span className="max-w-full truncate">{name}</span>
            </Link>
          </li>
        )
      })}
    </ul>
  )
}

/** The one legend for the marks, shown wherever they are. */
export function MarkLegend({ className = '' }: { className?: string }) {
  const item = (kind: StepMarkKind, words: string) => (
    <li className="flex items-center gap-1.5">
      <MarkIcon kind={kind} />
      {words}
    </li>
  )
  return (
    <ul aria-label="What the step marks mean" className={`flex flex-wrap gap-x-4 gap-y-1 text-caption text-ink-2 ${className}`}>
      {item('record', 'From the record')}
      {item('example', 'Worked example, assumed values')}
      {item('input', 'Needs your input')}
    </ul>
  )
}

export type HasFilter = 'all' | 'record' | 'example' | 'input'

export const HAS_OPTIONS: { value: HasFilter; label: string }[] = [
  { value: 'all', label: 'Any' },
  { value: 'record', label: 'Full record' },
  { value: 'example', label: 'Worked example' },
  { value: 'input', label: 'Needs input' },
]

export const isHasFilter = (v: string | null): v is HasFilter => HAS_OPTIONS.some((o) => o.value === v)

/**
 * Whether a mission has what the filter asks for. Ready is entered by people
 * and never assumed, so a hollow Ready alone does not count as needing input.
 */
export function hasWhat(m: Mission, has: HasFilter): boolean {
  if (has === 'all') return true
  const s = (m.steps ?? []).filter((x) => x.mark !== 'none')
  if (!s.length) return false
  if (has === 'record') return s.every((x) => x.mark === 'record')
  if (has === 'example') return s.some((x) => x.mark === 'example')
  return s.some((x) => x.mark === 'input' && x.section !== 'ready')
}
