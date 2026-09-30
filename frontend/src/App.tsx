import { lazy, Suspense, useEffect, useMemo, type ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { ErrorPanel, NotFound, Skeleton } from './components/States'
import { Mark } from './components/Icon'
import { MapScreen } from './screens/MapScreen'
import { TwoClockScreen } from './screens/TwoClockScreen'
import { CompareScreen } from './screens/CompareScreen'
import { HorizonScreen } from './screens/HorizonScreen'
import { BlackoutScreen } from './screens/BlackoutScreen'
import { ReportScreen } from './screens/ReportScreen'
import { MissionsScreen } from './screens/MissionsScreen'
import { MissionHub } from './screens/MissionHub'
import { useMission } from './lib/store'
import { useEngineVersionWatch, useSites } from './lib/api/queries'
import { setSites, hasSite, defaultCompare, getCandidates } from './lib/sites'
import { ApiError } from './lib/api/client'
import { useSession } from './lib/session'

/**
 * The front page is its own chunk: three.js and GSAP are for it alone, and
 * the dashboard should not download them.
 */
const LandingScreen = lazy(() => import('./screens/LandingScreen'))

/**
 * `/` is the front page, open to anyone. Everything else is the dashboard,
 * which needs a session: without one, the visitor goes to the front page and
 * its one button, then on to the page they asked for.
 */
export default function App() {
  return (
    <Routes>
      <Route
        path="/"
        element={
          <Suspense fallback={<FrontPageLoading />}>
            <LandingScreen />
          </Suspense>
        }
      />
      {/* The four ideas the story told now open the front page. */}
      <Route path="/story" element={<Navigate to={{ pathname: '/', hash: '#why' }} replace />} />
      <Route
        path="/*"
        element={
          <RequireSession>
            <Dashboard />
          </RequireSession>
        }
      />
    </Routes>
  )
}

function RequireSession({ children }: { children: ReactNode }) {
  const session = useSession((s) => s.session)
  const location = useLocation()
  if (!session || session.expiresAt <= Date.now()) {
    const next = `${location.pathname}${location.search}`
    return <Navigate to={`/?next=${encodeURIComponent(next)}`} replace />
  }
  return <>{children}</>
}

/**
 * Loads the site registry, then renders.
 *
 * Eight components call `siteById()` synchronously in render, so the registry
 * has to be populated before any screen mounts. Gating here is the smallest
 * change that guarantees it, and it gives the whole application the three
 * states the design already has components for: loading with real progress,
 * an error that says what still works, and an empty state that is not a shrug.
 */
function Dashboard() {
  // Every site, candidates and mission targets alike, so a mission's target
  // resolves by id on Site, Compare, Horizon and Blackout. The Map narrows to
  // the candidates itself.
  const sites = useSites({ kind: 'all' })
  useEngineVersionWatch()
  const setSite = useMission((s) => s.setSite)
  const siteId = useMission((s) => s.siteId)

  // Populate the registry during render, not in an effect.
  //
  // Effects run *after* children render, so an effect here let the routes
  // mount for one frame against an empty registry and `siteById` threw. A
  // useMemo keyed on the data is the correct place: it is idempotent, derived
  // entirely from the query result, and guaranteed to have run before anything
  // below it reads the registry.
  useMemo(() => {
    if (sites.data) setSites(sites.data.items.map((i) => i.site))
  }, [sites.data])

  // Selection repair belongs in an effect, because it *is* a state update.
  // The default site and compare set are guesses until the list arrives; if
  // they are not in the dataset, fall back rather than render nothing.
  useEffect(() => {
    if (!sites.data?.items.length) return
    if (!hasSite(siteId)) setSite((getCandidates()[0] ?? sites.data.items[0].site).id)
    const compare = defaultCompare()
    if (compare.length >= 2) useMission.setState({ compareIds: compare })
  }, [sites.data, siteId, setSite])

  if (sites.isPending) {
    return (
      <AppShell>
        <div className="pw-page flex flex-col gap-6 py-6" aria-busy="true">
          <span className="sr-only" role="status">
            Loading the missions and landing sites
          </span>
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-9 w-72 max-w-full" />
          <div className="grid gap-4 lg:grid-cols-2">
            <Skeleton className="h-80" />
            <Skeleton className="h-80" />
          </div>
        </div>
      </AppShell>
    )
  }

  if (sites.error) {
    const e = sites.error as ApiError
    return (
      <AppShell>
        <div className="mx-auto w-full max-w-2xl p-8">
          <ErrorPanel
            title={e.title ?? 'Cannot load the site list'}
            detail={e.detail ?? String(sites.error)}
            stillWorks={
              e.stillWorks ??
              'The interface is loaded. Nothing has been computed incorrectly. There is simply nothing to compute against yet.'
            }
            onRetry={() => void sites.refetch()}
          />
        </div>
      </AppShell>
    )
  }

  if (!sites.data?.items.length) {
    return (
      <AppShell>
        <div className="mx-auto w-full max-w-2xl p-8">
          <ErrorPanel
            title="No candidate sites have been surveyed"
            detail="The service is running but its site table is empty. Sites are seeded from the lunar south polar elevation model before the first run."
            stillWorks="The service itself is healthy; this is a data-loading step, not a failure."
            onRetry={() => void sites.refetch()}
          />
        </div>
      </AppShell>
    )
  }

  return (
    <AppShell>
      <Routes>
        <Route path="/missions" element={<MissionsScreen />} />
        {/* A mission's hub: Landing by default, or one of its six steps. */}
        <Route path="/missions/:id/*" element={<MissionHub />} />
        <Route path="/map" element={<MapScreen />} />
        <Route path="/site" element={<TwoClockScreen />} />
        <Route path="/compare" element={<CompareScreen />} />
        <Route path="/skyline" element={<HorizonScreen />} />
        <Route path="/plan" element={<BlackoutScreen />} />
        <Route path="/report" element={<ReportScreen />} />
        {/* The old addresses, so a saved link still lands on its page. */}
        <Route path="/clocks" element={<Navigate to="/site" replace />} />
        <Route path="/horizon" element={<Navigate to="/skyline" replace />} />
        <Route path="/blackout" element={<Navigate to="/plan" replace />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </AppShell>
  )
}

/** While the front page's own chunk (the Moon) downloads: the name, not a blank screen. */
function FrontPageLoading() {
  return (
    <div className="flex min-h-full flex-col items-center justify-center gap-4 bg-canvas text-ink" aria-busy="true">
      <Mark />
      <p role="status" className="text-small text-ink-3">
        Opening POLAR WINDOW…
      </p>
    </div>
  )
}
