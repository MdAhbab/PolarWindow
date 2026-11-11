import { Link, useLocation } from 'react-router-dom'
import type { ScenarioDTO } from '../../lib/api/experience.types'
import { useScenarios } from '../../lib/api/scenarios'
import { Disclosure } from '../ui'
import { AssumptionList } from './Basis'
import { useActiveScenario } from './store'
import { stepsWords, withScenario } from './words'

const BTN =
  'pw-press inline-flex h-12 items-center rounded-pill border border-line-strong bg-tray px-5 text-control font-semibold text-ink no-underline hover:border-ink-3 hover:bg-inset'

/**
 * The band above a scenario's answer: it can never be mistaken for the
 * record. Name, what it is, the assumptions with their bases (a count,
 * expandable), the way back to the builder, the way out, and the mission's
 * other scenarios.
 */
export function ScenarioBand({ scenario }: { scenario: ScenarioDTO }) {
  const loc = useLocation()
  const forget = useActiveScenario((s) => s.forget)
  const others = useScenarios(scenario.mission_id).data?.items.filter((s) => s.id !== scenario.id) ?? []
  const here = (id: string | null, extra: Record<string, string | null> = {}) => ({ pathname: loc.pathname, search: withScenario(loc.search, id, extra) })
  return (
    <aside aria-label="Scenario" className="pw-scenario -mt-2 flex min-w-0 flex-col gap-4 rounded-sheet border-2 border-dashed border-ink-3 bg-panel p-4 sm:p-5">
      <div className="flex flex-col gap-1">
        <p className="text-tag font-semibold tracking-caps-md text-ink uppercase">Scenario{scenario.preset ? ' · ready-made' : ''}</p>
        <h3 className="text-title leading-6 font-semibold text-ink">{scenario.name}</h3>
        <p className="max-w-3xl text-small leading-5 text-ink-2">
          Worked out from assumptions, not from the mission’s record. Nothing here is written to the record.
          {scenario.sections.length > 0 && <> Steps worked out: {stepsWords(scenario.sections)}.</>}
        </p>
        {scenario.prompt && <p className="max-w-3xl text-small leading-5 text-ink-3">You asked: “{scenario.prompt}”</p>}
      </div>
      <Disclosure title="Assumptions" meta={`${scenario.assumptions.length} · each with where it came from`}>
        <AssumptionList items={scenario.assumptions} />
      </Disclosure>
      <div className="flex flex-wrap gap-3">
        <Link to={here('new', { edit: scenario.id })} className={BTN}>
          Edit assumptions
        </Link>
        <Link to={here(null, { edit: null })} onClick={() => forget(scenario.mission_id)} className={BTN}>
          Leave the scenario
        </Link>
      </div>
      {others.length > 0 && (
        <nav aria-label="Other scenarios for this mission" className="flex flex-col gap-1">
          <h4 className="pw-eyebrow">This mission’s other scenarios</h4>
          <ul className="flex flex-wrap gap-x-5">
            {others.map((o) => (
              <li key={o.id}>
                <Link to={here(o.id, { edit: null })} className="inline-flex min-h-11 items-center text-small font-semibold">
                  {o.name}
                  {o.preset ? ' (ready-made)' : ''}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      )}
    </aside>
  )
}
