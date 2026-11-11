import { Link } from 'react-router-dom'
import type { ScenarioDTO, ScenarioPhaseDTO } from '../../lib/api/experience.types'
import { useSections } from '../../lib/api/lifecycleQueries'
import { Icon, type IconName } from '../Icon'
import { SECTIONS, sectionPath } from '../lifecycle/JourneyBar'
import { UNDER_QUESTION } from '../lifecycle/Section'
import { ProgressTrack } from '../States'
import { Panel } from '../ui'

const PHASE_STATE: Record<ScenarioPhaseDTO['state'], { icon: IconName; words: string }> = {
  pending: { icon: 'ring', words: 'Waiting' },
  active: { icon: 'quarter', words: 'Working' },
  done: { icon: 'check', words: 'Done' },
  skipped: { icon: 'dash', words: 'Left out' },
  failed: { icon: 'alert', words: 'Failed' },
}

/**
 * A scenario being worked out: its phases with their states and details, the
 * real fraction, the service's message, and where else to go meanwhile.
 * Announces itself politely; the page updates when the answer is ready.
 */
export function ScenarioProgress({ scenario }: { scenario: ScenarioDTO }) {
  const pct = Math.round(scenario.progress * 100)
  const sections = useSections(scenario.mission_id)
  const open = SECTIONS.filter((s) => s.id !== 'ready').filter((s) => {
    const st = sections.data?.data.find((x) => x.section === s.id)
    return st ? st.state === 'available' : false
  })
  return (
    <Panel className={`${UNDER_QUESTION} flex flex-col gap-4 p-5`} guide="scenario-progress">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 className="flex items-center gap-2 text-title font-semibold text-ink">
          <Icon name="quarter" size={18} />
          {scenario.status === 'queued' ? 'Waiting its turn to be worked out' : 'Working out the scenario'}
        </h3>
        <span className="font-mono text-small text-ink-2 tnum">{pct}%</span>
      </div>
      <ProgressTrack label="Scenario progress" max={100} now={pct} fraction={scenario.progress} valueText={`${pct} percent`} />
      <p className="text-body text-ink-2" role="status" aria-live="polite">
        {scenario.message}
      </p>
      <ol className="flex flex-col divide-y divide-line border-y border-line" aria-label="Phases">
        {scenario.phases.map((p) => {
          const s = PHASE_STATE[p.state]
          return (
            <li key={p.id} className="flex items-start gap-3 py-2.5" data-state={p.state}>
              <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-pill border border-line-strong text-ink-2" aria-hidden="true">
                <Icon name={s.icon} size={13} strokeWidth={2.2} />
              </span>
              <span className="flex min-w-0 flex-col">
                <span className="flex flex-wrap items-baseline gap-x-2 text-body font-semibold text-ink">
                  {p.label}
                  <span className="text-caption font-normal text-ink-3">{s.words}</span>
                </span>
                {p.detail && <span className="text-small leading-5 text-ink-2">{p.detail}</span>}
              </span>
            </li>
          )
        })}
      </ol>
      <div className="flex flex-col gap-1.5 border-l-2 border-line-strong pl-3">
        <p className="text-small leading-5 text-ink-2">
          The other pages are free to use meanwhile. This one keeps working, and the activity ring shows it everywhere.
        </p>
        <ul className="flex flex-wrap gap-x-4">
          {open.slice(0, 3).map((s) => (
            <li key={s.id}>
              <Link to={sectionPath(scenario.mission_id, s.id)} className="inline-flex min-h-11 items-center text-small font-semibold">
                {s.name}
              </Link>
            </li>
          ))}
          <li>
            <Link to="/map" className="inline-flex min-h-11 items-center text-small font-semibold">
              The map
            </Link>
          </li>
        </ul>
      </div>
    </Panel>
  )
}
