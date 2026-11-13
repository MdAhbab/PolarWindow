import { lazy, Suspense, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import type React from 'react'
import { routeDrawn, useTransitionClick } from '../lib/viewTransition'
import { NavLink, useLocation } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { useMission } from '../lib/store'
import { useKeyboardMap } from '../hooks/useKeyboard'
import { useMotionClass, useReducedMotion } from '../hooks/useMotion'
import { LIVE_SERVICE, useActivity } from '../lib/api/home'
import { useAsk, useAskShortcuts } from './ask/store'
import { ASK_DOCK_ID, AskDock } from './ask/AskDock'
import { ActivityRing } from './activity/ActivityRing'
import { ACTIVITY_TRAY_ID, ActivityTray } from './activity/ActivityTray'
import { ringState, useActivityTray } from './activity/model'
import { useActivityToasts } from './activity/useActivityToasts'
import { useArrivals } from '../hooks/useArrivals'
import { Icon } from './Icon'
import { BrandName } from './Brand'
import { useProvenance } from '../lib/useProvenance'
import { Hold, SampleDataBadge, SvgDefs } from './ui'
import { Indicator } from './ui/Indicator'
import { AmbientGlow } from './AmbientGlow'
import { leave } from '../lib/motion'
import { ConnectionBanner, ErrorBoundary, useOnline } from './States'
import { Toaster } from './Toast'
import { RunLogDrawer } from './RunLog'
import { GuideBar } from './GuideBar'
import { useGuide } from '../lib/guide'
import { isoDateWords } from '../lib/format'
import { SourcesAndMethod } from './KindMark'
import { snapshotCapturedAt } from '../lib/api/snapshot'

/** Settings loads the first time it is opened, not with every page. */
const SettingsSheet = lazy(() => import('./SettingsSheet').then((m) => ({ default: m.SettingsSheet })))

/**
 * Three views: Home (what needs the manager today), the missions (projects
 * among them), and the landing sites with their four pages. A mission's six
 * steps live inside its own page; the skyline and the report are reached
 * from Site and keep their routes.
 */
const VIEWS = [
  { to: '/home', label: 'Home', icon: 'home' as const, match: (p: string) => p === '/home' },
  {
    to: '/missions',
    label: 'Missions',
    icon: 'pin' as const,
    match: (p: string) => p.startsWith('/missions') || p.startsWith('/projects'),
  },
  { to: '/map', label: 'Sites', icon: 'layers' as const, match: (p: string) => SITE_PATHS.some((s) => p.startsWith(s)) },
]

/**
 * One item of the phone's bottom bar. Four share it (Home, Missions, Sites,
 * Ask), so the icon sits over its word: "Missions" has room at 320 px, and
 * each item is 48 px tall, over the 44 px a thumb needs.
 */
const BAR_ITEM =
  'pw-press flex h-12 min-w-0 grow basis-0 flex-col items-center justify-center gap-0.5 rounded-pill px-1 text-small leading-4 no-underline'

/** The landing-site pages, as tabs under the header while one is open. */
const SITE_PAGES = [
  { to: '/map', label: 'Map' },
  { to: '/site', label: 'Site' },
  { to: '/compare', label: 'Compare' },
  { to: '/plan', label: 'Plan' },
]
const SITE_PATHS = ['/map', '/site', '/compare', '/plan', '/skyline', '/report']

const TITLES: Record<string, string> = {
  '/home': 'Home',
  '/projects/new': 'New project',
  '/missions': 'Commercial Moon landings (CLPS)',
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
  const askOpen = useAsk((a) => a.isOpen)
  const toggleAsk = useAsk((a) => a.toggle)
  const trayOpen = useActivityTray((t) => t.isOpen)
  const setTrayOpen = useActivityTray((t) => t.setOpen)
  const activity = useActivity()
  useActivityToasts(activity.data)
  useAskShortcuts()
  useKeyboardMap({ reducedMotion: useReducedMotion() })
  useRouteFocus()
  useArrivals('pw-main')
  const inSites = SITE_PATHS.some((p) => pathname.startsWith(p))
  // Once opened, Settings stays mounted, so it can slide out when closed.
  const settingsLoaded = useRef(false)
  if (settingsOpen) settingsLoaded.current = true
  const go = useTransitionClick()
  const saved = provenance === 'snapshot'
  // A page change waits for this before the browser takes its picture of the new page (lib/viewTransition.ts).
  const { key: locationKey } = useLocation()
  useLayoutEffect(() => routeDrawn(), [locationKey])
  // The three rows of choices in the shell, each with one sliding indicator (rule 2).
  const view = VIEWS.find((n) => n.match(pathname))?.to ?? null
  const sitePage = SITE_PAGES.find((n) => pathname === n.to || pathname.startsWith(`${n.to}/`))?.to ?? null

  return (
    <div className="flex min-h-full flex-col text-ink">
      {/* The faint, slow glow behind every page in the app (not the front page). */}
      <AmbientGlow />
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
        {/* Named for page changes, so it holds still over the content as a page changes (rule 5). */}
        <div
          style={{ viewTransitionName: 'pw-island' }}
          className="pw-island pointer-events-auto mx-auto flex w-fit max-w-full items-center gap-1 rounded-pill py-1.5 pr-1.5 pl-1.5 min-[360px]:pl-3 sm:pl-4"
        >
          <NavLink
            to="/home"
            onClick={go('/home')}
            className="flex h-12 min-w-12 shrink-0 items-center justify-center min-[360px]:justify-start gap-2.5 rounded-pill pr-0 min-[360px]:pr-2 sm:pr-3 no-underline"
            aria-label="POLAR WINDOW, Home"
          >
            <BrandName />
          </NavLink>

          <nav aria-label="Views" className="pw-ind-host hidden h-12 items-stretch gap-1 lg:flex">
            {VIEWS.map((n) => {
              const on = n.match(pathname)
              return (
                <NavLink
                  key={n.to}
                  to={n.to}
                  onClick={go(n.to)}
                  aria-current={on ? 'page' : undefined}
                  data-pw-item={n.to}
                  data-pw-on={on || undefined}
                  className={`pw-press inline-flex shrink-0 items-center gap-2 rounded-pill px-4 text-body whitespace-nowrap no-underline ${
                    on ? 'font-semibold text-ink' : 'font-medium text-ink-2 hover:bg-inset hover:text-ink'
                  }`}
                >
                  {/* Room for the dot, which the indicator draws and carries. */}
                  {on && <span aria-hidden="true" className="size-1.5 shrink-0" />}
                  <Hold text={n.label} />
                </NavLink>
              )
            })}
            <Indicator selected={view} tone="inset" mark={16} />
          </nav>

          <span aria-hidden="true" className="mx-1 hidden h-6 w-px bg-line-strong lg:block" />

          <div className="flex items-center gap-1">
            {/* Ask opens the dock; below lg it is the fourth item of the bottom bar instead. */}
            <button
              type="button"
              onClick={toggleAsk}
              aria-expanded={askOpen}
              aria-controls={askOpen ? ASK_DOCK_ID : undefined}
              aria-keyshortcuts="/ Control+K Meta+K"
              title="Ask (/ or Ctrl+K)"
              className="pw-press hidden h-12 items-center gap-2 rounded-pill border border-line-strong bg-tray pr-2 pl-4 text-body font-semibold text-ink hover:border-ink-3 hover:bg-inset aria-expanded:bg-inset lg:inline-flex"
            >
              <Icon name="ask" size={18} strokeWidth={1.9} />
              Ask
              <kbd
                aria-hidden="true"
                className="inline-flex h-7 min-w-7 items-center justify-center rounded-control bg-inset px-1.5 font-mono text-caption font-normal text-ink-3"
              >
                /
              </kbd>
            </button>
            <ActivityRing
              ring={ringState(activity.data)}
              live={LIVE_SERVICE}
              expanded={trayOpen}
              controls={trayOpen ? ACTIVITY_TRAY_ID : undefined}
              onClick={(e) => {
                e.currentTarget.focus()
                setTrayOpen(true)
              }}
            />
            <ShellMenu
              guideOpen={guideOpen}
              onGuide={() => setGuideOpen(!guideOpen)}
              onSettings={() => setSettingsOpen(true)}
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
            aria-label="Landing sites"
            className="pw-ind-host flex w-full max-w-full overflow-x-auto rounded-pill border border-line-strong bg-tray sm:w-fit"
          >
            {SITE_PAGES.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                onClick={go(n.to)}
                data-pw-item={n.to}
                data-pw-on={sitePage === n.to || undefined}
                className={({ isActive }) =>
                  // The chosen page is a pill set 4 px inside its target: a clear border with the
                  // fill kept inside it. The pill is the row's one indicator; it slides (rule 2).
                  `pw-press inline-flex h-[46px] min-w-0 grow basis-0 items-center justify-center rounded-pill border-4 border-transparent bg-clip-padding px-3 text-body whitespace-nowrap no-underline sm:grow-0 sm:basis-auto sm:px-4 ${
                    isActive
                      ? 'font-semibold text-ink'
                      : 'font-medium text-ink-2 hover:text-ink'
                  }`
                }
              >
                <Hold text={n.label} />
              </NavLink>
            ))}
            <Indicator selected={sitePage} inset={4} />
          </nav>
        </div>
      )}

      {/* Below lg the floating bottom bar (72 px from the screen's edge, the home
          indicator's room included), and at every width the guide card when it
          is open, must never cover the last line. From lg the open Ask panel
          sits beside the page, which makes room for it rather than hiding
          under it. */}
      <main
        id="pw-main"
        tabIndex={-1}
        className={`flex grow flex-col pb-[calc(8rem+env(safe-area-inset-bottom)+var(--pw-guide-h,0px))] outline-none lg:pb-[var(--pw-guide-h,0px)] ${
          askOpen ? 'lg:pr-[25.5rem]' : ''
        }`}
      >
        {/* The part that cross-fades when the page changes. On a mission's
            step only the step itself does (MissionHub names it), so the
            header and the step bar hold still. One name per page. */}
        <div className={`flex grow flex-col ${/^\/missions\/[^/]+\/[^/]+/.test(pathname) ? '' : 'pw-content'}`}>
          <ErrorBoundary resetKey={pathname}>{children}</ErrorBoundary>
        </div>
        {/* U13: one line per screen instead of "≈" before every value. */}
        <div className="pw-page mt-auto pt-10 pb-6 text-caption leading-caption text-ink-3">
          <div className="border-t border-line pt-3">
            <SourcesAndMethod />
          </div>
        </div>
      </main>

      {/* On a phone the three views and Ask float at the bottom, in reach of a
          thumb and clear of the home indicator. The open view is filled in ink,
          with bold words: amber means sunlight. */}
      <nav
        aria-label="Views"
        style={{ viewTransitionName: 'pw-bar' }}
        className="pw-island pw-ind-host fixed bottom-[calc(0.75rem+env(safe-area-inset-bottom))] left-1/2 z-40 flex w-[min(24rem,calc(100%-1.5rem))] -translate-x-1/2 gap-1 rounded-pill p-1.5 lg:hidden"
      >
        {/* Each item is one `data-pw-item`, and the row's one indicator sits on the open view. */}
        {VIEWS.map((n) => {
          const on = n.match(pathname)
          return (
            <NavLink
              key={n.to}
              to={n.to}
              onClick={go(n.to)}
              aria-current={on ? 'page' : undefined}
              data-pw-item={n.to}
              data-pw-on={on || undefined}
              className={`${BAR_ITEM} ${on ? 'font-semibold text-ink' : 'font-medium text-ink-2 hover:text-ink'}`}
            >
              <Icon name={n.icon} size={20} strokeWidth={on ? 2 : 1.7} />
              <span className="max-w-full truncate">{n.label}</span>
            </NavLink>
          )
        })}
        {/* Ask, the fourth item: a button that opens the same dock the header's does (a
            sheet on a phone), looking like the three views but never the page's open one. */}
        <button
          type="button"
          onClick={toggleAsk}
          aria-haspopup="dialog"
          aria-expanded={askOpen}
          aria-keyshortcuts="/ Control+K Meta+K"
          data-pw-item="ask"
          className={`${BAR_ITEM} font-medium text-ink-2 hover:text-ink aria-expanded:font-semibold aria-expanded:text-ink`}
        >
          <Icon name="ask" size={20} strokeWidth={1.7} />
          <span className="max-w-full truncate">Ask</span>
        </button>
        <Indicator selected={view} />
      </nav>

      <GuideBar />
      <AskDock />
      <RunLogDrawer />
      <ActivityTray open={trayOpen} onClose={() => setTrayOpen(false)} live={LIVE_SERVICE} feed={activity} />
      {settingsLoaded.current && (
        <Suspense fallback={null}>
          <SettingsSheet />
        </Suspense>
      )}
      <Toaster />
    </div>
  )
}

