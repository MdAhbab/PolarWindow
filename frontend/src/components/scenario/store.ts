import { create } from 'zustand'

/**
 * The scenario each mission is being read in, kept for the session so that a
 * step link which drops `?scenario=` (the step bar, a card) does not drop the
 * reader out of the scenario. The address is still the state that is shared:
 * this only restores it. Leaving the scenario clears it.
 */
interface ActiveScenarioState {
  active: Record<string, string>
  /** Missions the reader asked to see only what is published: no worked example opens by itself. */
  recordOnly: Record<string, true>
  remember: (missionId: string, scenarioId: string) => void
  forget: (missionId: string) => void
  /** Leave the scenario and keep to the record for the rest of the session. */
  showRecord: (missionId: string) => void
}

export const useActiveScenario = create<ActiveScenarioState>((set) => ({
  active: {},
  recordOnly: {},
  remember: (missionId, scenarioId) =>
    set((s) => {
      if (s.active[missionId] === scenarioId && !s.recordOnly[missionId]) return s
      const { [missionId]: _shown, ...recordOnly } = s.recordOnly
      return { active: { ...s.active, [missionId]: scenarioId }, recordOnly }
    }),
  showRecord: (missionId) =>
    set((s) => {
      const { [missionId]: _gone, ...rest } = s.active
      return { active: rest, recordOnly: { ...s.recordOnly, [missionId]: true } }
    }),
  forget: (missionId) =>
    set((s) => {
      if (!(missionId in s.active)) return s
      const { [missionId]: _gone, ...rest } = s.active
      return { active: rest }
    }),
}))
