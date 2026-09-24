/**
 * The few choices worth keeping between visits: the theme, reduced motion
 * and the single-key shortcuts. A voice-control user
 * who turns the shortcuts off should not have to do it again on every visit.
 *
 * Browser storage can be missing or refuse (a private window, blocked site
 * data), so every read and write is wrapped, and a failure simply means the
 * defaults: dark, full motion, shortcuts on.
 */
export interface Prefs {
  theme: 'dark' | 'light'
  motion: 'full' | 'reduced'
  shortcuts: boolean
}

export const PREFS_KEY = 'pw-prefs'

export const DEFAULT_PREFS: Prefs = { theme: 'dark', motion: 'full', shortcuts: true }

/**
 * Stored values are checked field by field; anything unexpected falls back to
 * its default, and a key from an older version (the detail level) is ignored.
 */
export function parsePrefs(raw: string | null): Prefs {
  let v: Record<string, unknown> = {}
  try {
    const parsed: unknown = raw ? JSON.parse(raw) : {}
    if (parsed && typeof parsed === 'object') v = parsed as Record<string, unknown>
  } catch {
    /* unreadable: defaults */
  }
  return {
    theme: v.theme === 'light' ? 'light' : 'dark',
    motion: v.motion === 'reduced' ? 'reduced' : 'full',
    shortcuts: v.shortcuts === false ? false : true,
  }
}

export function readPrefs(): Prefs {
  try {
    return parsePrefs(typeof localStorage === 'undefined' ? null : localStorage.getItem(PREFS_KEY))
  } catch {
    return DEFAULT_PREFS
  }
}

export function writePrefs(p: Prefs): void {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(p))
  } catch {
    /* storage refused: the choice lasts for this visit only */
  }
}
