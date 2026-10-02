import { lazy, Suspense, useEffect, useRef, type ReactNode } from 'react'
import { useTransitionClick } from '../lib/viewTransition'
import { NavLink, useLocation } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { useMission } from '../lib/store'
import { useKeyboardMap } from '../hooks/useKeyboard'
import { useReducedMotion } from '../hooks/useMotion'
import { useArrivals } from '../hooks/useArrivals'
import { Icon } from './Icon'
import { BrandName } from './Brand'
import { useProvenance } from '../lib/useProvenance'
import { IconButton, SampleDataBadge, SvgDefs } from './ui'
import { ConnectionBanner, ErrorBoundary, useOnline } from './States'
import { Toaster } from './Toast'
import { RunLogDrawer } from './RunLog'
import { GuideBar } from './GuideBar'
import { useGuide } from '../lib/guide'
import { ESTIMATES, isoDateWords } from '../lib/format'
import { snapshotCapturedAt } from '../lib/api/snapshot'

/** Settings loads the first time it is opened, not with every page. */
const SettingsSheet = lazy(() => import('./SettingsSheet').then((m) => ({ default: m.SettingsSheet })))

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
  useArrivals('pw-main')
  const inSites = SITE_PATHS.some((p) => pathname.startsWith(p))
  // Once opened, Settings stays mounted, so it can slide out when closed.
  const settingsLoaded = useRef(false)
  if (settingsOpen) settingsLoaded.current = true
  const go = useTransitionClick()
  const saved = provenance === 'snapshot'

  return (
    <div className="flex min-h-full flex-col text-ink">
      <SvgDefs />
      <a
        href="#pw-main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-pill focus:bg-raised focus:px-5 focus:py-3"
      >
        Skip to the content
      </a>

      {/* The island: one floating strip for the mark, the two views and the
          two tools, instead of a full-width bar (decision D3). It stays in
          reach as the page scrolls under it; the space around it lets clicks
          through to the page. */}
      <header className="pointer-events-none sticky top-0 z-40 px-3 pt-3 sm:px-4">
        <div className="pw-island pointer-events-auto mx-auto flex w-fit max-w-full items-center gap-1 rounded-pill py-1.5 pr-1.5 pl-3 sm:pl-4">
          <NavLink
            to="/missions"
            onClick={go('/missions')}
            className="flex h-12 shrink-0 items-center gap-2.5 rounded-pill pr-2 no-underline sm:pr-3"
            aria-label="POLAR WINDOW, CLPS missions"
          >
            <BrandName />
          </NavLink>

          <nav aria-label="Views" className="hidden h-12 items-stretch gap-1 lg:flex">
            {VIEWS.map((n) => {
              const on = n.match(pathname)
              return (
                <NavLink
                  key={n.to}
                  to={n.to}
                  onClick={go(n.to)}
                  aria-current={on ? 'page' : undefined}
                  className={`pw-press inline-flex shrink-0 items-center gap-2 rounded-pill px-4 text-body whitespace-nowrap no-underline ${
                    on ? 'bg-inset font-semibold text-ink' : 'font-medium text-ink-2 hover:bg-inset hover:text-ink'
                  }`}
                >
                  {on && <span aria-hidden="true" className="size-1.5 rounded-pill bg-ink" />}
                  {n.label}
                </NavLink>
              )
            })}
          </nav>

          <span aria-hidden="true" className="mx-1 hidden h-6 w-px bg-line-strong lg:block" />

          <div className="flex items-center gap-1.5">
            <button
              type="button"
              aria-pressed={guideOpen}
              aria-label="Guide"
              onClick={() => setGuideOpen(!guideOpen)}
              title={guideOpen ? 'Hide the guide' : 'Show the guide: a short tour of every feature'}
              className="pw-press inline-flex h-12 min-w-12 items-center justify-center gap-2 rounded-pill px-3 text-body font-semibold text-ink-2 hover:bg-inset hover:text-ink aria-pressed:bg-inset aria-pressed:text-ink sm:px-4"
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
        // The four landing-site pages, as one pill under the island. It holds
        // still while the page under it changes.
        <div className="pw-page pt-5 sm:pt-6">
          <nav
            aria-label="Landing site pages"
            className="flex w-full max-w-full overflow-x-auto rounded-pill border border-line-strong bg-tray sm:w-fit"
          >
            {SITE_PAGES.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                onClick={go(n.to)}
                className={({ isActive }) =>
                  // The chosen page is a pill set 4 px inside its target: a clear border with the fill kept inside it.
                  `pw-press inline-flex h-[46px] min-w-0 grow basis-0 items-center justify-center rounded-pill border-4 border-transparent bg-clip-padding px-3 text-body whitespace-nowrap no-underline sm:grow-0 sm:basis-auto sm:px-4 ${
                    isActive
                      ? 'bg-ink font-semibold text-canvas'
                      : 'font-medium text-ink-2 hover:text-ink'
                  }`
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
        </div>
      )}

      {/* Below lg the floating dock, and at every width the guide card when it
          is open, must never cover the last line. */}
      <main
        id="pw-main"
        tabIndex={-1}
        className="flex grow flex-col pb-[calc(6rem+env(safe-area-inset-bottom)+var(--pw-guide-h,0px))] outline-none lg:pb-[var(--pw-guide-h,0px)]"
      >
        {/* The part that cross-fades when the page changes. On a mission's
            step only the step itself does (MissionHub names it), so the
            header and the step bar hold still. One name per page. */}
        <div className={`flex grow flex-col ${/^\/missions\/[^/]+\/[^/]+/.test(pathname) ? '' : 'pw-content'}`}>
          <ErrorBoundary resetKey={pathname}>{children}</ErrorBoundary>
        </div>
        {/* U13: one line per screen instead of "≈" before every value. */}
        <p className="pw-page mt-auto pt-10 pb-6 text-caption leading-caption text-ink-3">
          <span className="block border-t border-line pt-5">{ESTIMATES}</span>
        </p>
      </main>

      {/* On a phone the two views float at the bottom, in reach of a thumb and
          clear of the home indicator. The open one is filled in ink, with bold
          words: amber means sunlight. */}
      <nav
        aria-label="Views"
        className="pw-island fixed bottom-[calc(0.75rem+env(safe-area-inset-bottom))] left-1/2 z-40 flex w-[min(22rem,calc(100%-1.5rem))] -translate-x-1/2 gap-1 rounded-pill p-1.5 lg:hidden"
      >
        {VIEWS.map((n) => {
          const on = n.match(pathname)
          return (
            <NavLink
              key={n.to}
              to={n.to}
              onClick={go(n.to)}
              aria-current={on ? 'page' : undefined}
              className={`pw-press flex h-12 min-w-0 grow basis-0 items-center justify-center gap-2 rounded-pill px-3 text-body no-underline ${
                on ? 'bg-ink font-semibold text-canvas' : 'font-medium text-ink-2 hover:text-ink'
              }`}
            >
              <Icon name={n.icon} size={19} strokeWidth={on ? 2 : 1.7} />
              <span className="truncate">{n.label}</span>
            </NavLink>
          )
        })}
      </nav>

      <GuideBar />
      <RunLogDrawer />
      {settingsLoaded.current && (
        <Suspense fallback={null}>
          <SettingsSheet />
        </Suspense>
      )}
      <Toaster />
    </div>
  )
}
