import { useEffect, type ReactNode } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { ApiError } from '../../lib/api/client'
import type { ScenarioResultsDTO, ScenarioSection } from '../../lib/api/experience.types'
import type { SectionDTO } from '../../lib/api/lifecycle'
import { useScenario } from '../../lib/api/scenarios'
import { useMissions } from '../../lib/api/queries'
import { SectionLayout, StatePanel, UNDER_QUESTION } from '../lifecycle/Section'
import { ProblemPanel, Skeleton } from '../States'
import { ScenarioContext } from './context'
import { ScenarioBand } from './ScenarioBand'
import { ScenarioBuilder } from './ScenarioBuilder'
import { ScenarioProgress } from './ScenarioProgress'
import { useActiveScenario } from './store'
import { STEP_NAME, withScenario } from './words'

/**
 * The worked example that answers this step when the record does not, as the
 * mission list marks it (hatched), or null. Flown and cancelled missions have
 * none, so they always open on their record.
 */
function useFirstExample(missionId: string, section: ScenarioSection): string | null {
  const list = useMissions({})
  const step = list.data?.items.find((m) => m.id === missionId)?.steps?.find((s) => s.section === section)
  return step?.mark === 'example' ? step.scenarioId : null
}

/**
 * Between a step and the mission: with no `?scenario=` it draws the record;
 * `?scenario=new` the builder; `?scenario=<id>` that scenario, its progress
 * and then its answer in the step's own layout. If a link dropped the
 * parameter, the scenario the session was reading is put back. A step the
 * record cannot answer opens on its first worked example, unless the reader
 * asked to see only what is published.
 */
export function ScenarioGate<T>({
  missionId,
  section,
  question,
  record,
  pick,
  children,
}: {
  missionId: string
  section: ScenarioSection
  question: string
  record: ReactNode
  pick: (r: ScenarioResultsDTO) => SectionDTO<T> | undefined
  children: (s: SectionDTO<T>) => ReactNode
}) {
  const [params, setParams] = useSearchParams()
  const sc = params.get('scenario')
  const stored = useActiveScenario((s) => s.active[missionId])
  const recordOnly = useActiveScenario((s) => Boolean(s.recordOnly[missionId]))
  const example = useFirstExample(missionId, section)
  const target = sc ? null : (stored ?? (recordOnly ? null : example))
  const restore = Boolean(target)

  useEffect(() => {
    if (target) {
      setParams(
        (cur) => {
          const n = new URLSearchParams(cur)
          n.set('scenario', target)
          return n
        },
        { replace: true },
      )
    }
  }, [target, setParams])

  if (restore) return null
  if (!sc) return <>{record}</>
  if (sc === 'new') {
    return (
      <ScenarioTitle>
        <SectionLayout question={question} scenario>
          <ScenarioBuilder missionId={missionId} section={section} editFrom={params.get('edit')} />
        </SectionLayout>
      </ScenarioTitle>
    )
  }
  return (
    <ScenarioTitle>
      <ScenarioStep id={sc} missionId={missionId} section={section} question={question} pick={pick}>
        {children}
      </ScenarioStep>
    </ScenarioTitle>
  )
}

/** "Scenario" leads the document title while one is shown, whatever else sets it. */
function ScenarioTitle({ children }: { children: ReactNode }) {
  useEffect(() => {
    const mark = () => {
      if (!/^Scenario:/.test(document.title)) document.title = `Scenario: ${document.title}`.trim()
    }
    mark()
    const el = document.querySelector('title')
    if (!el) return
    const mo = new MutationObserver(mark)
    mo.observe(el, { childList: true, characterData: true, subtree: true })
    return () => {
      mo.disconnect()
      document.title = document.title.replace(/^Scenario:\s*/, '')
    }
  }, [])
  return <>{children}</>
}

function ScenarioStep<T>({
  id,
  missionId,
  section,
  question,
  pick,
  children,
}: {
  id: string
  missionId: string
  section: ScenarioSection
  question: string
  pick: (r: ScenarioResultsDTO) => SectionDTO<T> | undefined
  children: (s: SectionDTO<T>) => ReactNode
}) {
  const loc = useLocation()
  const q = useScenario(id)
  const remember = useActiveScenario((s) => s.remember)
  const showRecord = useActiveScenario((s) => s.showRecord)
  const s = q.data
  const done = s?.status === 'done'
  useEffect(() => {
    if (done) remember(missionId, id)
  }, [done, remember, missionId, id])
  const leave = `${loc.pathname}${withScenario(loc.search, null, { edit: null })}`

  if (q.error) {
    const gone = q.error instanceof ApiError && q.error.status === 404
    return (
      <SectionLayout question={question} scenario>
        {gone ? (
          <StatePanel
            icon="ring"
            title="That scenario is not there"
            detail="It may have been deleted, or the link is for another server."
            action={
              <Link to={leave} onClick={() => showRecord(missionId)} className="inline-flex min-h-11 items-center text-body font-semibold underline">
                Back to the record
              </Link>
            }
          />
        ) : (
          <ProblemPanel error={q.error} fallbackTitle="The scenario could not be loaded" onRetry={() => void q.refetch()} />
        )}
      </SectionLayout>
    )
  }
  if (!s) {
    return (
      <SectionLayout question={question} scenario>
        <div className={`${UNDER_QUESTION} flex flex-col gap-2.5`} aria-busy="true">
          <span className="sr-only" role="status">
            Loading the scenario
          </span>
          <Skeleton className="h-28" />
          <Skeleton className="h-64" />
        </div>
      </SectionLayout>
    )
  }
  const result = s.status === 'done' && s.results ? pick(s.results) : undefined
  const phase = s.phases.find((p) => p.id === section)
  return (
    <ScenarioContext.Provider value={s}>
      <SectionLayout question={question} scenario>
        <ScenarioBand scenario={s} />
        {s.status === 'queued' || s.status === 'running' ? (
          <ScenarioProgress scenario={s} />
        ) : s.status === 'failed' ? (
          <StatePanel
            icon="alert"
            title="This scenario could not be worked out"
            detail={s.error ?? s.message}
            stillWorks="The mission’s record and every other step are unaffected. Change the assumptions to try again."
            action={
              <Link
                to={{ pathname: loc.pathname, search: withScenario(loc.search, 'new', { edit: s.id }) }}
                className="pw-press inline-flex h-12 items-center rounded-pill border border-line-strong bg-tray px-5 text-control font-semibold text-ink no-underline hover:bg-inset"
              >
                Change the assumptions
              </Link>
            }
          />
        ) : result ? (
          <>
            <span className="sr-only" role="status" aria-live="polite">
              The scenario’s answer for {STEP_NAME[section]} is ready.
            </span>
            {s.summaries[section] && <p className="sr-only">{s.summaries[section]}</p>}
            {children(result)}
          </>
        ) : (
          <StatePanel
            icon="dash"
            title={`${STEP_NAME[section]} was left out of this scenario`}
            detail={phase?.detail ?? s.summaries[section] ?? 'These assumptions were not enough to work this step out.'}
            stillWorks="The steps it could support are shown on their own pages."
            action={
              <Link
                to={{ pathname: loc.pathname, search: withScenario(loc.search, 'new', { edit: s.id }) }}
                className="pw-press inline-flex h-12 items-center rounded-pill border border-line-strong bg-tray px-5 text-control font-semibold text-ink no-underline hover:bg-inset"
              >
                Edit assumptions to add what it needs
              </Link>
            }
          />
        )}
      </SectionLayout>
    </ScenarioContext.Provider>
  )
}
