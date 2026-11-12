import { useEffect, useId, useRef, useState } from 'react'
import { useMotionClass, useReducedMotion } from '../../hooks/useMotion'
import { useWidth } from '../../hooks/useWidth'
import { Link, useLocation } from 'react-router-dom'
import { useTransitionClick } from '../../lib/viewTransition'
import type { SectionId, SectionState, SectionStatusDTO } from '../../lib/api/lifecycle'
import type { MissionStatus } from '../../lib/api/adapters'
import type { NextEvent } from '../../lib/api/home'
import { STATUS_GLYPH, STATUS_LABEL } from '../../lib/missions'
import { useActiveScenario } from '../scenario/store'
import { Icon, type IconName } from '../Icon'
import { Skeleton } from '../States'
import { CountUp } from '../ui'

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
 * A step's address, keeping the scenario being read (`?scenario=<id>`), so
 * moving between steps does not drop the reader out of it. Ready is entered
 * by people and never assumed, so it always opens on the record.
 */
export function stepHref(missionId: string, section: SectionId, scenario?: string | null): string {
  const base = sectionPath(missionId, section)
  return scenario && section !== 'ready' ? `${base}?scenario=${encodeURIComponent(scenario)}` : base
}

/** The scenario being read in a mission: the address's, or the one kept for the session. */
export function useOpenScenario(missionId: string): string | null {
  const { search } = useLocation()
  const stored = useActiveScenario((s) => s.active[missionId])
  const sc = new URLSearchParams(search).get('scenario')
  if (sc && sc !== 'new') return sc
  return stored ?? null
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
      className={`relative z-[1] flex size-8 shrink-0 items-center justify-center rounded-pill font-mono text-caption font-medium shadow-[0_0_0_4px_var(--color-canvas)] ${
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
      {/* The space is said, not drawn: the tag sits in a flex row, which drops it. */}{' '}
      <span className="sr-only">(where it is now)</span>
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
 * line, so a phone keeps the words. A scenario being read stays open across
 * the steps.
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
  const scenario = useOpenScenario(missionId)
  return (
    <nav aria-label="Mission sections" data-guide="journey" className={`flex flex-col gap-2 ${draw}`}>
      <ol className={`grid grid-cols-3 gap-x-1.5 min-[360px]:gap-x-3 gap-y-4 md:grid-cols-6 md:gap-x-4 ${progress?.now ? 'md:pt-9' : ''}`}>
        {SECTIONS.map((s, i) => {
          const st = byId.get(s.id)
          const active = s.id === current
          const behind = i <= reached
          const href = stepHref(missionId, s.id, scenario)
          return (
            <li key={s.id} className="relative flex min-w-0">
              {i < SECTIONS.length - 1 && (
                <span className="hidden md:contents">
                  <Segment behind={i < reached} orient="row" index={i} />
                </span>
              )}
              <Link
                to={href}
                onClick={go(href)}
                aria-current={active ? 'page' : undefined}
                className={`pw-press group relative flex min-h-12 w-full min-w-0 items-start gap-1.5 min-[360px]:gap-2.5 rounded-control no-underline md:flex-col md:gap-2 ${
                  active ? 'text-ink' : 'text-ink-2 hover:text-ink'
                }`}
              >
                <Node n={i + 1} behind={behind} open={active} />
                <span className="flex min-w-0 flex-col gap-0.5 pt-1 md:pt-0">
                  <span className={`text-body leading-5 ${active ? 'font-semibold' : 'font-medium'}`}>{s.name}</span>
                  <StateLine status={st} loading={loading} className={active ? 'text-ink-2' : 'text-ink-3'} />
                </span>
                {progress?.now && i === reached && (
                  // Clear of the open step's ring, which reaches 6 px above the disc.
                  <span className="absolute -top-9 left-0 hidden md:block">
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

/* ---------------------------------------------------------------------------
   The mission's home: one path from Earth to the Moon with six stops.
   --------------------------------------------------------------------------- */

/** The band the arc is drawn in above the stops, on a journey 56rem wide or more. */
const BAND = 112
/** Where Earth and the Moon sit in it, and how far the arc rises above them. */
const BASE = 84
const LIFT = 58
/** The room either side of the six columns, for Earth and the Moon. */
const PAD = 44
/** Earth's and the Moon's centres, in from the edges. */
const END = 20
/** A stop's mark. */
const MARK = 28

/** The arc's height at `x`: a parabola from Earth (x0) to the Moon (x1), which is what the drawn curve is. */
function arcY(x: number, x0: number, x1: number): number {
  const u = (x - x0) / (x1 - x0)
  return BASE - LIFT * 4 * u * (1 - u)
}

/** Missions whose journey has drawn itself in this visit: it draws once, not on every return. */
const drawnThisVisit = new Set<string>()

/**
 * A stop's mark: its state as a shape. Solid with a dot once there is an
 * answer; an open ring around a quarter (being worked out), a pencil (needs
 * input) or a ring (no data yet); a faint dash where the step does not apply.
 * The same shapes as Home's strip; the words are always beside it.
 */
function StopMark({ state, loading }: { state?: SectionState; loading: boolean }) {
  if (!state) {
    return loading ? (
      <Skeleton className="size-7 rounded-pill" />
    ) : (
      <span className="flex size-7 items-center justify-center rounded-pill border border-line-strong bg-canvas text-caption text-ink-3 shadow-[0_0_0_4px_var(--color-canvas)]">
        ?
      </span>
    )
  }
  const look =
    state === 'available'
      ? 'bg-ink text-canvas'
      : state === 'not_applicable'
        ? 'border border-line-strong bg-canvas text-ink-3'
        : 'border-2 border-ink bg-canvas text-ink'
  return (
    <span className={`flex size-7 items-center justify-center rounded-pill shadow-[0_0_0_4px_var(--color-canvas)] ${look}`}>
      <Icon name={STATE_WORDS[state].icon} size={14} strokeWidth={2.2} />
    </span>
  )
}

/** The next dated event, the days to it counting up once; the date as published when it is vaguer than a day. */
function NextWords({ ev }: { ev: NextEvent }) {
  if (ev.days === null) {
    return (
      <>
        {ev.what}: {ev.date.asPublished}
      </>
    )
  }
  if (ev.days === 0) return <>{ev.what} today</>
  if (ev.days === 1) return <>{ev.what} tomorrow</>
  return (
    <>
      {ev.what} in <CountUp value={ev.days} className="font-semibold text-ink" /> days, on {ev.date.asPublished}
    </>
  )
}

/**
 * The mission's home: its six steps as stops on one path from Earth to the
 * Moon. Each stop says its state twice, as a shape on the path and in words
 * under it, with the question it answers and the service's one-line answer;
 * a step with nothing to show (no data, or input missing) offers a scenario.
 * The path is ink as far as the mission has got and a hairline beyond.
 *
 * Where the journey itself is 56rem wide or more, the path is an arc across
 * it over six columns; narrower, it runs straight down the left with each
 * stop beside it, so a phone keeps every word. The choice is the journey's
 * own width (a container query), not the screen's: with the Ask panel open
 * beside the page on a laptop, the journey goes down the page rather than
 * squeezing six columns. It draws itself once per mission per visit, and
 * not at all under reduced motion.
 */
export function JourneyPath({
  missionId,
  statuses,
  loading,
  problem,
  status,
  target,
  next,
}: {
  missionId: string
  statuses: SectionStatusDTO[] | undefined
  loading: boolean
  problem?: string
  status?: MissionStatus
  /** The landing spot's name, for the Moon's end of the path. */
  target?: string | null
  /** The next dated event, counted down to when it is known to the day. */
  next?: NextEvent | null
}) {
  const byId = new Map(statuses?.map((s) => [s.section, s]))
  const go = useTransitionClick()
  const progress = missionProgress(status)
  const reached = progress?.reached ?? -1
  const scenario = useOpenScenario(missionId)
  const wrap = useRef<HTMLDivElement>(null)
  const w = useWidth(wrap, 1200)
  const reduced = useReducedMotion()
  const [fresh] = useState(() => !drawnThisVisit.has(missionId))
  useEffect(() => {
    drawnThisVisit.add(missionId)
  }, [missionId])
  const animate = fresh && !reduced
  const clipId = `pw-ink-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`

  const x0 = END
  const x1 = Math.max(w - END, x0 + 1)
  const col = (w - 2 * PAD) / SECTIONS.length
  const stops = SECTIONS.map((_, i) => {
    const x = PAD + i * col + MARK / 2
    return { x, y: arcY(x, x0, x1) }
  })
  const finished = Boolean(progress && !progress.now && reached === SECTIONS.length - 1)
  const inkTo = reached < 0 ? 0 : finished ? x1 : stops[reached].x
  const d = `M ${x0} ${BASE} Q ${w / 2} ${BASE - 2 * LIFT} ${x1} ${BASE}`
  // The segments down the page on a phone draw one after another (globals.css, .pw-journey-draw).
  const railDraw = animate ? 'pw-journey-draw' : ''
  const pop = animate ? 'pw-stop-in' : ''

  return (
    <nav aria-label="Mission sections" data-guide="journey" className="@container flex flex-col gap-5">
      {(progress || next) && (
        <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between sm:gap-6">
          {progress && (
            <p className="flex items-center gap-2 text-small text-ink-2">
              <span aria-hidden="true" className="text-ink">
                {status ? STATUS_GLYPH[status] : ''}
              </span>
              {progress.words}
            </p>
          )}
          {next && (
            <p className="flex items-center gap-2 text-small text-ink-2">
              <Icon name="clocks" size={15} strokeWidth={2} className="shrink-0 text-ink-3" />
              <span>
                <NextWords ev={next} />
              </span>
            </p>
          )}
        </div>
      )}
      {scenario && (
        <p className="pw-scenario self-start rounded-control px-3 py-2 text-small leading-5 text-ink-2">
          The steps open in the scenario you were reading. Ready always shows the record.
        </p>
      )}

      <div ref={wrap} className={`relative ${railDraw}`}>
        {/* The arc, on a wide journey: a hairline all the way, ink over it as far as the mission has got. */}
        <svg
          aria-hidden="true"
          width={w}
          height={BAND}
          className={`pointer-events-none absolute top-0 left-0 hidden overflow-visible @4xl:block ${animate ? 'pw-path-draw' : ''}`}
        >
          <defs>
            <clipPath id={clipId}>
              <rect x={0} y={0} width={inkTo} height={BAND} />
            </clipPath>
          </defs>
          <path d={d} fill="none" strokeWidth={1.5} className="stroke-line-strong" />
          {inkTo > 0 && <path d={d} fill="none" strokeWidth={2} clipPath={`url(#${clipId})`} className="stroke-ink" />}
        </svg>
        <Terminal kind="earth" wide={{ left: x0, top: BASE }} inked={reached >= 0} />

        <ol className="relative flex flex-col @4xl:grid @4xl:grid-cols-6 @4xl:px-[44px]">
          {SECTIONS.map((s, i) => {
            const st = byId.get(s.id)
            const here = Boolean(progress?.now && i === reached)
            const href = stepHref(missionId, s.id, scenario)
            const missing = Boolean(st && s.id !== 'ready' && (st.state === 'no_data' || st.state === 'needs_input'))
            const vars = {
              ['--pw-y' as string]: `${stops[i].y}px`,
              ['--pw-at' as string]: `${500 + i * 150}ms`,
              ['--pw-at-lg' as string]: `${Math.round(160 + 720 * (stops[i].x / w))}ms`,
            }
            return (
              <li key={s.id} className="relative flex min-w-0 gap-4 pb-8 @4xl:block @4xl:pr-5 @4xl:pb-0" style={vars}>
                <span aria-hidden="true" className="relative z-[1] flex w-7 shrink-0 justify-center @4xl:absolute @4xl:top-[calc(var(--pw-y)_-_14px)] @4xl:left-0">
                  <span className={`flex ${pop}`}>
                    <StopMark state={st?.state} loading={loading} />
                  </span>
                </span>
                {/* Down the page on a phone: the stretch to the next stop (the last one to the Moon). */}
                <span
                  aria-hidden="true"
                  data-journey-segment={i < reached || (i === SECTIONS.length - 1 && finished) ? 'behind' : 'ahead'}
                  data-orient="column"
                  style={{ ['--pw-i' as string]: i + 1 }}
                  className={`pointer-events-none absolute top-7 bottom-0 left-[13px] w-0.5 @4xl:hidden ${
                    i < reached || (i === SECTIONS.length - 1 && finished) ? 'bg-ink' : 'bg-line-strong'
                  }`}
                />
                <div className="flex min-w-0 grow flex-col items-start gap-2.5 @4xl:pt-[112px]">
                  <Link
                    to={href}
                    onClick={go(href)}
                    className="-mx-2 -my-1.5 flex w-[calc(100%+1rem)] min-w-0 flex-col gap-1.5 pw-press rounded-control px-2 py-1.5 no-underline hover:bg-tray"
                  >
                    <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className="font-mono text-body text-ink-3">{i + 1}</span>{' '}
                      <span className="text-title-lg font-semibold tracking-title text-ink">{s.name}</span>
                      {here && <NowTag />}
                    </span>
                    <span className="text-small leading-5 text-ink-3">{s.question}</span>
                    <StateLine status={st} loading={loading} className="text-ink" />
                    {st?.summary ? (
                      <span className="text-body leading-6 text-ink-2">{st.summary}</span>
                    ) : loading ? (
                      <span className="flex w-full flex-col gap-1.5">
                        <Skeleton className="h-4 w-full" />
                        <Skeleton className="h-4 w-2/3" />
                      </span>
                    ) : null}
                  </Link>
                  {missing && (
                    <Link
                      to={`${sectionPath(missionId, s.id)}?scenario=new`}
                      className="pw-scenario pw-press inline-flex min-h-11 items-center gap-2 rounded-pill px-3.5 text-small font-semibold text-ink no-underline hover:bg-inset"
                    >
                      <Icon name="plus" size={14} strokeWidth={2.2} className="shrink-0" />
                      <span>
                        Explore a scenario{' '}
                        <span className="sr-only">for {s.name}</span>
                      </span>
                    </Link>
                  )}
                </div>
              </li>
            )
          })}
        </ol>

        <Terminal kind="moon" wide={{ left: x1, top: BASE }} inked={finished} target={target} />
      </div>
      {problem && <p className="text-caption leading-caption text-ink-3">Step summaries are not available: {problem}</p>}
    </nav>
  )
}

/**
 * Either end of the path. On a wide journey a glyph on the arc's end with its name
 * under it; below, a row of its own on the line down the page (Earth above
 * the first stop, the Moon and the landing spot below the last).
 */
function Terminal({
  kind,
  wide,
  inked,
  target,
}: {
  kind: 'earth' | 'moon'
  wide: { left: number; top: number }
  inked: boolean
  target?: string | null
}) {
  const earth = kind === 'earth'
  const glyph = (
    <span
      aria-hidden="true"
      className={`flex size-7 items-center justify-center rounded-pill bg-canvas shadow-[0_0_0_4px_var(--color-canvas)] ${earth ? 'text-earth' : 'text-ink-2'}`}
    >
      <Icon name={earth ? 'earth' : 'moon'} size={20} strokeWidth={1.7} />
    </span>
  )
  const name = earth ? 'Earth' : 'The Moon'
  return (
    <>
      <div
        className="pointer-events-none absolute hidden flex-col items-center gap-1 @4xl:flex"
        style={{ left: wide.left - MARK / 2, top: wide.top - MARK / 2, width: MARK }}
      >
        {glyph}
        <span className="text-caption leading-caption whitespace-nowrap text-ink-3">{earth ? 'Earth' : 'Moon'}</span>
      </div>
      <div className={`relative flex items-center gap-4 @4xl:hidden ${earth ? 'pb-8' : ''}`}>
        {glyph}
        <span className="min-w-0 text-small text-ink-3">
          {name}
          {!earth && target ? `, ${target}` : ''}
        </span>
        {earth && (
          <span
            aria-hidden="true"
            data-journey-segment={inked ? 'behind' : 'ahead'}
            data-orient="column"
            style={{ ['--pw-i' as string]: 0 }}
            className={`pointer-events-none absolute top-7 bottom-0 left-[13px] w-0.5 ${inked ? 'bg-ink' : 'bg-line-strong'}`}
          />
        )}
      </div>
    </>
  )
}
