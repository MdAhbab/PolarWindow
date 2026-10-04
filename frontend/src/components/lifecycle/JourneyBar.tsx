import { useMotionClass } from '../../hooks/useMotion'
import { Link } from 'react-router-dom'
import { useTransitionClick } from '../../lib/viewTransition'
import type { SectionId, SectionState, SectionStatusDTO } from '../../lib/api/lifecycle'
import type { MissionStatus } from '../../lib/api/adapters'
import { STATUS_GLYPH, STATUS_LABEL } from '../../lib/missions'
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

/**
 * How far a mission has got, from its published status: the index of the
 * last step it has been through (-1 for none), whether that is where it is
 * now, and the same in words. Never a verdict: only where it is.
 */
export function missionProgress(status: MissionStatus | undefined): { reached: number; now: boolean; words: string } | null {
  if (!status) return null
  const label = STATUS_LABEL[status]
  switch (status) {
    case 'planned':
      return { reached: 0, now: true, words: `${label}: getting ready` }
    case 'in_transit':
      return { reached: 2, now: true, words: `${label}: on the trip` }
    case 'operating':
      return { reached: 3, now: true, words: `${label}: on the surface` }
    case 'completed':
    case 'partial_success':
      return { reached: SECTIONS.length - 1, now: false, words: `${label}: all six steps are behind it` }
    case 'landing_failed':
      return { reached: 2, now: false, words: `${label}: it did not land` }
    case 'lost_before_landing':
      return { reached: 2, now: false, words: `${label}: it was lost on the way` }
    case 'cancelled':
    case 'reassigned':
      return { reached: -1, now: false, words: label }
  }
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
      <span className="truncate">{state.words}</span>
      <span className="sr-only">.</span>
    </span>
  )
}

/**
 * A step's place on the line: its number in a disc, solid once the mission
 * has been through it, outlined ahead of it. The open step (on a step's page)
 * wears a ring that slides to the step pressed (a view transition).
 */
function Node({ n, behind, open }: { n: number; behind: boolean; open: boolean }) {
  return (
    <span
      className={`relative z-[1] flex size-8 shrink-0 items-center justify-center rounded-pill font-mono text-caption font-medium shadow-[0_0_0_4px_var(--color-canvas)] transition-colors duration-[var(--pw-dur-base)] ${
        behind ? 'bg-ink text-canvas' : 'border-2 border-line-strong bg-canvas text-ink-2'
      }`}
    >
      {n}
      {open && (
        <span
          aria-hidden="true"
          className="absolute -inset-[6px] rounded-pill border-2 border-ink"
          style={{ viewTransitionName: 'pw-step-mark' }}
        />
      )}
    </span>
  )
}

/**
 * The stretch of line from one step to the next: ink where the mission has
 * been, a hairline ahead. Drawn from each step's node to the next one's, so
 * it fits any column width and turns to run down the page on a phone.
 */
function Segment({ behind, orient, index }: { behind: boolean; orient: 'row' | 'column' | 'both'; index: number }) {
  const geometry =
    orient === 'row'
      ? 'left-4 top-[15px] h-0.5 w-[calc(100%+1rem)]'
      : orient === 'column'
        ? 'left-[15px] top-4 w-0.5 h-full'
        : 'left-[15px] top-4 w-0.5 h-full lg:left-4 lg:top-[15px] lg:h-0.5 lg:w-[calc(100%+1.25rem)]'
  return (
    <span
      aria-hidden="true"
      data-journey-segment={behind ? 'behind' : 'ahead'}
      data-orient={orient}
      style={{ ['--pw-i' as string]: index }}
      className={`pointer-events-none absolute ${geometry} ${behind ? 'bg-ink' : 'bg-line-strong'}`}
    />
  )
}

/** The tag over the step the mission is on now. Words for a screen reader, a pill for the eye. */
function NowTag() {
  return (
    <>
      <span className="sr-only"> (where it is now)</span>
      <span
        aria-hidden="true"
        className="pw-eyebrow inline-flex h-5 items-center rounded-pill border border-line-strong bg-tray px-2 text-[10px] leading-none tracking-[0.12em] text-ink"
      >
        Now
      </span>
    </>
  )
}

/**
 * The step bar on a step's page: the six steps on one line, the open one
 * ringed in ink and marked for assistive technology (`aria-current`), the
 * line solid as far as the mission has got. Each step says its state in
 * words; the summary is for screen readers here, since the mission's home
 * shows it in full. Six across from 768 px; three by two below, without the
 * line, so a phone keeps the words.
 */
