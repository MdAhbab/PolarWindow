// @vitest-environment jsdom
/**
 * The motion grammar's guard (M1). One table of timings lives in globals.css;
 * no other source file may bring its own. And every class of the grammar has
 * its reduced-motion branch, in code and in the CSS floor.
 */
import { readFileSync } from 'node:fs'
import { act } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { useMission } from './store'
import { leave } from './motion'
import { SwapLabel, useOpenRow } from '../components/ui'
import { AmbientGlow } from '../components/AmbientGlow'

/** Every script under src/, as text, keyed by its path from src/ ("components/ui.tsx"). */
const FILES: Record<string, string> = Object.fromEntries(
  Object.entries(import.meta.glob<string>('../**/*.{ts,tsx}', { query: '?raw', import: 'default', eager: true })).map(
    ([path, text]) => [path.replace(/^\.\.\//, ''), text],
  ),
)
/** The stylesheet, read from disk (a test's CSS import is empty: vitest leaves CSS out). Tests run from frontend/. */
const GLOBALS_CSS: string = readFileSync('src/styles/globals.css', 'utf8')

/**
 * Files that may keep their own timings, and why. Short on purpose: a new
 * entry needs a reason a reviewer would accept.
 */
const ALLOW: { path: string; why: string }[] = [
  { path: 'screens/LandingScreen.tsx', why: 'owned by L1 (the landing page is being rebuilt this round)' },
  { path: 'components/landing/', why: 'owned by L1 (the landing page is being rebuilt this round)' },
  { path: 'lib/motion.test.tsx', why: 'this guard, which names the patterns it forbids' },
]

/** Raw Tailwind timing utilities, and a literal time given to a transition or an animation. */
const FORBIDDEN: { name: string; re: RegExp }[] = [
  { name: 'raw Tailwind duration utility', re: /(?<![\w-])duration-\d+\b/ },
  { name: 'raw Tailwind easing utility', re: /(?<![\w-])ease-(?:in-out|in|out|linear)(?![\w-])/ },
  { name: 'literal time in an arbitrary duration or delay', re: /(?<![\w-])(?:duration|delay)-\[\d/ },
  {
    name: 'literal time in a transition or animation',
    re: /\b(?:transition|animation)[A-Za-z]*['"]?\s*[:=]\s*[`'"][^`'"]*?\b\d+(?:\.\d+)?m?s\b/,
  },
  { name: 'literal duration handed to an animation', re: /\bduration\s*:\s*\d/ },
]

describe('one table of timings', () => {
  it('no source file outside globals.css brings a timing of its own', () => {
    const found: string[] = []
    expect(Object.keys(FILES).length).toBeGreaterThan(100)
    for (const [rel, text] of Object.entries(FILES)) {
      if (rel === 'styles/globals.css' || ALLOW.some((a) => rel.startsWith(a.path))) continue
      text
        .split(/\r?\n/)
        .forEach((line, i) => {
          for (const f of FORBIDDEN) if (f.re.test(line)) found.push(`${rel}:${i + 1} ${f.name}: ${line.trim().slice(0, 120)}`)
        })
    }
    expect(found).toEqual([])
  })

  it('catches what it is meant to catch', () => {
    const bad = [
      'className="transition duration-300 ease-in-out"',
      "transition: 'transform 460ms cubic-bezier(.2,.8,.2,1)'",
      'className="duration-[460ms]"',
      'el.animate(frames, { duration: 300 })',
      'className="ease-linear"',
    ]
    for (const b of bad) expect(FORBIDDEN.some((f) => f.re.test(b)), b).toBe(true)
    const good = [
      'className="transition-colors duration-[var(--pw-dur-quick)] ease-[var(--ease-settle)]"',
      "transition: reduced ? 'none' : 'transform var(--pw-dur-sheet) var(--ease-move)'",
      '--ease-leave: cubic-bezier(0.4, 0, 1, 1)',
    ]
    for (const g of good) expect(FORBIDDEN.some((f) => f.re.test(g)), g).toBe(false)
  })

  it('globals.css names a time only in the tokens or in a named exception', () => {
    const css = GLOBALS_CSS
    /** Lines that may carry a literal time, each with its reason. */
    const KEPT: { has: string; why: string }[] = [
      { has: '--pw-dur-', why: 'the duration tokens themselves' },
      { has: '0.001ms !important', why: 'the reduced-motion floor' },
      { has: '0s !important', why: 'the reduced-motion floor for rows' },
      { has: 'visibility 0s', why: 'a discrete switch, not a motion' },
      { has: '60ms both', why: 'arrival stagger (one beat per item)' },
      { has: '120ms both', why: 'arrival stagger (one beat per item)' },
      { has: '+ 120ms) backwards', why: 'a bar grows a beat after its card' },
      { has: '+ 160ms) backwards', why: 'a chart draws a beat after its card' },
      { has: '* 35ms) backwards', why: 'pins drop one after another' },
      { has: 'pw-seg-y) 420ms', why: 'the journey line drawing itself keeps its own pace (motion-spec)' },
      { has: 'pw-path-draw 960ms', why: 'the journey line drawing itself keeps its own pace (motion-spec)' },
      { has: 'pw-pulse 1.6s', why: 'a loading breath: a loop period, not a transition' },
      { has: 'pw-slide 1.4s', why: "a job's progress: one pass of the band" },
      { has: 'pw-spin 1.4s', why: "a job's progress: one turn" },
      { has: '--pw-glow-cycle:', why: 'the ambient glow, the one loop the owner asked for (L-12): 70 to 110 s cycles' },
      { has: '* -1s)', why: 'the glow starts where the clock says it is' },
    ]
    // A time other than zero (a `0ms` fallback is no timing).
    const time = /(?<![\w.-])(?!0m?s\b)\d+(?:\.\d+)?m?s\b/
    const lines: { line: string; n: number }[] = css.split(/\r?\n/).map((line: string, i: number) => ({ line, n: i + 1 }))
    const stray = lines
      .filter(({ line }) => !line.trim().startsWith('/*') && !line.trim().startsWith('*') && time.test(line.replace(/\/\*.*?\*\//g, '')))
      .filter(({ line }) => !KEPT.some((k) => line.includes(k.has)))
      .map(({ line, n }) => `globals.css:${n} ${line.trim()}`)
    expect(stray).toEqual([])
  })
})

describe('every class of the grammar has its reduced-motion branch', () => {
  beforeEach(() => useMission.setState({ motion: 'full' }))
  afterEach(() => {
    cleanup()
    useMission.setState({ motion: 'full' })
    vi.useRealTimers()
  })

  it('the CSS floor stops every movement, for the OS setting and the app’s own', () => {
    const css = GLOBALS_CSS
    const os = css.slice(css.indexOf('@media (prefers-reduced-motion: reduce)'))
    const app = css.slice(css.indexOf(":root[data-motion='reduced'] *,"))
    for (const block of [os, app]) {
      expect(block).toMatch(/animation-duration: 0\.001ms !important/)
      expect(block).toMatch(/transition-duration: 0\.001ms !important/)
      // `*` does not reach these, so each has its own line.
      expect(block).toMatch(/\.pw-glow-field \{\s*animation: none;/)
      expect(block).toMatch(/::details-content \{\s*transition-duration: 0s !important;/)
      expect(block).toMatch(/::view-transition-group\(\*\)/)
    }
  })

  it('a label that changes settles into place, and under reduced motion simply changes', () => {
    const { rerender } = render(<SwapLabel label="Work it out" room={['Work it out', 'Working it out…']} />)
    rerender(<SwapLabel label="Working it out…" room={['Work it out', 'Working it out…']} />)
    expect(screen.getByText('Working it out…').className).toContain('pw-swap-in')
    cleanup()
    act(() => useMission.setState({ motion: 'reduced' }))
    const r = render(<SwapLabel label="Work it out" room={['Work it out', 'Working it out…']} />)
    r.rerender(<SwapLabel label="Working it out…" room={['Work it out', 'Working it out…']} />)
    expect(screen.getByText('Working it out…').className).not.toContain('pw-swap-in')
    // The other labels hold the width without being words in the page.
    expect(screen.queryByText('Work it out')).toBeNull()
  })

  function Row({ open }: { open: boolean }) {
    const row = useOpenRow(open)
    return (
      <div ref={row.ref} hidden={row.hidden} className="pw-open-row" data-testid="row">
        <p hidden={row.hidden}>Body</p>
      </div>
    )
  }

  it('a row closes on its own time, and at once under reduced motion', () => {
    vi.useFakeTimers()
    const { rerender } = render(<Row open={false} />)
    expect(screen.getByTestId('row').hidden).toBe(true)
    rerender(<Row open />)
    expect(screen.getByTestId('row').hidden).toBe(false)
    expect(screen.getByTestId('row').hasAttribute('data-open')).toBe(true)
    rerender(<Row open={false} />)
    // Still drawn while it closes, then hidden.
    expect(screen.getByTestId('row').hidden).toBe(false)
    expect(screen.getByTestId('row').hasAttribute('data-open')).toBe(false)
    act(() => vi.advanceTimersByTime(300))
    expect(screen.getByTestId('row').hidden).toBe(true)

    act(() => useMission.setState({ motion: 'reduced' }))
    rerender(<Row open />)
    rerender(<Row open={false} />)
    expect(screen.getByTestId('row').hidden).toBe(true)
  })

  it('a menu leaves as a copy with no words, roles or focus, and not at all under reduced motion', () => {
    const proto = Element.prototype as Element & { getAnimations?: () => Animation[] }
    const had = proto.getAnimations
    proto.getAnimations = () => []
    try {
      document.body.innerHTML = '<div id="host"><div id="m" role="menu" class="pw-pop"><button role="menuitem">Guide</button></div></div>'
      const menu = document.getElementById('m')!
      leave(menu, 'pw-pop-out', true)
      expect(document.querySelectorAll('.pw-pop-out')).toHaveLength(0)
      leave(menu, 'pw-pop-out', false)
      const ghost = document.querySelector<HTMLElement>('.pw-pop-out')!
      expect(ghost).not.toBeNull()
      expect(ghost.getAttribute('aria-hidden')).toBe('true')
      expect(ghost.hasAttribute('inert')).toBe(true)
      expect(ghost.hasAttribute('id') || ghost.hasAttribute('role')).toBe(false)
      expect(ghost.querySelector('[role]')).toBeNull()
      expect(ghost.textContent).toBe('')
      expect(ghost.classList.contains('pw-pop')).toBe(false)
    } finally {
      proto.getAnimations = had
      document.body.innerHTML = ''
    }
  })

  it('the glow rests under reduced motion', () => {
    const { container } = render(<AmbientGlow />)
    const glow = container.querySelector('.pw-glow')!
    expect(glow.getAttribute('aria-hidden')).toBe('true')
    expect(glow.hasAttribute('data-still')).toBe(false)
    cleanup()
    act(() => useMission.setState({ motion: 'reduced' }))
    const r = render(<AmbientGlow />)
    expect(r.container.querySelector('.pw-glow')!.hasAttribute('data-still')).toBe(true)
  })
})
