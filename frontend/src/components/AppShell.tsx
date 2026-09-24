import { useEffect, useRef, type ReactNode } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { useMission } from '../lib/store'
import { useKeyboardMap } from '../hooks/useKeyboard'
import { useReducedMotion } from '../hooks/useMotion'
import { Icon, Mark, Wordmark } from './Icon'
import { useProvenance } from '../lib/useProvenance'
import { IconButton, SampleDataBadge, Segmented, SvgDefs } from './ui'
import { RunLogDrawer } from './RunLog'
import { SettingsSheet } from './SettingsSheet'
import type { Face } from '../lib/types'
import { ESTIMATES } from '../lib/format'

/**
 * The five tabs (§10.1), in order. Horizon is reached from Site ("See the
 * skyline") and Report from Site and Mission detail; both keep their routes.
 */
const NAV = [
  { to: '/missions', label: 'Missions', icon: 'pin' as const },
  { to: '/map', label: 'Map', icon: 'layers' as const },
  { to: '/clocks', label: 'Site', icon: 'clocks' as const },
  { to: '/compare', label: 'Compare', icon: 'compare' as const },
  { to: '/blackout', label: 'Blackout', icon: 'gap' as const },
]

const TITLES: Record<string, string> = {
  '/missions': 'CLPS missions',
  '/map': 'Map',
  '/clocks': 'Site',
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
    const title = TITLES[pathname] ?? (pathname.startsWith('/missions/') ? 'Mission' : 'POLAR WINDOW')
    document.title = `${title} — POLAR WINDOW`
    if (first.current) {
      first.current = false
      return
    }
    document.getElementById('pw-main')?.focus()
  }, [pathname])
}

/**
 * How much detail, not who you are (U15): people choose by task, not by job
 * title. The three faces underneath are unchanged; Simple is the default.
 */
export const FACES: { value: Face; label: string }[] = [
  { value: 'public', label: 'Simple' },
  { value: 'educator', label: 'Explain' },
  { value: 'planner', label: 'Expert' },
]

export function AppShell({ children }: { children: ReactNode }) {
  const provenance = useProvenance()
  // Selectors, not the whole store: during M1 the cursor changes sixty times a
  // second, and a whole-store subscription re-rendered the shell on each one.
  const { face, setFace, theme, setTheme, motion, setMotion, openRunLog, settingsOpen, setSettingsOpen } =
    useMission(
      useShallow((s) => ({
        face: s.face,
        setFace: s.setFace,
        theme: s.theme,
        setTheme: s.setTheme,
        motion: s.motion,
        setMotion: s.setMotion,
        openRunLog: s.openRunLog,
        settingsOpen: s.settingsOpen,
        setSettingsOpen: s.setSettingsOpen,
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
        <NavLink to="/missions" className="flex h-12 items-center gap-2.5 no-underline" aria-label="POLAR WINDOW, CLPS missions">
          <Mark />
          <Wordmark />
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

        {/* Below lg: logo and the two sheet buttons on the first line, the
            provenance badge and the faces on the second. */}
        <div className="order-3 flex w-full flex-wrap items-center gap-x-3 gap-y-2 lg:order-none lg:ml-auto lg:w-auto lg:justify-end">
          <Link to="/story" className="hidden h-12 items-center text-[14px] font-semibold lg:inline-flex">
            Start here
          </Link>
          {/* Once, at every width (U12): the one element that says how much to
              trust everything else. */}
          <SampleDataBadge provenance={provenance} />
          <Segmented options={FACES} value={face} onChange={setFace} label="Detail" pill />
          <button
            type="button"
            aria-pressed={theme === 'light'}
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            className="hidden h-12 rounded-control border border-line-strong px-3 text-[13px] font-semibold text-ink hover:bg-inset xl:inline-flex xl:items-center"
            aria-label={theme === 'dark' ? 'Switch to the light theme' : 'Switch to the dark theme'}
            title="Both themes pass contrast. The light one is for print and projection."
          >
            {theme === 'dark' ? 'Light' : 'Dark'}
          </button>
          <button
            type="button"
            aria-pressed={motion === 'reduced'}
            onClick={() => setMotion(motion === 'full' ? 'reduced' : 'full')}
            className="hidden h-12 rounded-control border border-line-strong px-3 text-[13px] font-semibold text-ink hover:bg-inset xl:inline-flex xl:items-center"
            aria-label={motion === 'full' ? 'Reduce motion' : 'Turn motion back on'}
            title="Every animation has a named static fallback."
          >
            {motion === 'full' ? 'Reduce motion' : 'Motion on'}
          </button>
        </div>
        <div className="ml-auto flex items-center gap-2 lg:ml-0">
          <IconButton
            name="log"
            label="AI activity log"
            haspopup="dialog"
            onClick={(e) => {
              e.currentTarget.focus()
              openRunLog(null)
            }}
          />
          <IconButton
            name="settings"
            label="Settings"
            haspopup="dialog"
            expanded={settingsOpen}
            onClick={(e) => {
              e.currentTarget.focus()
              setSettingsOpen(true)
            }}
          />
        </div>
      </header>

      {/* pb-16 below lg: the fixed tab bar must never cover the last line. */}
      <main id="pw-main" tabIndex={-1} className="flex grow flex-col pb-16 outline-none lg:pb-0">
        {children}
        {/* U13: one line per screen instead of "≈" before every value. */}
        <p className="border-t border-line px-4 py-3 text-[12px] leading-[18px] text-ink-3 lg:px-6">{ESTIMATES}</p>
      </main>

      {/* U3: fixed to the bottom on a phone, all five tabs, clear of the home
          indicator. It used to sit at the end of a 2,366 px page and drop
          Blackout. */}
      <nav
        aria-label="Views"
        className="fixed inset-x-0 bottom-0 z-40 flex border-t border-line bg-canvas pb-[env(safe-area-inset-bottom)] lg:hidden"
      >
        {NAV.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            className={({ isActive }) =>
              `flex h-16 min-w-0 grow basis-0 flex-col items-center justify-center gap-1 no-underline ${
                isActive ? 'text-sun' : 'text-ink-3'
              }`
            }
          >
            <Icon name={n.icon} size={22} strokeWidth={1.7} />
            <span className="text-[11px] font-semibold">{n.label}</span>
          </NavLink>
        ))}
      </nav>

      <RunLogDrawer />
      <SettingsSheet />
    </div>
  )
}
