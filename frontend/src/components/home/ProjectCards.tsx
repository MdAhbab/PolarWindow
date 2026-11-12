import { Link } from 'react-router-dom'
import { useTransitionClick } from '../../lib/viewTransition'
import type { Mission } from '../../lib/api/adapters'
import type { SectionStatusDTO } from '../../lib/api/lifecycle'
import { nextEvent } from '../../lib/api/home'
import { STATUS_LABEL } from '../../lib/missions'
import { Icon } from '../Icon'
import { Skeleton } from '../States'
import { pillClass } from '../ui'
import { STATE_WORDS } from '../lifecycle/JourneyBar'
import { countdownWords, journeySteps } from './model'
import { StepStrip } from '../StepStrip'

/**
 * A project's six steps as a small strip: each step's state as a glyph and
 * its name, the line solid between steps that are available. Shapes and
 * words, never colour alone; the list is read out as "Launch: Needs input".
 */
export function JourneyStrip({ statuses, loading }: { statuses: SectionStatusDTO[] | undefined; loading: boolean }) {
  const steps = journeySteps(statuses)
  if (!statuses && loading) return <Skeleton className="h-10 w-full rounded-control" />
  return (
    <ol aria-label="The six steps" className="grid grid-cols-6">
      {steps.map((s, i) => {
        const w = s.state ? STATE_WORDS[s.state] : null
        const open = s.state === 'needs_input' || s.state === 'no_data'
        const solid = s.state === 'available' && steps[i + 1]?.state === 'available'
        return (
          <li key={s.id} className="relative flex min-w-0 flex-col items-center gap-1" title={`${s.name}: ${w?.words ?? 'not known'}`}>
            {i < steps.length - 1 && (
              <span
                aria-hidden="true"
                className={`absolute top-[11px] left-1/2 h-px w-full ${solid ? 'bg-ink-2' : 'bg-line-strong'}`}
              />
            )}
            <span
              aria-hidden="true"
              className={`relative z-[1] flex size-6 items-center justify-center rounded-pill ${
                s.state === 'available'
                  ? 'bg-ink text-canvas'
                  : open
                    ? 'border-2 border-ink bg-panel text-ink'
                    : 'border border-line-strong bg-panel text-ink-3'
              }`}
            >
              {w ? <Icon name={w.icon} size={12} strokeWidth={2.4} /> : <span className="text-micro">?</span>}
            </span>
            <span aria-hidden="true" className={`max-w-full truncate text-tag leading-4 ${open ? 'font-semibold text-ink' : 'text-ink-3'}`}>
              {s.name}
            </span>
            <span className="sr-only">
              {s.name}: {w?.words ?? 'not known'}
            </span>
          </li>
        )
      })}
    </ol>
  )
}

/** One project: its name, its next dated event with a countdown, and its six steps. */
export function ProjectCard({
  project,
  statuses,
  loading,
  now,
}: {
  project: Mission
  statuses: SectionStatusDTO[] | undefined
  loading: boolean
  now: number
}) {
  const ev = nextEvent(project, now)
  const waiting = statuses?.filter((s) => s.state === 'needs_input' || s.state === 'no_data').length ?? 0
  const go = useTransitionClick()
  const to = `/missions/${encodeURIComponent(project.id)}`
  return (
    <li className="pw-card pw-card-link relative flex min-w-0 flex-col gap-4 p-4 has-[a:focus-visible]:outline-2 has-[a:focus-visible]:outline-offset-[7px] has-[a:focus-visible]:outline-focus sm:p-5">
      <div className="flex min-w-0 flex-col gap-1">
        <h3 className="pw-display truncate text-subhead leading-7 text-ink">
          {/* The whole card is the link: the name is its words, the rest is read after. */}
          {/* The name moves into the mission's header as its page opens (rule 5). */}
          <Link
            to={to}
            onClick={go(to, undefined, 'pw-mission-name')}
            className="no-underline after:absolute after:inset-0 after:rounded-card focus-visible:outline-none"
          >
            {project.name}
          </Link>
        </h3>
        <p className="text-small text-ink-3">
          {STATUS_LABEL[project.status]}
          {project.target ? `, ${project.target.name}` : ', no landing spot yet'}
        </p>
      </div>
      <p className="flex items-baseline gap-2 text-body text-ink-2">
        {ev ? (
          <>
            <Icon name="clocks" size={15} strokeWidth={2} className="shrink-0 self-center text-ink-3" />
            <span>
              <span className="font-semibold text-ink">{countdownWords(ev)}</span>
              {ev.days !== null && <span className="text-ink-3">, {ev.date.asPublished}</span>}
            </span>
          </>
        ) : (
          <span className="text-ink-3">No dated event ahead</span>
        )}
      </p>
      {project.steps?.length ? (
        // Above the card's own link, so each mark opens its step.
        <div className="relative z-[1]">
          <StepStrip mission={project} />
        </div>
      ) : (
        <JourneyStrip statuses={statuses} loading={loading} />
      )}
      {waiting > 0 && (
        <p className="text-small font-semibold text-ink">
          {waiting} {waiting === 1 ? 'step waits' : 'steps wait'} on you
        </p>
      )}
    </li>
  )
}

