import { Link } from 'react-router-dom'
import { useTransitionClick } from '../../lib/viewTransition'
import type { SectionId, SectionState, SectionStatusDTO } from '../../lib/api/lifecycle'
import { useMotionClass } from '../../hooks/useMotion'
import { Icon, type IconName } from '../Icon'
import { Skeleton } from '../States'

/**
 * The six steps, in the order a mission lives them. `slug` is the address;
 * the service calls the fourth `landing`, and the screen calls it Surface,
 * since it answers for the time on the surface after landing.
 */
export const SECTIONS: { id: SectionId; slug: string; name: string; question: string }[] = [
  { id: 'ready', slug: 'ready', name: 'Ready', question: 'What is ready, and what is holding it up?' },
  { id: 'launch', slug: 'launch', name: 'Launch', question: 'When and from where can it launch?' },
  { id: 'trip', slug: 'trip', name: 'Trip', question: 'What does the lander go through on the way?' },
  {
    id: 'landing',
    slug: 'surface',
    name: 'Surface',
    question: 'How much sunlight and contact with Earth does it get on the surface?',
  },
  { id: 'contact', slug: 'contact', name: 'Contact', question: 'How often can the lander talk to Earth?' },
  {
    id: 'return',
    slug: 'return',
    name: 'Return',
    question: 'Where do the booster and any capsule come down, and what is the sea like there?',
  },
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
  const slug = SECTIONS.find((s) => s.id === section)?.slug ?? section
  return `/missions/${encodeURIComponent(missionId)}/${slug}`
}

/** A step's state as glyph and words, or a quiet placeholder while it loads. */
function StateLine({ status, loading, className = '' }: { status?: SectionStatusDTO; loading: boolean; className?: string }) {
  const state = status ? STATE_WORDS[status.state] : null
  if (!state) {
    return loading ? (
      <Skeleton className="h-4 w-20" />
    ) : (
      <span className={`text-caption text-ink-3 ${className}`}>Not known</span>
    )
  }
  return (
    <span className={`flex min-w-0 items-center gap-1.5 text-caption leading-caption ${className}`}>
      <Icon name={state.icon} size={14} strokeWidth={2} className="shrink-0" />
      <span>{state.words}</span>
      <span className="sr-only">.</span>
    </span>
  )
}

/**
 * The step bar on a step's page: six links, the open one marked in ink (a bar
 * on top, the panel ground) and for assistive technology (`aria-current`).
 * The mark slides to the step pressed (a view transition), so the move reads
 * as one page changing its tab. Each step says its state in words; the
 * summary is for screen readers here, since the hub shows it in full.
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
  const go = useTransitionClick()
  return (
    <nav aria-label="Mission sections" data-guide="journey" className="flex flex-col gap-2">
      <ol className="grid grid-cols-3 gap-px border border-line bg-line md:grid-cols-6">
        {SECTIONS.map((s, i) => {
          const status = byId.get(s.id)
          const active = s.id === current
          return (
            <li key={s.id} className="flex min-w-0">
              <Link
                to={sectionPath(missionId, s.id)}
                onClick={go(sectionPath(missionId, s.id))}
                aria-current={active ? 'page' : undefined}
                className={`relative flex min-h-14 w-full min-w-0 flex-col justify-center gap-1 px-3 py-2 no-underline transition-colors duration-[var(--pw-dur-quick)] ${
                  active ? 'bg-panel text-ink' : 'bg-canvas text-ink-2 hover:bg-inset hover:text-ink'
                }`}
              >
                {active && (
                  <span
                    aria-hidden="true"
                    className="absolute inset-x-0 top-0 h-[3px] bg-ink"
                    style={{ viewTransitionName: 'pw-step-mark' }}
                  />
                )}
                <span className="flex items-baseline gap-2 text-body font-semibold">
                  <span className="font-mono text-caption font-medium text-ink-3">{i + 1}</span>
                  <span>{s.name}</span>
                </span>
                <StateLine status={status} loading={loading} className={active ? 'text-ink-2' : 'text-ink-3'} />
                {status?.summary && <span className="sr-only">{status.summary}</span>}
              </Link>
            </li>
          )
        })}
      </ol>
      {problem && <p className="text-caption leading-caption text-ink-3">Step summaries are not available: {problem}</p>}
    </nav>
  )
}

/**
 * The mission's home: its six steps as cards, each with the question it
 * answers, its state in glyph and words, and the service's one-sentence
 * summary, in full. The whole card is one link.
 */
export function StepCards({
  missionId,
  statuses,
  loading,
  problem,
}: {
  missionId: string
  statuses: SectionStatusDTO[] | undefined
  loading: boolean
  problem?: string
}) {
  const byId = new Map(statuses?.map((s) => [s.section, s]))
  const arrive = useMotionClass('pw-arrive')
  const go = useTransitionClick()
  return (
    <nav aria-label="Mission sections" data-guide="journey" className="flex flex-col gap-3">
      <ol className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {SECTIONS.map((s, i) => {
          const status = byId.get(s.id)
          return (
            <li
              key={s.id}
              className={`flex min-w-0 ${arrive}`}
              style={arrive ? { animationDelay: `${i * 40}ms` } : undefined}
            >
              <Link
                to={sectionPath(missionId, s.id)}
                onClick={go(sectionPath(missionId, s.id))}
                className="group flex w-full min-w-0 flex-col gap-3 border border-line bg-panel p-5 no-underline shadow-rest transition-[border-color,box-shadow,transform] duration-[var(--pw-dur-base)] ease-[var(--ease-settle)] hover:-translate-y-0.5 hover:border-line-strong hover:shadow-lift"
              >
                <span className="flex items-center justify-between gap-3">
                  <span className="flex items-baseline gap-2.5">
                    <span className="font-mono text-small text-ink-3">{i + 1}</span>
                    <span className="text-title-lg font-semibold text-ink">{s.name}</span>
                  </span>
                  <Icon
                    name="arrow"
                    size={18}
                    strokeWidth={1.8}
                    className="shrink-0 text-ink-3 transition-transform duration-[var(--pw-dur-base)] ease-[var(--ease-settle)] group-hover:translate-x-1 group-hover:text-ink"
                  />
                </span>
                <span className="text-small leading-5 text-ink-3">{s.question}</span>
                <StateLine status={status} loading={loading} className="text-ink" />
                {status?.summary ? (
                  <span className="text-body leading-6 text-ink-2">{status.summary}</span>
                ) : loading ? (
                  <span className="flex flex-col gap-1.5">
                    <Skeleton className="h-4 w-full" />
                    <Skeleton className="h-4 w-2/3" />
                  </span>
                ) : null}
              </Link>
            </li>
          )
        })}
      </ol>
      {problem && <p className="text-caption leading-caption text-ink-3">Step summaries are not available: {problem}</p>}
    </nav>
  )
}
