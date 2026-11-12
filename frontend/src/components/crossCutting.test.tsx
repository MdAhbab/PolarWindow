// @vitest-environment jsdom
/**
 * S2, cross-cutting: a table that scrolls says so and fades towards its hidden
 * edge; breadcrumbs reach a phone's 44 px and their separators pass AA; the
 * Ask field's placeholder fits a narrow phone; a quiet button still has an edge.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Button, ScrollRegion, pillClass } from './ui'
import { Breadcrumbs } from './Page'
import { AskBar } from './home/AskBar'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

/** jsdom has no layout: say how wide a box is and how wide its content is. */
function size(el: Element, scrollWidth: number, clientWidth: number) {
  Object.defineProperty(el, 'scrollWidth', { configurable: true, value: scrollWidth })
  Object.defineProperty(el, 'clientWidth', { configurable: true, value: clientWidth })
}

describe('ScrollRegion: the words and the fade', () => {
  let observers: ResizeObserverCallback[] = []
  beforeEach(() => {
    observers = []
    vi.stubGlobal(
      'ResizeObserver',
      class {
        constructor(cb: ResizeObserverCallback) {
          observers.push(cb)
        }
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    )
  })

  it('says nothing and fades nothing while everything fits', () => {
    render(
      <ScrollRegion label="Table, scrolls sideways">
        <table />
      </ScrollRegion>,
    )
    expect(screen.queryByText('Scrolls sideways')).toBeNull()
    expect(screen.getByRole('region').getAttribute('style') ?? '').not.toContain('--pw-scroll-fade')
  })

  it('says "Scrolls sideways" and fades the right edge when there is more to the right, and the left once scrolled', () => {
    const { rerender } = render(
      <ScrollRegion label="Table, scrolls sideways">
        <table />
      </ScrollRegion>,
    )
    const region = screen.getByRole('region')
    size(region, 720, 326)
    act(() => observers.forEach((cb) => cb([], {} as ResizeObserver)))
    rerender(
      <ScrollRegion label="Table, scrolls sideways">
        <table />
      </ScrollRegion>,
    )
    expect(screen.getByText('Scrolls sideways')).toBeTruthy()
    const atStart = region.getAttribute('style') ?? ''
    expect(atStart).toContain('--pw-scroll-fade')
    // Only the far edge is clear at the start: it begins solid, ends transparent.
    expect(atStart).toMatch(/linear-gradient\(to right, var\(--color-ink\), var\(--color-ink\) 0%, var\(--color-ink\) calc\(100% - 2\.5rem\), transparent\)/)

    region.scrollLeft = 200
    act(() => {
      region.dispatchEvent(new Event('scroll'))
    })
    // Scrolled into the middle: both edges fade.
    expect(region.getAttribute('style') ?? '').toMatch(/linear-gradient\(to right, transparent, var\(--color-ink\) 2\.5rem, var\(--color-ink\) calc\(100% - 2\.5rem\), transparent\)/)

    // The region is still named and still takes the keyboard, and the cue is for the eye alone (the name already says it).
    expect(region.getAttribute('aria-label')).toBe('Table, scrolls sideways')
    expect(region.tabIndex).toBe(0)
    expect(screen.getByText('Scrolls sideways').getAttribute('aria-hidden')).toBe('true')
  })

  it('gives the focus ring its whole shape: the fade steps aside on keyboard focus', () => {
    render(
      <ScrollRegion label="Table, scrolls sideways">
        <table />
      </ScrollRegion>,
    )
    expect(screen.getByRole('region').className).toContain('focus-visible:[mask-image:none]')
  })
})

describe('Breadcrumbs on a phone', () => {
  it('has 44 px links below 640 px, 32 px from there, and separators that are hidden from assistive technology and readable', () => {
    render(
      <MemoryRouter>
        <Breadcrumbs items={[{ label: 'Missions', to: '/missions' }, { label: 'IM-2', to: '/missions/im-2' }, { label: 'Surface' }]} />
      </MemoryRouter>,
    )
    const link = screen.getByRole('link', { name: 'Missions' })
    expect(link.className).toContain('min-h-11')
    expect(link.className).toContain('sm:min-h-8')
    const seps = screen.getAllByText('/')
    expect(seps).toHaveLength(2)
    for (const s of seps) {
      expect(s.getAttribute('aria-hidden')).toBe('true')
      // text-line-strong measured 1.75:1; ink-3 clears 4.5:1 in both themes.
      expect(s.className).toContain('text-ink-3')
      expect(s.className).not.toContain('line-strong')
    }
  })
})

describe('the Ask field on a narrow phone', () => {
  function media(narrow: boolean) {
    vi.stubGlobal(
      'matchMedia',
      (q: string) => ({ matches: q.includes('max-width: 399px') ? narrow : false, media: q, addEventListener() {}, removeEventListener() {} }),
    )
  }

  it('keeps the full placeholder on a wide screen', () => {
    media(false)
    render(<AskBar suggestions={[]} />)
    expect(screen.getByRole('textbox').getAttribute('placeholder')).toBe('Ask about a mission, a site or a date')
  })

  it('shortens it under 400 px so it is not cut mid-word, and the field keeps its full accessible name', () => {
    media(true)
    render(<AskBar suggestions={[]} />)
    const box = screen.getByRole('textbox', { name: 'Ask about a mission, a site or a date' })
    expect(box.getAttribute('placeholder')).toBe('Ask about a mission or site')
  })
})

describe('a quiet button still looks like a control', () => {
  it('has a hairline edge, as a button and as a link', () => {
    render(<Button variant="ghost">Cancel</Button>)
    expect(screen.getByRole('button', { name: 'Cancel' }).className).toMatch(/\bborder border-line\b/)
    expect(pillClass('ghost')).toMatch(/\bborder border-line\b/)
  })
})
