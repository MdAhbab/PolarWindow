import { create } from 'zustand'

/**
 * The scenario each mission is being read in, kept for the session so that a
 * step link which drops `?scenario=` (the step bar, a card) does not drop the
 * reader out of the scenario. The address is still the state that is shared:
 * this only restores it. Leaving the scenario clears it.
 */
interface ActiveScenarioState {
  active: Record<string, string>
  remember: (missionId: string, scenarioId: string) => void
  forget: (missionId: string) => void
}

export const useActiveScenario = create<ActiveScenarioState>((set) => ({
  active: {},
  remember: (missionId, scenarioId) =>
    set((s) => (s.active[missionId] === scenarioId ? s : { active: { ...s.active, [missionId]: scenarioId } })),
  forget: (missionId) =>
    set((s) => {
      if (!(missionId in s.active)) return s
      const { [missionId]: _gone, ...rest } = s.active
      return { active: rest }
    }),
}))
