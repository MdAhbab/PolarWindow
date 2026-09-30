import { create } from 'zustand'

export type SettingsTab = 'project' | 'parameters' | 'risk' | 'sources' | 'appearance' | 'offline'

/**
 * Which group Settings opens on. Kept apart from the sheet itself, so a link
 * elsewhere ("See the data sources") can choose it without loading Settings.
 */
export const useSettingsTab = create<{ tab: SettingsTab; setTab: (t: SettingsTab) => void }>((set) => ({
  tab: 'project',
  setTab: (tab) => set({ tab }),
}))
