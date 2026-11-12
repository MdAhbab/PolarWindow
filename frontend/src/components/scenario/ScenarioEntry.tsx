import { Link, useLocation } from 'react-router-dom'
import { ApiError } from '../../lib/api/client'
import type { ScenarioBriefDTO, ScenarioSection } from '../../lib/api/experience.types'
import { useScenarioGaps } from '../../lib/api/scenarios'
import { useSnapshotActive } from '../../lib/api/snapshot'
import { Icon } from '../Icon'
import { Skeleton } from '../States'
import { PillArrow, pillClass } from '../ui'
import { STEP_NAME, withScenario } from './words'

/** Where a scenario link goes: this step, with its other parameters kept. */
function useScenarioTo() {
  const loc = useLocation()
  return (scenario: string) => ({ pathname: loc.pathname, search: withScenario(loc.search, scenario, { edit: null }) })
}

export const OFFLINE_WORDS =
  'A scenario is worked out by the live service, and this offline copy does not have it. Every other step works as usual.'

/**
 * The way on from a step that has nothing published: what the record lacks, in
 * plain words, one primary action, and the ready-made scenarios that open at
 * once. Sits in the dead-end panel's action slot.
 */
export function ScenarioEntry({ missionId, section }: { missionId: string; section: ScenarioSection }) {
  const offline = useSnapshotActive()
  const gaps = useScenarioGaps(missionId, !offline)
  const to = useScenarioTo()

  if (offline) return <p className="w-full max-w-3xl text-small leading-5 text-ink-3">{OFFLINE_WORDS}</p>
  if (gaps.isPending) return <Skeleton className="h-12 w-56" />
  if (gaps.error || !gaps.data) {
    const why = gaps.error instanceof ApiError && gaps.error.status === 404 ? 'The service running here does not offer scenarios yet.' : 'Scenarios could not be loaded just now.'
    return (
      <p className="w-full max-w-3xl text-small leading-5 text-ink-3">
        {why}{' '}
        {!(gaps.error instanceof ApiError && gaps.error.status === 404) && (
          <button type="button" className="min-h-11 font-semibold text-ink underline" onClick={() => void gaps.refetch()}>
            Try again
          </button>
        )}
      </p>
    )
  }

  const gap = gaps.data.gaps.find((g) => g.section === section)
  const presets = gaps.data.presets.filter((p) => p.sections.includes(section))
  const missing = gap?.missing ?? []
  const can = gap ? gap.can_explore : true

  return (
    <div className="flex w-full min-w-0 flex-col gap-5" data-testid="scenario-entry">
      {missing.length > 0 && (
        <div className="flex max-w-3xl flex-col gap-2 border-l-2 border-line-strong pl-3">
          <h3 className="pw-eyebrow">What the record does not give for {STEP_NAME[section]}</h3>
          <ul className="flex flex-col gap-1.5">
            {missing.map((m) => (
              <li key={m.field} className="text-small leading-5 text-ink-2">
                <span className="font-semibold text-ink">{m.label}</span>: {m.why}
              </li>
            ))}
          </ul>
        </div>
      )}
      {can ? (
        <div className="flex flex-col items-start gap-2">
          <Link to={to('new')} className={pillClass('primary', true)}>
            Explore a scenario
            <PillArrow />
          </Link>
          <p className="max-w-xl text-caption leading-caption text-ink-3">
            Say or set what to assume. The answer is labelled as a scenario and never goes into the mission’s record.
          </p>
        </div>
      ) : (
        // No dead end: what the defaults cannot supply, the reader can choose.
        <div className="flex flex-col items-start gap-2">
          <p className="max-w-3xl text-small leading-5 text-ink-2">
            Nothing published gives {missing.length === 1 ? 'this' : 'these'} yet. Choose{' '}
            {missing.length === 1 ? 'it' : 'them'}, and this step is worked out as a scenario.
          </p>
          <Link to={to('new')} className={pillClass('primary', true)}>
            Choose the {missing.map((m) => m.label.toLowerCase()).join(' and ') || 'assumed values'}
            <PillArrow />
          </Link>
        </div>
      )}
      {can && presets.length > 0 && <PresetCards presets={presets} to={to} />}
    </div>
  )
}

/** Ready-made scenarios, worked out ahead of time: each opens at once. */
export function PresetCards({ presets, to }: { presets: ScenarioBriefDTO[]; to: (id: string) => { pathname: string; search: string } }) {
  return (
    <section aria-label="Ready-made scenarios" className="flex flex-col gap-2.5">
      <h3 className="pw-eyebrow">Ready-made scenarios, open at once</h3>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {presets.map((p) => (
          <li key={p.id} className="flex">
            <Link
              to={to(p.id)}
              className="pw-press pw-scenario flex min-h-11 w-full flex-col gap-1.5 rounded-sheet border border-dashed border-ink-3 bg-panel p-4 text-ink no-underline hover:bg-inset"
            >
              <span className="text-control font-semibold">{p.name}</span>
              <span className="text-small leading-5 text-ink-2">{p.message}</span>
              <span className="mt-auto inline-flex items-center gap-1.5 pt-1 text-caption font-semibold text-ink-3">
                <Icon name="arrow" size={13} strokeWidth={2} />
                {p.status === 'done' ? 'Ready: opens at once' : 'Opens, and finishes working out'}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** On a step that has its answer: a quiet way into the same builder. */
export function WhatIfLink({ status }: { status: string }) {
  const offline = useSnapshotActive()
  const to = useScenarioTo()
  // Scenarios are for missions still to fly: a flown mission's record is what happened.
  if (offline || status !== 'planned') return null
  return (
    <p className="text-small text-ink-3">
      <Link to={to('new')} className="inline-flex min-h-11 items-center gap-1.5 text-ink-2 underline decoration-line-strong underline-offset-4 hover:text-ink">
        <Icon name="quarter" size={14} />
        What if…
      </Link>{' '}
      Try other dates, a vehicle or a landing spot. The result is labelled as a scenario and the record stays as it is.
    </p>
  )
}
