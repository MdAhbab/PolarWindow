import { useId, type ReactNode } from 'react'
import type { JobRefDTO, LifecycleMetaDTO, SectionDTO, SectionStatusDTO } from '../../lib/api/lifecycle'
import { ApiError } from '../../lib/api/client'
import { STATE_WORDS } from './JourneyBar'
import type { SectionView } from '../../lib/api/lifecycleQueries'
import { useMission } from '../../lib/store'
import { dateTimeWords } from '../../lib/format'
import { ageWords, hostWords } from '../../lib/lifecycle/quantity'
import { Icon, type IconName } from '../Icon'
import { ProblemPanel, ProgressTrack, Skeleton, UncertaintyNote } from '../States'
import { useMotionClass } from '../../hooks/useMotion'
import { Button, Disclosure, Panel, RowGroup, SectionLabel } from '../ui'
import { NumberRow } from './QuantityTile'
import { KeyNumberTile } from '../KeyNumbers'
import { termLabel } from '../../lib/format'

/**
 * The one shape every lifecycle section has (design-lifecycle.md §2):
 *
 *   1. the question, and one sentence that answers it;
 *   2. at most four key numbers, always in the same row;
 *   3. one chart with its table twin;
 *   4. everything else in closed rows.
 *
 * Learn it once on one section and the other five read the same way.
 */
export function SectionLayout({ question, children }: { question: string; children: ReactNode }) {
  const id = useId()
  return (
    <section aria-labelledby={id} className="flex w-full min-w-0 flex-col gap-6">
      <h2 id={id} className="text-body font-semibold text-ink-3">
        {question}
      </h2>
      {children}
    </section>
  )
}

/**
 * The answer: one plain sentence, and how old it is. Counts and quantities,
 * never a verdict (invariant 9). It arrives with a short rise, never from
 * invisible, so it can be read at once.
 */
export function Answer({ children, meta, extra }: { children: ReactNode; meta?: LifecycleMetaDTO; extra?: ReactNode }) {
  const at = meta ? Date.parse(meta.computed_at) : NaN
  const arrive = useMotionClass('pw-arrive')
  return (
    <div className={`-mt-4 flex flex-col gap-2 ${arrive}`}>
      {/* The answer, and at most a line more that qualifies it: one block for the guide and the tests. */}
      <div data-guide="section-answer" className="flex max-w-4xl flex-col gap-1.5">
        <p className="text-title-lg leading-7 font-medium text-ink sm:text-subhead sm:leading-8">{children}</p>
        {extra && <p className="text-body leading-6 text-ink-2">{extra}</p>}
      </div>
      {meta && !Number.isNaN(at) && (
        <p className="text-caption text-ink-3">
          <span title={dateTimeWords(at)}>Worked out {ageWords(at)}</span>
        </p>
      )}
      {meta?.stale && (
        <UncertaintyNote title="Some of the data behind this is out of date">
          A number past its limit is replaced by the reason there is no number. The age of each live number is shown
          beside it.
        </UncertaintyNote>
      )}
    </div>
  )
}

/** The section's key numbers while its answer is still coming: labels, no values. */
export function PendingNumbers({ terms }: { terms: string[] }) {
  return (
    <NumberRow>
      {terms.map((t) => {
        const l = termLabel(t)
        return <KeyNumberTile key={t} label={l.label} value={0} unit="" state="computing" inRow />
      })}
    </NumberRow>
  )
}

/**
 * Loading, working it out (a 202 job) and failure, drawn the same on every
 * section; `children` draws the answer.
 */
