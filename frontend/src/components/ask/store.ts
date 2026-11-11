import { useEffect } from 'react'
import { create } from 'zustand'
import { useMission } from '../../lib/store'

/**
 * Whether the Ask dock is open, and the words it should start with.
 *
 * The shell's Ask button, the `/` and Ctrl/Cmd+K shortcuts and Home's Ask bar
 * all come here; the dock itself (a later piece of stream C) reads it. `text`
 * is a question someone already typed or picked, with `textId` changing each
 * time one is sent, so the same chip pressed twice still arrives twice.
 */
interface AskState {
  isOpen: boolean
  text: string | null
  textId: number
  open: (text?: string) => void
  close: () => void
  toggle: () => void
}

export const useAsk = create<AskState>((set) => ({
  isOpen: false,
  text: null,
  textId: 0,
  open: (text) =>
    set((s) => {
      const t = text?.trim()
      return t ? { isOpen: true, text: t, textId: s.textId + 1 } : { isOpen: true }
    }),
  close: () => set({ isOpen: false }),
  toggle: () => set((s) => ({ isOpen: !s.isOpen })),
}))

/** The keys a press is judged on: the event's, without the DOM. */
export interface KeyPress {
  key: string
  ctrlKey: boolean
  metaKey: boolean
  altKey: boolean
  shiftKey?: boolean
}

/** Where the press landed: typing in a field, or inside an open modal. */
export interface KeyTarget {
  typing: boolean
  inDialog: boolean
}

/**
 * Whether a key press opens Ask. Ctrl/Cmd+K works anywhere outside a modal,
 * since it is never a character. A bare `/` is a character, so it only counts
 * outside a field, and only while bare-key shortcuts are on (WCAG 2.1.4).
 */
export function isAskShortcut(e: KeyPress, at: KeyTarget, shortcutsOn: boolean): boolean {
  if (at.inDialog) return false
  if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 'k') return true
  if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey) return false
  return shortcutsOn && !at.typing
}

const TYPING = new Set(['INPUT', 'TEXTAREA', 'SELECT'])

/** Opens Ask on `/` or Ctrl/Cmd+K, from anywhere in the shell. */
export function useAskShortcuts() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement
      const at: KeyTarget = {
        typing: Boolean(el && (TYPING.has(el.tagName) || (el as HTMLElement).isContentEditable)),
        inDialog: el instanceof HTMLElement && Boolean(el.closest('dialog[open]')),
      }
      if (!isAskShortcut(e, at, useMission.getState().shortcuts)) return
      e.preventDefault()
      useAsk.getState().open()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
}
