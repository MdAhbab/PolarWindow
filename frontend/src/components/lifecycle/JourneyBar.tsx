import { Link } from 'react-router-dom'
import type { SectionId, SectionState, SectionStatusDTO } from '../../lib/api/lifecycle'
import { Icon, type IconName } from '../Icon'

/** The six steps, in the order a mission lives them. */
export const SECTIONS: { id: SectionId; name: string }[] = [
  { id: 'ready', name: 'Ready' },
  { id: 'launch', name: 'Launch' },
  { id: 'trip', name: 'Trip' },
  { id: 'landing', name: 'Landing' },
  { id: 'contact', name: 'Contact' },
  { id: 'return', name: 'Return' },
]

/** A step's state: a shape and words, never colour alone (invariant 4). */
export const STATE_WORDS: Record<SectionState, { icon: IconName; words: string }> = {
  available: { icon: 'dot', words: 'Available' },
  computing: { icon: 'quarter', words: 'Working it out' },
  needs_input: { icon: 'pencil', words: 'Needs input' },
  not_applicable: { icon: 'dash', words: 'Does not apply' },
  no_data: { icon: 'ring', words: 'No data yet' },
}

export function sectionPath(missionId: string, section: SectionId): string {
  return `/missions/${encodeURIComponent(missionId)}/${section}`
}

/**
 * The mission's six steps, one link each. Each shows its state and the
 * server's one-sentence summary, and nothing else: the numbers are in the
 * section. The open one is marked for assistive technology
 * (`aria-current="page"`) and on screen by an ink bar, the panel ground and
 * ink text; not amber, which means sunlight.
 */
export function JourneyBar({
  missionId,
  current,
  statuses,
  loading,
  problem,
}: {
  missionId: string
  current: SectionId
  statuses: SectionStatusDTO[] | undefined
  loading: boolean
  /** Why the summaries are missing, when `/sections` failed. */
  problem?: string
}) {
  const byId = new Map(statuses?.map((s) => [s.section, s]))
  return (
    <nav aria-label="Mission sections" data-guide="journey" className="flex flex-col gap-2">
      <ol className="grid grid-cols-3 gap-px border border-line bg-line lg:grid-cols-6">
        {SECTIONS.map((s, i) => {
          const status = byId.get(s.id)
          const state = status ? STATE_WORDS[status.state] : null
          const active = s.id === current
          return (
            <li key={s.id} className="flex min-w-0">
              <Link
                to={sectionPath(missionId, s.id)}
                aria-current={active ? 'page' : undefined}
                className={`flex min-h-12 w-full min-w-0 flex-col gap-1 border-t-[3px] px-3 pt-2 pb-2.5 no-underline transition-colors ${
                  active ? 'border-ink bg-panel text-ink' : 'border-transparent bg-canvas text-ink-2 hover:bg-inset hover:text-ink'
                }`}
              >
                <span className="flex items-baseline gap-2 text-tag font-semibold tracking-caps-md uppercase">
                  <span className="font-mono text-ink-3">{i + 1}</span>
                  <span className={active ? 'text-ink' : ''}>{s.name}</span>
                </span>
                {state ? (
                  <span className="flex min-w-0 items-start gap-1.5 text-caption leading-caption text-ink-2">
                    <Icon name={state.icon} size={14} strokeWidth={2} className="mt-0.5 shrink-0" />
                    <span>{state.words}</span>
                    <span className="sr-only">.</span>
                  </span>
                ) : (
                  <span className="text-caption leading-caption text-line-strong" aria-hidden={loading ? 'true' : undefined}>
                    {loading ? '…' : ''}
                  </span>
                )}
                {status?.summary && (
                  <>
                    {/* Kept for screen readers on a phone, where the step itself repeats it as its answer. */}
                    <span className="sr-only md:hidden">{status.summary}</span>
                    <span className="hidden text-caption leading-caption text-ink-3 md:line-clamp-2">{status.summary}</span>
                  </>
                )}
              </Link>
            </li>
          )
        })}
      </ol>
      {problem && <p className="text-caption leading-caption text-ink-3">Step summaries are not available: {problem}</p>}
    </nav>
  )
}