export function SectionStates<T>({
  view,
  terms,
  status,
  children,
}: {
  view: SectionView<T>
  /** The key numbers' terms, so their labels show while the answer comes. */
  terms: string[]
  /** This step's own status, from the step bar: it names why there is no answer. */
  status?: SectionStatusDTO
  children: (section: SectionDTO<T>) => ReactNode
}) {
  if (view.status === 'answer') return <>{children(view.section)}</>
  if (view.status === 'error') {
    // A refusal the step's status already explains (nothing entered yet, does
    // not apply to this mission, no data) is that state, not a failure.
    const refused = view.error instanceof ApiError && (view.error.status === 404 || view.error.status === 409)
    if (refused && status && status.state !== 'available' && status.state !== 'computing') {
      const w = STATE_WORDS[status.state]
      return (
        <StatePanel
          icon={w.icon}
          title={w.words}
          detail={status.summary}
          stillWorks="The other steps are unaffected; each answers on its own."
        />
      )
    }
    // A 404 with no problem of its own: this server does not answer this step yet.
    if (view.error instanceof ApiError && view.error.status === 404 && !view.error.problem) {
      return (
        <StatePanel
          icon="ring"
          title="Not served yet"
          detail="The service running here does not answer this step yet."
          stillWorks="Landing and the steps it does answer work as usual."
        />
      )
    }
    return <ProblemPanel error={view.error} fallbackTitle="This section could not be loaded" onRetry={view.retry} />
  }
  return (
    <>
      {view.status === 'working' ? (
        <WorkingPanel job={view.job} />
      ) : (
        <div className="-mt-4 flex flex-col gap-2" aria-hidden="true">
          <Skeleton className="h-7 w-full max-w-3xl" />
          <Skeleton className="h-7 w-1/2 max-w-md" />
          <Skeleton className="mt-1 h-4 w-28" />
        </div>
      )}
      <span className="sr-only" role="status">
        {view.status === 'working' ? '' : 'Loading this step'}
      </span>
      <PendingNumbers terms={terms} />
      <Skeleton className="h-64" />
    </>
  )
}

/**
 * A 202: the answer is being worked out. Real progress when the service gives
 * a figure, a moving band while it has none (still under reduced motion), and
 * the service's own words for what it is doing.
 */
export function WorkingPanel({ job }: { job: JobRefDTO }) {
  const pct = job.progress === null ? null : Math.round(job.progress * 100)
  return (
    <Panel className="-mt-4 flex flex-col gap-3 p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div className="flex items-center gap-2 text-control font-semibold text-ink">
          <Icon name="quarter" size={18} />
          {job.status === 'queued' ? 'Waiting its turn to be worked out' : 'Working it out'}
        </div>
        {pct !== null && <span className="font-mono text-small text-ink-2 tnum">{pct}%</span>}
      </div>
      <p className="text-body text-ink-2">{job.message}</p>
      <ProgressTrack
        label="Progress"
        max={100}
        now={pct ?? undefined}
        fraction={pct === null ? null : pct / 100}
        valueText={pct === null ? 'Not started yet' : `${pct} percent`}
      />
      <p className="text-small leading-5 text-ink-3">
        This page updates itself when the answer is ready. The other steps are unaffected.
      </p>
    </Panel>
  )
}

/**
 * The states that are answers too: needs input, does not apply, no data yet.
 * Each says what is missing and what still works.
 */
export function StatePanel({
  icon,
  title,
  detail,
  stillWorks,
  action,
}: {
  icon: IconName
  title: string
  detail: ReactNode
  stillWorks?: ReactNode
  action?: ReactNode
}) {
  return (
    <Panel className="-mt-4 flex flex-col gap-3 p-5">
      <div className="flex items-center gap-2 text-title font-semibold text-ink">
        <Icon name={icon} size={18} />
        {title}
      </div>
      <div className="max-w-3xl text-body leading-6 text-ink-2">{detail}</div>
      {stillWorks && (
        <div className="flex flex-col gap-1 border-l-2 border-line-strong pl-3">
          <SectionLabel as="h3">What still works</SectionLabel>
          <p className="text-small leading-5 text-ink-2">{stillWorks}</p>
        </div>
      )}
      {action && <div className="flex flex-wrap gap-3">{action}</div>}
    </Panel>
  )
}

/**
 * The one chart and its table twin (invariant 5). The table is drawn from the
 * same array as the chart, below it, by the button or the T key.
 */
export function ChartPanel({
  title,
  chart,
  table,
  legend,
  guide,
}: {
  title: string
  chart: ReactNode
  table: ReactNode
  legend?: ReactNode
  guide?: string
}) {
  const showTable = useMission((s) => s.tableOpen)
  const toggle = useMission((s) => s.toggleTable)
  const id = useId()
  const reveal = useMotionClass('pw-chart-reveal')
  const drop = useMotionClass('pw-arrive')
  return (
    <Panel as="section" guide={guide} className="flex min-w-0 flex-col gap-4 p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SectionLabel as="h3" id={`${id}-h`}>
          {title}
        </SectionLabel>
        <Button size="sm" onClick={toggle} expanded={showTable} controls={`${id}-table`} title="Or press T">
          <Icon name="table" size={16} strokeWidth={1.7} />
          {showTable ? 'Hide the table' : 'Read the chart as a table'}
        </Button>
      </div>
      <div className={`min-w-0 ${reveal}`}>{chart}</div>
      {legend}
      <div id={`${id}-table`} hidden={!showTable} className={showTable ? drop : ''}>
        {showTable && table}
      </div>
    </Panel>
  )
}

