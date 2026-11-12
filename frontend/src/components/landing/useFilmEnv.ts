import { useState, useSyncExternalStore } from 'react'
import { readPrefs } from '../../lib/prefs'
import { filmMode, filmSize, type FilmEnv, type FilmMode, type FilmSize } from './film'

/** A media query as a value that follows the window. */
function useMedia(query: string): boolean {
  return useSyncExternalStore(
    (notify) => {
      if (typeof matchMedia === 'undefined') return () => {}
      const mq = matchMedia(query)
      mq.addEventListener('change', notify)
      return () => mq.removeEventListener('change', notify)
    },
    () => typeof matchMedia !== 'undefined' && matchMedia(query).matches,
    () => false,
  )
}

/** The visitor's data saver choice, where the browser says it (Chromium does; others read as off). */
function saveDataOn(): boolean {
  const c = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection
  return Boolean(c?.saveData)
}

/** A connection the browser calls 2G or 3G. */
function slowConnection(): boolean {
  const c = (navigator as Navigator & { connection?: { effectiveType?: string } }).connection
  return Boolean(c?.effectiveType && /^(slow-2g|2g|3g)$/.test(c.effectiveType))
}

/**
 * What the visitor's device and settings allow the films to do: the system's
 * reduced-motion setting and the app's own both count, as does data saver, and
 * a phone's width (under 768 px) is its own case (see `filmMode`).
 */
export function useFilmEnv(): FilmEnv & FilmMode & { size: FilmSize } {
  const osReduced = useMedia('(prefers-reduced-motion: reduce)')
  const phone = useMedia('(max-width: 767px)')
  const env: FilmEnv = {
    reduced: osReduced || readPrefs().motion === 'reduced',
    phone,
    saveData: saveDataOn(),
  }
  // Which file to fetch is decided once, when the page opens: a window dragged wider later keeps the file it has.
  const [size] = useState<FilmSize>(() => filmSize(window.innerWidth, window.devicePixelRatio, slowConnection()))
  return { ...env, ...filmMode(env), size }
}
