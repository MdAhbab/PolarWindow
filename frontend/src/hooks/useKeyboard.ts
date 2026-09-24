import { useEffect } from 'react'
import { useMission } from '../lib/store'

/** Where a key press belongs to the focused element, not to the shortcut map. */
const TYPING = new Set(['INPUT', 'TEXTAREA', 'SELECT'])
const ACTIVATES_ON_SPACE = new Set(['BUTTON', 'A', 'SUMMARY'])

/**
 * The keyboard map from the accessibility sheet. Nothing here is mouse-only,
 * and nothing fires while the caret is in a field.
 *
 *   [ ]        step the date by 6 h        ⇧[ ⇧]  by one day
 *   T          read the chart on screen as its table
 *   Space      play / pause the window (M1), unless reduced motion is on
 *
 * The previous version took `(onHelp, onTable)` positionally and was called as
 * `(undefined, navigate('/states'))`: Space was dead, because it returned early
 * whenever `onHelp` was undefined, and T left the screen instead of opening its
 * table -- the opposite of what the on-screen help promised.
 */
export function useKeyboardMap({ reducedMotion }: { reducedMotion: boolean }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement
      if (el && (TYPING.has(el.tagName) || (el as HTMLElement).isContentEditable)) return
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const s = useMission.getState()
      // U8 / WCAG 2.1.4: every bare-key shortcut can be switched off.
      if (!s.shortcuts) return
      // A modal (the run log, the settings sheet) owns the keyboard while open.
      if (el instanceof HTMLElement && el.closest('dialog[open]')) return

      switch (e.key) {
        case '[':
        case '{':
          s.nudgeCursor(e.shiftKey ? -24 : -6)
          break
        case ']':
        case '}':
          s.nudgeCursor(e.shiftKey ? 24 : 6)
          break
        case ' ':
          // Space already means "press" on a focused control; do not steal it.
          if (el && ACTIVATES_ON_SPACE.has(el.tagName)) return
          if (reducedMotion) return
          e.preventDefault()
          s.setPlaying(!s.playing)
          break
        case 't':
        case 'T':
          s.toggleTable()
          break
        default:
          return
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [reducedMotion])
}
