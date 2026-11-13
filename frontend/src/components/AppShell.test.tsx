// @vitest-environment jsdom
/**
 * The shell's phone bar (ruling L-1): Home, Missions, Sites and Ask are its
 * four items, Ask a button that opens the same dock the header's button does,
 * and no floating Ask button is left over the page.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, screen, within } from '@testing-library/react'
import { renderApp } from '../test/render'
import { AppShell } from './AppShell'
import { useAsk } from './ask/store'

beforeEach(() => {
  // No service: every request stays pending, so the shell renders its own parts only.
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})))
  useAsk.setState({ isOpen: false, text: null, textId: 0, turns: [], nextId: 1 })
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

/** The bar at the bottom of a phone: the last "Views" navigation (the header's comes first). */
const bar = () => screen.getAllByRole('navigation', { name: 'Views' }).at(-1) as HTMLElement

describe('the phone bar', () => {
  it('has four items in order: Home, Missions, Sites, then Ask as a button', () => {
    renderApp(<AppShell>page</AppShell>, { route: '/home' })
    const items = [...bar().querySelectorAll('[data-pw-item]')]
    expect(items.map((i) => i.textContent?.trim())).toEqual(['Home', 'Missions', 'Sites', 'Ask'])
    expect(items.map((i) => i.tagName)).toEqual(['A', 'A', 'A', 'BUTTON'])
    // The three views are links; Ask is not one.
    expect(within(bar()).getAllByRole('link')).toHaveLength(3)
    expect(within(bar()).getByRole('button', { name: 'Ask' })).toBeTruthy()
  })

  it('draws Ask like the other three, at least 44 px tall', () => {
    renderApp(<AppShell>page</AppShell>, { route: '/home' })
    const [home, , , ask] = [...bar().querySelectorAll<HTMLElement>('[data-pw-item]')]
    // 48 px (h-12), the same height and layout as a view's link.
    for (const item of [home, ask]) {
      expect(item.className).toContain('h-12')
      expect(item.className).toContain('flex-col')
    }
    expect(ask.className).not.toContain('bg-ink')
  })

  it('opens the Ask dock, and says so', () => {
    renderApp(<AppShell>page</AppShell>, { route: '/home' })
    const ask = within(bar()).getByRole('button', { name: 'Ask' })
    expect(ask.getAttribute('aria-expanded')).toBe('false')
    fireEvent.click(ask)
    expect(useAsk.getState().isOpen).toBe(true)
    expect(ask.getAttribute('aria-expanded')).toBe('true')
    fireEvent.click(ask)
    expect(useAsk.getState().isOpen).toBe(false)
  })

  it('leaves no floating Ask button: every Ask button is the header\'s or the bar\'s', () => {
    renderApp(<AppShell>page</AppShell>, { route: '/home' })
    const asks = screen.getAllByRole('button', { name: 'Ask' })
    expect(asks).toHaveLength(2)
    for (const a of asks) expect(a.closest('header, nav[aria-label="Views"]')).not.toBeNull()
    expect(document.querySelector('button.fixed[aria-label="Ask"]')).toBeNull()
  })

  it('still opens on / and on Ctrl+K', () => {
    renderApp(<AppShell>page</AppShell>, { route: '/home' })
    act(() => {
      fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    })
    expect(useAsk.getState().isOpen).toBe(true)
    act(() => useAsk.getState().close())
    act(() => {
      fireEvent.keyDown(window, { key: '/' })
    })
    expect(useAsk.getState().isOpen).toBe(true)
  })

  it('leaves room under the page for the bar alone: no extra for a floating button', () => {
    renderApp(<AppShell>page</AppShell>, { route: '/home' })
    const main = document.getElementById('pw-main') as HTMLElement
    // The bar and its gap from the screen's edge, plus room so a page's last line clears it.
    expect(main.className).toContain('pb-[calc(8rem+')
    expect(main.className).not.toContain('9.5rem')
  })
})