/**
 * Guide and Settings, in one menu at the end of the island. A menu button
 * (WAI-ARIA menu pattern): Enter, Space or the down arrow opens it on the
 * first item, the arrows move, Esc closes it and returns to the button, and
 * Tab or a click elsewhere closes it.
 */
function ShellMenu({
  guideOpen,
  onGuide,
  onSettings,
}: {
  guideOpen: boolean
  onGuide: () => void
  onSettings: () => void
}) {
  const [open, setOpen] = useState(false)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const id = useId()
  // The menu grows out of its button and leaves the same way, in half the time (rule 1).
  const pop = useMotionClass('pw-pop')
  const reduced = useReducedMotion()
  const close = () => {
    leave(menuRef.current, 'pw-pop-out', reduced)
    setOpen(false)
  }
  const closeRef = useRef(close)
  closeRef.current = close

  useEffect(() => {
    if (!open) return
    menuRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus()
    const away = (e: PointerEvent) => {
      const t = e.target as Node
      if (!menuRef.current?.contains(t) && !buttonRef.current?.contains(t)) closeRef.current()
    }
    document.addEventListener('pointerdown', away)
    return () => document.removeEventListener('pointerdown', away)
  }, [open])

  const items = () => [...(menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])]
  const onMenuKey = (e: React.KeyboardEvent) => {
    const list = items()
    const i = list.indexOf(document.activeElement as HTMLElement)
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      const n = list.length
      list[(i + (e.key === 'ArrowDown' ? 1 : n - 1)) % n]?.focus()
    } else if (e.key === 'Home' || e.key === 'End') {
      e.preventDefault()
      list[e.key === 'Home' ? 0 : list.length - 1]?.focus()
    } else if (e.key === 'Escape') {
      e.preventDefault()
      close()
      buttonRef.current?.focus()
    } else if (e.key === 'Tab') {
      close()
    }
  }
  const choose = (run: () => void) => {
    close()
    // Settings is a dialog: it returns focus to what had it, so the button holds focus first.
    buttonRef.current?.focus()
    run()
  }

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        type="button"
        aria-label="Guide and settings"
        title="Guide and settings"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        data-guide="settings"
        onClick={() => (open ? close() : setOpen(true))}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown' && !open) {
            e.preventDefault()
            setOpen(true)
          }
        }}
        className="pw-press inline-flex size-12 items-center justify-center rounded-pill border border-line-strong bg-tray text-ink hover:border-ink-3 hover:bg-inset aria-expanded:bg-inset"
      >
        <Icon name="menu" size={20} />
      </button>
      {open && (
        <div
          ref={menuRef}
          id={id}
          role="menu"
          aria-label="Guide and settings"
          onKeyDown={onMenuKey}
          data-origin="top"
          // Its button sits at the menu's right end: it grows from that button's centre.
          style={{ ['--pw-origin-x' as string]: 'calc(100% - 24px)' }}
          className={`absolute top-[calc(100%+10px)] right-0 z-50 flex w-64 flex-col rounded-card border border-line-strong bg-raised p-1.5 text-ink shadow-overlay ${pop}`}
        >
          <button type="button" role="menuitem" onClick={() => choose(onGuide)} className="pw-menu-option text-left hover:bg-inset focus-visible:bg-inset">
            <Icon name="info" size={18} strokeWidth={1.8} className="shrink-0" />
            <span className="flex flex-col">
              <span className="font-semibold text-ink">{guideOpen ? 'Hide the guide' : 'Guide'}</span>
              <span className="text-caption leading-caption text-ink-3">A short tour of every feature</span>
            </span>
          </button>
          <button type="button" role="menuitem" aria-haspopup="dialog" onClick={() => choose(onSettings)} className="pw-menu-option text-left hover:bg-inset focus-visible:bg-inset">
            <Icon name="settings" size={18} strokeWidth={1.8} className="shrink-0" />
            <span className="flex flex-col">
              <span className="font-semibold text-ink">Settings</span>
              <span className="text-caption leading-caption text-ink-3">Team, data sources, appearance</span>
            </span>
          </button>
        </div>
      )}
    </div>
  )
}