export function JourneyBar({
  missionId,
  current,
  statuses,
  loading,
  problem,
  status,
}: {
  missionId: string
  current: SectionId
  statuses: SectionStatusDTO[] | undefined
  loading: boolean
  /** Why the summaries are missing, when `/sections` failed. */
  problem?: string
  /** The mission's published status, for how far along the line it has got. */
  status?: MissionStatus
}) {
  const byId = new Map(statuses?.map((s) => [s.section, s]))
  const go = useTransitionClick()
  const progress = missionProgress(status)
  const reached = progress?.reached ?? -1
  const draw = useMotionClass('pw-journey-draw')
  return (
    <nav aria-label="Mission sections" data-guide="journey" className={`flex flex-col gap-2 ${draw}`}>
      <ol className={`grid grid-cols-3 gap-x-1.5 min-[360px]:gap-x-3 gap-y-4 md:grid-cols-6 md:gap-x-4 ${progress?.now ? 'md:pt-6' : ''}`}>
        {SECTIONS.map((s, i) => {
          const st = byId.get(s.id)
          const active = s.id === current
          const behind = i <= reached
          return (
            <li key={s.id} className="relative flex min-w-0">
              {i < SECTIONS.length - 1 && (
                <span className="hidden md:contents">
                  <Segment behind={i < reached} orient="row" index={i} />
                </span>
              )}
              <Link
                to={sectionPath(missionId, s.id)}
                onClick={go(sectionPath(missionId, s.id))}
                aria-current={active ? 'page' : undefined}
                className={`group relative flex min-h-12 w-full min-w-0 items-start gap-1.5 min-[360px]:gap-2.5 rounded-control no-underline md:flex-col md:gap-2 ${
                  active ? 'text-ink' : 'text-ink-2 hover:text-ink'
                }`}
              >
                <Node n={i + 1} behind={behind} open={active} />
                <span className="flex min-w-0 flex-col gap-0.5 pt-1 md:pt-0">
                  <span className={`text-body leading-5 ${active ? 'font-semibold' : 'font-medium'}`}>{s.name}</span>
                  <StateLine status={st} loading={loading} className={active ? 'text-ink-2' : 'text-ink-3'} />
                </span>
                {progress?.now && i === reached && (
                  <span className="absolute -top-6 left-0 hidden md:block">
                    <NowTag />
                  </span>
                )}
                {st?.summary && <span className="sr-only">{st.summary}</span>}
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
 * The mission's home: its six steps on one line, each with the question it
 * answers, its state in glyph and words, and the service's one-sentence
 * summary in full. Each step is one link. Across the page from 1024 px; down
 * it below, the line running beside the steps.
 */
export function StepCards({
  missionId,
  statuses,
  loading,
  problem,
  status,
}: {
  missionId: string
  statuses: SectionStatusDTO[] | undefined
  loading: boolean
  problem?: string
  status?: MissionStatus
}) {
  const byId = new Map(statuses?.map((s) => [s.section, s]))
  const go = useTransitionClick()
  const progress = missionProgress(status)
  const reached = progress?.reached ?? -1
  const draw = useMotionClass('pw-journey-draw')
  return (
    <nav aria-label="Mission sections" data-guide="journey" className={`flex flex-col gap-4 ${draw}`}>
      {progress && (
        <p className="flex items-center gap-2 text-small text-ink-2">
          <span aria-hidden="true" className="text-ink">
            {status ? STATUS_GLYPH[status] : ''}
          </span>
          {progress.words}
        </p>
      )}
      <ol className="flex flex-col lg:grid lg:grid-cols-6 lg:gap-x-5 lg:pt-7">
        {SECTIONS.map((s, i) => {
          const st = byId.get(s.id)
          const behind = i <= reached
          return (
            <li key={s.id} className="relative flex min-w-0 pb-6 last:pb-0 lg:pb-0">
              {i < SECTIONS.length - 1 && <Segment behind={i < reached} orient="both" index={i} />}
              <Link
                to={sectionPath(missionId, s.id)}
                onClick={go(sectionPath(missionId, s.id))}
                className="group relative -m-3 flex w-full min-w-0 gap-4 rounded-card p-3 no-underline transition-colors duration-[var(--pw-dur-quick)] hover:bg-tray lg:flex-col lg:gap-3"
              >
                <Node n={i + 1} behind={behind} open={false} />
                <span className="flex min-w-0 grow flex-col gap-2">
                  <span className="flex items-center justify-between gap-3">
                    <span className="text-title-lg font-semibold tracking-title text-ink">{s.name}</span>
                    <Icon
                      name="arrow"
                      size={17}
                      strokeWidth={1.8}
                      className="shrink-0 text-ink-3 opacity-60 transition-[transform,opacity,color] duration-[var(--pw-dur-lift)] ease-[var(--ease-settle)] group-hover:translate-x-1 group-hover:text-ink group-hover:opacity-100"
                    />
                  </span>
                  <span className="text-small leading-5 text-ink-3">{s.question}</span>
                  <StateLine status={st} loading={loading} className="text-ink" />
                  {st?.summary ? (
                    <span className="text-body leading-6 text-ink-2">{st.summary}</span>
                  ) : loading ? (
                    <span className="flex flex-col gap-1.5">
                      <Skeleton className="h-4 w-full" />
                      <Skeleton className="h-4 w-2/3" />
                    </span>
                  ) : null}
                </span>
                {progress?.now && i === reached && (
                  <span className="absolute top-3 right-3 lg:-top-6 lg:right-auto lg:left-3">
                    <NowTag />
                  </span>
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
