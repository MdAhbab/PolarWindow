import { useEffect, useState } from 'react'
import { filmFilesReachable } from './film'

/**
 * Whether the film files are there (public/landing). One small request, once
 * per page, before any film asks for its own: if the folder is missing, blocked
 * or answers with the app's own page in place of a file, every stage falls back
 * to the Moon behind the page and nothing else is requested, so a deployment
 * without the films costs the console one line and not one per file.
 */
let probe: Promise<boolean> | null = null
function reachable(): Promise<boolean> {
  probe ??= fetch('/landing/light-poster-small.jpg', { method: 'HEAD' })
    .then((r) => filmFilesReachable(r.ok, r.headers.get('content-type')))
    .catch(() => false)
  return probe
}

export type FilmFiles = 'checking' | 'yes' | 'no'

export function useFilmFiles(): FilmFiles {
  const [state, setState] = useState<FilmFiles>('checking')
  useEffect(() => {
    let on = true
    void reachable().then((ok) => on && setState(ok ? 'yes' : 'no'))
    return () => {
      on = false
    }
  }, [])
  return state
}
