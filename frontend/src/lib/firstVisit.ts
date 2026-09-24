/**
 * The first-visit flag (U1), in `localStorage`, always inside try/catch: a
 * private window, blocked site data or a storage quota must never break the
 * front door. When storage fails the visitor is treated as returning, which
 * sends them to Missions rather than into a loop through the story.
 */
export const VISITED_KEY = 'pw-visited'

export function hasVisited(storage: Pick<Storage, 'getItem'> | undefined = safeStorage()): boolean {
  try {
    return !storage || storage.getItem(VISITED_KEY) !== null
  } catch {
    return true
  }
}

export function markVisited(storage: Pick<Storage, 'setItem'> | undefined = safeStorage()): void {
  try {
    storage?.setItem(VISITED_KEY, '1')
  } catch {
    /* storage refused: the next visit goes to Missions anyway */
  }
}

function safeStorage(): Storage | undefined {
  try {
    return typeof localStorage === 'undefined' ? undefined : localStorage
  } catch {
    return undefined
  }
}