/** A key under a chart: each swatch beside its words. */
export function Legend({ items }: { items: { swatch: ReactNode; label: string }[] }) {
  return (
    <ul className="flex flex-wrap gap-x-5 gap-y-2 text-caption text-ink-2">
      {items.map((i) => (
        <li key={i.label} className="flex items-center gap-2">
          <span aria-hidden="true" className="flex">
            {i.swatch}
          </span>
          {i.label}
        </li>
      ))}
    </ul>
  )
}

/** Each source of error in a number, by name, with what it means (the service's `meta.uncertainty.parts`). */
export function UncertaintyParts({ parts, small }: { parts: LifecycleMetaDTO['uncertainty']['parts']; small?: boolean }) {
  return (
    <dl className="flex flex-col gap-3">
      {parts.map((p) => (
        <div key={p.source} className="flex flex-col gap-0.5">
          <dt className={`${small ? 'text-small' : 'text-body'} font-semibold text-ink`}>{p.source}</dt>
          <dd className={`${small ? 'text-small leading-5' : 'text-body leading-6'} text-ink-2`}>{p.note}</dd>
        </div>
      ))}
    </dl>
  )
}

/**
 * "How this was worked out": each source of error in the answer in plain
 * words, the section's own method notes, and when and with what it was
 * worked out.
 */
export function HowSure({ meta, children }: { meta: LifecycleMetaDTO; children?: ReactNode }) {
  const parts = meta.uncertainty.parts
  const at = Date.parse(meta.computed_at)
  const engines = Object.entries(meta.engines)
  return (
    <Disclosure
      title="How this was worked out"
      meta={parts.length ? `${parts.length} source${parts.length === 1 ? '' : 's'} of error` : undefined}
    >
      {parts.length ? (
        <UncertaintyParts parts={parts} />
      ) : (
        <p className="text-body text-ink-2">Each number’s own margin is shown beside it.</p>
      )}
      {children}
      <p className="text-caption leading-caption text-ink-3">
        Worked out {Number.isNaN(at) ? '' : dateTimeWords(at)}
        {meta.compute_ms !== null ? ` in ${(meta.compute_ms / 1000).toFixed(1)} s` : ''}
        {engines.length ? '. Calculation versions: ' : '.'}
        {engines.length > 0 && <span className="font-mono">{engines.map(([k, v]) => `${k} ${v}`).join(', ')}</span>}
      </p>
    </Disclosure>
  )
}

/** "Sources": each one with its issue time, age and licence (invariants 10, 11). */
export function SourcesRow({ meta, children }: { meta: LifecycleMetaDTO; children?: ReactNode }) {
  return (
    <Disclosure title="Sources" meta={`${meta.sources.length} source${meta.sources.length === 1 ? '' : 's'}`}>
      {meta.sources.length > 0 ? (
        <ul className="flex flex-col gap-3">
          {meta.sources.map((s, i) => {
            const fetched = s.fetched_at ? Date.parse(s.fetched_at) : null
            const issued = s.issued_at ? Date.parse(s.issued_at) : null
            return (
              // One record can be cited at several pages, so the name alone is not a key.
              <li key={`${s.name}-${s.snapshot_id ?? ''}-${s.url ?? i}`} className="flex flex-col gap-0.5 text-body leading-5">
                {s.url ? (
                  <a href={s.url} target="_blank" rel="noreferrer">
                    {s.name}
                  </a>
                ) : (
                  <span className="text-ink">{s.name}</span>
                )}
                <span className="text-caption leading-caption text-ink-3">
                  {[
                    issued !== null ? `issued ${dateTimeWords(issued)}` : null,
                    fetched !== null ? `fetched ${ageWords(fetched)}` : null,
                    s.licence ? `licence ${s.licence}` : null,
                    s.url ? hostWords(s.url) : null,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              </li>
            )
          })}
        </ul>
      ) : (
        <p className="text-body text-ink-2">Worked out by POLAR WINDOW from the inputs listed under each number.</p>
      )}
      {children}
    </Disclosure>
  )
}

/**
 * The closed rows under a section: its own rows as "Details", then how it
 * was worked out and its sources, always last and always in that order.
 * Sections pass their rows as children and the two fixed rows as `about`.
 */
export function Rows({ children, about }: { children?: ReactNode; about?: ReactNode }) {
  return (
    <div className="flex flex-col gap-6">
      {children && <RowGroup title="Details">{children}</RowGroup>}
      {about && <RowGroup title="About these numbers">{about}</RowGroup>}
    </div>
  )
}
