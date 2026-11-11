import { createContext, useContext } from 'react'
import type { ScenarioDTO } from '../../lib/api/experience.types'

/**
 * The scenario being shown, for everything drawn under it. A section that
 * would write to the mission's record (an official forecast, a booking, a
 * limit, an export of record) asks `useInScenario()` and holds back with a
 * reason; headings ask it to say "Scenario".
 */
export const ScenarioContext = createContext<ScenarioDTO | null>(null)

export function useScenarioShown(): ScenarioDTO | null {
  return useContext(ScenarioContext)
}

export function useInScenario(): boolean {
  return useContext(ScenarioContext) !== null
}
