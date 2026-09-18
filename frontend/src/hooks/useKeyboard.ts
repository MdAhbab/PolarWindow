import { useEffect } from 'react'
import { useMission } from '../lib/store'

const TYPING = new Set(['INPUT', 'TEXTAREA', 'SELECT'])

/**
 * The keyboard map from the accessibility sheet. Nothing here is mouse-only,
 * and nothing fires while the caret is in a field.
 */
export function useKeyboardMap(onHelp?: () => void, onTable?: () => void) {
  const nudgeCursor = useMission((s) => s.nudgeCursor)
  const setFace = useMission((s) => s.setFace)
  const setPlaying = useMission((s) => s.setPlaying)
  const playing = useMission((s) => s.playing)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement
      if (el && TYPING.has(el.tagName)) return
      if (e.metaKey || e.ctrlKey || e.altKey) return

      switch (e.key) {
        case '[':
          nudgeCursor(e.shiftKey ? -24 : -6)
          break
        case ']':
          nudgeCursor(e.shiftKey ? 24 : 6)
          break
        case '1':
          setFace('planner')
          break
        case '2':
          setFace('educator')
          break
        case '3':
          setFace('public')
          break
        case ' ':
          if (onHelp === undefined) return
          e.preventDefault()
          setPlaying(!playing)
          break
        case 't':
        case 'T':
          onTable?.()
          break
        case '?':
          onHelp?.()
          break
        default:
          return
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [nudgeCursor, setFace, setPlaying, playing, onHelp, onTable])
}
