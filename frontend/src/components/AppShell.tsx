import { useEffect, useRef, type ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { useMission } from '../lib/store'
import { useKeyboardMap } from '../hooks/useKeyboard'
import { useReducedMotion } from '../hooks/useMotion'
import { Icon, Mark, Wordmark } from './Icon'
import { useProvenance } from '../lib/useProvenance'
import { IconButton, SampleDataBadge, SvgDefs } from './ui'
import { RunLogDrawer } from './RunLog'
import { SettingsSheet } from './SettingsSheet'
import { GuideBar } from './GuideBar'
import { useGuide } from '../lib/guide'
import { ESTIMATES, isoDateWords } from '../lib/format'
import { snapshotCapturedAt } from '../lib/api/snapshot'

/**
 * The five tabs (§10.1), in order. The skyline page is reached from Site
 * ("See the skyline") and the report from Site and Mission detail; both keep
 * their routes.
 */
const NAV = [
  { to: '/missions', label: 'Missions', icon: 'pin' as const },
  { to: '/map', label: 'Map', icon: 'layers' as const },
  { to: '/site', label: 'Site', icon: 'clocks' as const },
  { to: '/compare', label: 'Compare', icon: 'compare' as const },
  { to: '/plan', label: 'Plan', icon: 'gap' as const },
]

const TITLES: Record<string, string> = {
  '/missions': 'CLPS missions',
  '/map': 'Map',
  '/site': 'Site',
  '/compare': 'Compare',
  '/skyline': 'Skyline',
  '/plan': 'Plan for time without contact',
  '/report': 'Printable report',
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
    document.title = `${title} · POLAR WINDOW`
    if (first.current) {
      first.current = false
      return
    }
    document.getElementById('pw-main')?.focus()
  }, [pathname])
}

export function AppShell({ children }: { children: ReactNode }) {
  const provenance = useProvenance()
  const capturedAt = snapshotCapturedAt()
  // Selectors, not the whole store: during M1 the cursor changes sixty times a
  // second, and a whole-store subscription re-rendered the shell on each one.
  const { settingsOpen, setSettingsOpen } = useMission(
    useShallow((s) => ({
      settingsOpen: s.settingsOpen,
      setSettingsOpen: s.setSettingsOpen,
    })),
  )
  const guideOpen = useGuide((g) => g.open)
  const setGuideOpen = useGuide((g) => g.setOpen)
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
                `inline-flex h-12 shrink-0 items-center gap-2 px-3 text-body font-medium whitespace-nowrap no-underline ${
                  isActive
                    ? 'font-semibold text-ink shadow-tab'
                    : 'text-ink-2 hover:text-ink'
                }`
              }
            >
              <Icon name={n.icon} size={17} className="lg:hidden" aria-hidden="true" />
              <span>{n.label}</span>
            </NavLink>
          ))}
        </nav>

        {/* Said only when it matters: live measurements are the normal case,
            so the badge appears for partial data, a saved copy or no data. */}
        {provenance !== 'measured' && (
          <div className="order-3 w-full lg:order-none lg:ml-auto lg:w-auto">
            <SampleDataBadge
              provenance={provenance}
              note={provenance === 'snapshot' && capturedAt ? `Saved ${isoDateWords(capturedAt)}.` : undefined}
            />
          </div>
        )}
        <div className={`ml-auto flex items-center gap-2 ${provenance !== 'measured' ? 'lg:ml-0' : ''}`}>
          <button
            type="button"
            aria-pressed={guideOpen}
            onClick={() => setGuideOpen(!guideOpen)}
            title={guideOpen ? 'Hide the guide' : 'Show the guide: a short tour of every feature'}
            className="inline-flex h-12 items-center gap-2 rounded-control border border-line-strong px-3 text-body font-semibold text-ink hover:bg-inset"
          >
            <Icon name="info" size={18} aria-hidden="true" />
            Guide
          </button>
          <IconButton
            name="settings"
            label="Settings"
            guide="settings"
            haspopup="dialog"
            expanded={settingsOpen}
            onClick={(e) => {
              e.currentTarget.focus()
              setSettingsOpen(true)
            }}
          />
        </div>
      </header>

      {/* Below lg the fixed tab bar, and at every width the guide bar when it
          is open, must never cover the last line. */}
      <main
        id="pw-main"
        tabIndex={-1}
        className="flex grow flex-col pb-[calc(4rem+var(--pw-guide-h,0px))] outline-none lg:pb-[var(--pw-guide-h,0px)]"
      >
        {children}
        {/* U13: one line per screen instead of "≈" before every value. */}
        <p className="border-t border-line px-4 py-3 text-caption leading-caption text-ink-3 lg:px-6">{ESTIMATES}</p>
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
            <span className="text-tag font-semibold">{n.label}</span>
          </NavLink>
        ))}
      </nav>

      <GuideBar />
      <RunLogDrawer />
      <SettingsSheet />
    </div>
  )
}