/** The way in for a new project. */
export function NewProjectCard() {
  return (
    <li className="flex min-h-40 min-w-0">
      <Link
        to="/projects/new"
        className="pw-press flex w-full flex-col items-start justify-center gap-2 rounded-card border border-line-strong bg-tray p-5 text-ink no-underline hover:bg-inset"
      >
        <span className="flex size-10 items-center justify-center rounded-pill bg-ink text-canvas" aria-hidden="true">
          <Icon name="plus" size={18} strokeWidth={2.2} />
        </span>
        <span className="text-control font-semibold">New project</span>
        <span className="text-small text-ink-2">Drop a file, or fill in the form.</span>
      </Link>
    </li>
  )
}

/**
 * No projects yet: the two ways to start, and three CLPS missions to explore
 * in the meantime. In a saved copy, projects cannot be added, and it says so.
 */
export function ProjectsEmpty({ explore, offline }: { explore: Mission[]; offline: boolean }) {
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
      <div className="pw-card flex flex-col gap-4 p-5 sm:p-6">
        <p className="text-title font-semibold text-ink">{offline ? 'Projects need the live service' : 'No projects yet'}</p>
        <p className="max-w-[60ch] text-body leading-6 text-ink-2">
          {offline
            ? 'This is a saved copy: it holds the CLPS missions as published, and nothing can be added to it.'
            : 'Add your mission once and it gets the same six steps as every CLPS mission. Only the name is required; anything you leave empty stays empty and is never guessed.'}
        </p>
        {!offline && (
          <ul className="grid gap-3 sm:grid-cols-2">
            <li>
              <Link to="/projects/new" className={`${pillClass('primary')} w-full justify-start`}>
                <Icon name="file" size={18} strokeWidth={2} />
                Drop a file
              </Link>
              <p className="mt-2 px-1 text-small leading-5 text-ink-3">PDF, Word, text or a table; the form arrives filled, and nothing is saved until you save.</p>
            </li>
            <li>
              <Link to="/projects/new" className={`${pillClass('secondary')} w-full justify-start`}>
                <Icon name="pencil" size={18} strokeWidth={2} />
                Fill in the form
              </Link>
              <p className="mt-2 px-1 text-small leading-5 text-ink-3">Grouped as the journey: mission, landing spot, dates, launch, radio, payloads.</p>
            </li>
          </ul>
        )}
      </div>
      <div className="flex min-w-0 flex-col gap-2">
        <p className="text-body font-semibold text-ink">CLPS missions to explore</p>
        {explore.length ? (
          <ul className="pw-card pw-card-quiet pw-rows flex flex-col">
            {explore.map((m) => (
              <li key={m.id} className="pw-row flex flex-col">
                <Link
                  to={`/missions/${encodeURIComponent(m.id)}`}
                  className="flex min-h-14 items-center gap-3 px-4 py-3 text-ink no-underline hover:bg-inset"
                >
                  <span className="flex min-w-0 grow flex-col">
                    <span className="truncate text-body font-semibold">{m.name}</span>
                    <span className="truncate text-small text-ink-3">
                      {[m.provider, STATUS_LABEL[m.status]].filter(Boolean).join(', ')}
                    </span>
                  </span>
                  <Icon name="chevron" size={16} strokeWidth={2} className="shrink-0 -rotate-90 text-ink-3" />
                </Link>
                <div className="px-3 pb-2">
                  <StepStrip mission={m} />
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <Link to="/missions" className="text-body font-semibold text-ink underline underline-offset-[3px]">
            See every CLPS mission
          </Link>
        )}
      </div>
    </div>
  )
}
