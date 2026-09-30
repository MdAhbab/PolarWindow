import { useEffect, useRef, type ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { useMission } from '../lib/store'
import { useKeyboardMap } from '../hooks/useKeyboard'
import { useReducedMotion } from '../hooks/useMotion'
import { Icon, Mark, Wordmark } from './Icon'
import { useProvenance } from '../lib/useProvenance'
import { IconButton, SampleDataBadge, SvgDefs } from './ui'
import { ConnectionBanner, ErrorBoundary, useOnline } from './States'
import { Toaster } from './Toast'
import { RunLogDrawer } from './RunLog'
import { SettingsSheet } from './SettingsSheet'
import { GuideBar } from './GuideBar'
import { useGuide } from '../lib/guide'
import { ESTIMATES, isoDateWords } from '../lib/format'
import { snapshotCapturedAt } from '../lib/api/snapshot'

/**
 * Two views: the missions, and the landing sites with their four pages.
 * A mission's six steps live inside its own page; the skyline and the report
 * are reached from Site and keep their routes.
 */
const VIEWS = [
  { to: '/missions', label: 'Missions', icon: 'pin' as const, match: (p: string) => p.startsWith('/missions') },
  { to: '/map', label: 'Landing sites', icon: 'layers' as const, match: (p: string) => SITE_PATHS.some((s) => p.startsWith(s)) },
]

/** The landing-site pages, as tabs under the header while one is open. */
const SITE_PAGES = [
  { to: '/map', label: 'Map' },
  { to: '/site', label: 'Site' },
  { to: '/compare', label: 'Compare' },
  { to: '/plan', label: 'Plan' },
]
const SITE_PATHS = ['/map', '/site', '/compare', '/plan', '/skyline', '/report']

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
  const previous = useRef(pathname)
  useEffect(() => {
    const before = previous.current
    previous.current = pathname
    // A mission's hub names its own page ("IM-2, Trip"), once its record is in.
    if (!missionOf(pathname)) document.title = `${TITLES[pathname] ?? 'POLAR WINDOW'} · POLAR WINDOW`
    // The first page, and the second run React's strict mode makes of this
    // effect in development, are not a move: focus stays where the browser put it.
    if (first.current || before === pathname) {
      first.current = false
      return
    }
    // Moving between one mission's six steps is a move inside one page, like
    // a tab: focus stays on the step that was pressed, so the next one is one
    // arrow or Tab away. Anywhere else, focus goes to the new content.
    const onStep = (p: string) => /^\/missions\/[^/]+\/[^/]+/.test(p)
    if (onStep(pathname) && onStep(before) && missionOf(pathname) === missionOf(before)) return
    // A new page starts at its top. Focus without the browser's own scroll,
    // which would bring main's middle into view on a long page.
    document.getElementById('pw-main')?.focus({ preventScroll: true })
    window.scrollTo(0, 0)
  }, [pathname])
}

/** The mission a path is about, for `/missions/:id` and its steps. */
function missionOf(pathname: string): string | null {
  return pathname.match(/^\/missions\/([^/]+)/)?.[1] ?? null
}

