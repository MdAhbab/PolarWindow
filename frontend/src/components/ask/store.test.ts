import { beforeEach, describe, expect, it } from 'vitest'
import { isAskShortcut, useAsk } from './store'

const key = (k: string, mods: Partial<{ ctrlKey: boolean; metaKey: boolean; altKey: boolean }> = {}) => ({
  key: k,
  ctrlKey: false,
  metaKey: false,
  altKey: false,
  ...mods,
})
const page = { typing: false, inDialog: false }

describe('the Ask shortcuts', () => {
  it('opens on / outside a field, and on Ctrl+K or Cmd+K anywhere outside a modal', () => {
    expect(isAskShortcut(key('/'), page, true)).toBe(true)
    expect(isAskShortcut(key('k', { ctrlKey: true }), page, true)).toBe(true)
    expect(isAskShortcut(key('K', { metaKey: true }), { typing: true, inDialog: false }, false)).toBe(true)
  })

  it('leaves / to a field, to a switched-off shortcut map and to an open modal', () => {
    expect(isAskShortcut(key('/'), { typing: true, inDialog: false }, true)).toBe(false)
    expect(isAskShortcut(key('/'), page, false)).toBe(false)
    expect(isAskShortcut(key('k', { ctrlKey: true }), { typing: false, inDialog: true }, true)).toBe(false)
    expect(isAskShortcut(key('/', { ctrlKey: true }), page, true)).toBe(false)
    expect(isAskShortcut(key('k'), page, true)).toBe(false)
  })
})

describe('the Ask store', () => {
  beforeEach(() => useAsk.setState({ isOpen: false, text: null, textId: 0 }))

  it('opens, closes and toggles', () => {
    useAsk.getState().open()
    expect(useAsk.getState().isOpen).toBe(true)
    useAsk.getState().close()
    expect(useAsk.getState().isOpen).toBe(false)
    useAsk.getState().toggle()
    expect(useAsk.getState().isOpen).toBe(true)
  })

  it('carries the words it was opened with, and the same words twice arrive twice', () => {
    useAsk.getState().open('  When can IM-3 launch? ')
    expect(useAsk.getState()).toMatchObject({ isOpen: true, text: 'When can IM-3 launch?', textId: 1 })
    useAsk.getState().open('When can IM-3 launch?')
    expect(useAsk.getState().textId).toBe(2)
    useAsk.getState().open('   ')
    expect(useAsk.getState().textId).toBe(2)
  })
})
