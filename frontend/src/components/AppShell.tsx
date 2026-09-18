import { useEffect, useRef, type ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { useMission } from '../lib/store'
import { useKeyboardMap } from '../hooks/useKeyboard'
import { useReducedMotion } from '../hooks/useMotion'
import { Icon, Mark, Wordmark } from './Icon'
import { useProvenance } from '../lib/useProvenance'
import { SampleDataBadge, Segmented, SvgDefs } from './ui'
import type { Face } from '../lib/types'

const NAV = [
  { to: '/map', label: 'Map', icon: 'pin' as const },
  { to: '/clocks', label: 'Two clocks', icon: 'clocks' as const },
  { to: '/compare', label: 'Compare', icon: 'compare' as const },
  { to: '/horizon', label: 'Horizon', icon: 'horizon' as const },
  { to: '/blackout', label: 'Blackout', icon: 'gap' as const },
]

const TITLES: Record<string, string> = {
  '/map': 'Map',
  '/clocks': 'Two clocks',
  '/compare': 'Compare',
  '/horizon': 'Horizon',
  '/blackout': 'Blackout',
  '/report': 'Report',
  '/story': 'Why the pole is hard',
  '/states': 'States',
}

/**
 * Move focus to the content and name the screen when the route changes.
 *
 * A client-side navigation otherwise leaves focus on the link that was
 * pressed, and a screen reader announces nothing: the new screen arrives
 * silently. Focus lands on `main` (not on the first control) so the next Tab
 * starts at the top of the new content, and the document title carries the
 * screen's name, which is what assistive technology reads out.
 */
function useRouteFocus() {
  const { pathname } = useLocation()
  const first = useRef(true)
  useEffect(() => {
    document.title = `${TITLES[pathname] ?? 'POLAR WINDOW'} — POLAR WINDOW`
    if (first.current) {
      first.current = false
      return
    }
    document.getElementById('pw-main')?.focus()
  }, [pathname])
}

const FACES: { value: Face; label: string }[] = [
  { value: 'planner', label: 'Planner' },
  { value: 'educator', label: 'Educator' },
  { value: 'public', label: 'Public' },
]

export function AppShell({ children }: { children: ReactNode }) {
  const provenance = useProvenance()
  // Selectors, not the whole store: during M1 the cursor changes sixty times a
  // second, and a whole-store subscription re-rendered the shell on each one.
  const { face, setFace, theme, setTheme, motion, setMotion } = useMission(
    useShallow((s) => ({
      face: s.face,
      setFace: s.setFace,
      theme: s.theme,
      setTheme: s.setTheme,
      motion: s.motion,
      setMotion: s.setMotion,
    })),
  )
  useKeyboardMap({ reducedMotion: useReducedMotion() })
  useRouteFocus()

  return (
    <div className="flex min-h-full flex-col bg-canvas text-ink">
      <SvgDefs />
      <a
        href="#pw-main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:bg-raised focus:px-4 focus:py-3"
      >
        Skip to the content
      </a>

      <header className="flex shrink-0 flex-wrap items-center gap-x-6 gap-y-2 border-b border-line px-4 py-2 lg:px-6">
        <NavLink to="/" className="flex items-center gap-2.5 no-underline">
          <Mark />
          <Wordmark className="hidden sm:inline" />
        </NavLink>

        <nav aria-label="Views" className="-mx-2 hidden grow gap-1 overflow-x-auto px-2 lg:flex">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              className={({ isActive }) =>
                `inline-flex h-12 shrink-0 items-center gap-2 px-3 text-[14px] font-medium whitespace-nowrap no-underline ${
                  isActive
                    ? 'font-semibold text-ink shadow-[inset_0_-2px_0_var(--color-sun)]'
                    : 'text-ink-2 hover:text-ink'
                }`
              }
            >
              <Icon name={n.icon} size={17} className="lg:hidden" aria-hidden="true" />
              <span>{n.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-3">
          <span className="hidden xl:inline">
            <SampleDataBadge provenance={provenance} />
          </span>
          <Segmented options={FACES} value={face} onChange={setFace} label="Audience" pill />
          <button
            type="button"
            aria-pressed={theme === 'light'}
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            className="h-12 rounded-control border border-line-strong px-3 text-[13px] font-semibold text-ink hover:bg-inset"
            aria-label={theme === 'dark' ? 'Switch to the light theme' : 'Switch to the dark theme'}
            title="Both themes pass contrast. The light one is for print and projection."
          >
            {theme === 'dark' ? 'Light' : 'Dark'}
          </button>
          <button
            type="button"
            aria-pressed={motion === 'reduced'}
            onClick={() => setMotion(motion === 'full' ? 'reduced' : 'full')}
            className="hidden h-12 rounded-control border border-line-strong px-3 text-[13px] font-semibold text-ink hover:bg-inset lg:inline-flex lg:items-center"
            aria-label={motion === 'full' ? 'Reduce motion' : 'Turn motion back on'}
            title="Every animation has a named static fallback."
          >
            {motion === 'full' ? 'Reduce motion' : 'Motion on'}
          </button>
        </div>
      </header>

      <main id="pw-main" tabIndex={-1} className="flex grow flex-col outline-none">
        {children}
      </main>

      <nav
        aria-label="Views"
        className="flex shrink-0 border-t border-line lg:hidden"
      >
        {NAV.slice(0, 4).map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            className={({ isActive }) =>
              `flex h-16 grow flex-col items-center justify-center gap-1 no-underline ${
                isActive ? 'text-sun' : 'text-ink-3'
              }`
            }
          >
            <Icon name={n.icon} size={22} strokeWidth={1.7} />
            <span className="text-[11px] font-semibold">{n.label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