export function AppShell({ children }: { children: ReactNode }) {
  const provenance = useProvenance()
  const capturedAt = snapshotCapturedAt()
  const online = useOnline()
  const { pathname } = useLocation()
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
  const inSites = SITE_PATHS.some((p) => pathname.startsWith(p))
  const saved = provenance === 'snapshot'

  return (
    <div className="flex min-h-full flex-col bg-canvas text-ink">
      <SvgDefs />
      <a
        href="#pw-main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:bg-raised focus:px-4 focus:py-3"
      >
        Skip to the content
      </a>

      <header className="pw-page flex shrink-0 items-center gap-x-8 border-b border-line bg-canvas py-1.5">
        <NavLink to="/missions" viewTransition className="flex h-12 shrink-0 items-center gap-2.5 no-underline" aria-label="POLAR WINDOW, CLPS missions">
          <Mark />
          <Wordmark />
        </NavLink>

        <nav aria-label="Views" className="hidden h-12 items-stretch gap-1 lg:flex">
          {VIEWS.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              viewTransition
              aria-current={n.match(pathname) ? 'page' : undefined}
              className={`inline-flex shrink-0 items-center px-3 text-control whitespace-nowrap no-underline transition-colors duration-[var(--pw-dur-quick)] ${
                n.match(pathname) ? 'font-semibold text-ink shadow-tab' : 'font-medium text-ink-2 hover:text-ink'
              }`}
            >
              {n.label}
            </NavLink>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            aria-pressed={guideOpen}
            aria-label="Guide"
            onClick={() => setGuideOpen(!guideOpen)}
            title={guideOpen ? 'Hide the guide' : 'Show the guide: a short tour of every feature'}
            className="inline-flex h-12 min-w-12 items-center justify-center gap-2 rounded-control border border-line-strong px-3 text-body font-semibold text-ink transition-colors duration-[var(--pw-dur-quick)] hover:bg-inset aria-pressed:bg-inset"
          >
            <Icon name="info" size={18} aria-hidden="true" />
            <span className="hidden sm:inline">Guide</span>
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

      {/* Said only when it matters: live measurements are the normal case, so
          the line appears offline, for a saved copy, partial data or no data. */}
      <ConnectionBanner
        offline={!online}
        saved={saved}
        savedOn={capturedAt ? isoDateWords(capturedAt) : undefined}
        badge={
          provenance !== 'measured' ? (
            <SampleDataBadge
              provenance={provenance}
              note={saved && capturedAt ? `Saved ${isoDateWords(capturedAt)}.` : undefined}
            />
          ) : undefined
        }
      />

      {inSites && (
        <nav aria-label="Landing site pages" className="pw-page flex border-b border-line">
          {SITE_PAGES.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              viewTransition
              className={({ isActive }) =>
                `inline-flex h-12 min-w-0 grow basis-0 items-center justify-center px-3 text-body whitespace-nowrap no-underline transition-colors duration-[var(--pw-dur-quick)] sm:grow-0 sm:basis-auto ${
                  isActive ? 'font-semibold text-ink shadow-tab' : 'font-medium text-ink-2 hover:text-ink'
                }`
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
      )}

      {/* Below lg the fixed tab bar, and at every width the guide bar when it
          is open, must never cover the last line. */}
      <main
        id="pw-main"
        tabIndex={-1}
        className="flex grow flex-col pb-[calc(4rem+var(--pw-guide-h,0px))] outline-none lg:pb-[var(--pw-guide-h,0px)]"
      >
        <ErrorBoundary resetKey={pathname}>{children}</ErrorBoundary>
        {/* U13: one line per screen instead of "≈" before every value. */}
        <p className="pw-page mt-auto border-t border-line py-3 text-caption leading-caption text-ink-3">{ESTIMATES}</p>
      </main>

      {/* On a phone the two views sit at the bottom, in reach of a thumb and
          clear of the home indicator. The open one is marked in ink, with a
          bar and bold words: amber means sunlight. */}
      <nav
        aria-label="Views"
        className="fixed inset-x-0 bottom-0 z-40 flex border-t border-line bg-canvas pb-[env(safe-area-inset-bottom)] lg:hidden"
      >
        {VIEWS.map((n) => {
          const on = n.match(pathname)
          return (
            <NavLink
              key={n.to}
              to={n.to}
              viewTransition
              aria-current={on ? 'page' : undefined}
              className={`relative flex h-16 min-w-0 grow basis-0 flex-col items-center justify-center gap-1 no-underline ${
                on ? 'text-ink' : 'text-ink-3'
              }`}
            >
              {on && <span aria-hidden="true" className="absolute inset-x-6 top-0 h-[3px] bg-ink" />}
              <Icon name={n.icon} size={22} strokeWidth={on ? 2 : 1.7} />
              <span className={`text-caption ${on ? 'font-semibold' : 'font-medium'}`}>{n.label}</span>
            </NavLink>
          )
        })}
      </nav>

      <GuideBar />
      <RunLogDrawer />
      <SettingsSheet />
      <Toaster />
    </div>
  )
}
