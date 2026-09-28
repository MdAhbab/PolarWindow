import { lazy, Suspense, useEffect, useRef } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { useMission as useMissionQuery } from '../lib/api/queries'
import { useSections } from '../lib/api/lifecycleQueries'
import { ApiError } from '../lib/api/client'
import type { SectionId } from '../lib/api/lifecycle'
import type { MissionDetail } from '../lib/api/adapters'
import { JourneyBar, SECTIONS } from '../components/lifecycle/JourneyBar'
import { OldFeedsNote } from '../components/lifecycle/OldFeeds'
import { LoadingPanel, ProblemPanel } from '../components/States'
import { LandingSection, initialWindow } from './MissionDetailScreen'
import { useMission as useStore } from '../lib/store'

/**
 * The five new steps load when first opened, so the mission list and Landing
 * (the demo path) download none of their charts and forms.
 */
const ReadySection = lazy(() => import('./sections/ReadySection').then((m) => ({ default: m.ReadySection })))
const LaunchSection = lazy(() => import('./sections/LaunchSection').then((m) => ({ default: m.LaunchSection })))
const TripSection = lazy(() => import('./sections/TripSection').then((m) => ({ default: m.TripSection })))
const ContactSection = lazy(() => import('./sections/ContactSection').then((m) => ({ default: m.ContactSection })))
const ReturnSection = lazy(() => import('./sections/ReturnSection').then((m) => ({ default: m.ReturnSection })))

const IDS = new Set<string>(SECTIONS.map((s) => s.id))

/**
 * A mission's hub (design-lifecycle.md §1): its name, the six steps from
 * getting ready to coming home, and one step at a time. `/missions/:id` opens
 * on Landing, the page this product began with, so every older link still
 * lands where it did; `/missions/:id/<step>` opens that step.
 */
export function MissionHub() {
  const params = useParams()
  const id = params.id
  const rest = (params['*'] ?? '').replace(/\/+$/, '')
  const section: SectionId | null = rest === '' ? 'landing' : IDS.has(rest) ? (rest as SectionId) : null
  const navigate = useNavigate()
  const q = useMissionQuery(id)
  const sections = useSections(id)
  const m = q.data
  const setWindow = useStore((s) => s.setWindow)
  const applied = useRef<string | null>(null)

  // A mission sets the dates to its time on the surface (system-design
  // §10.6), once per mission and whichever step is opened first, so Landing
  // and Contact answer for the same dates, and a date the user then picks is
  // not overwritten.
  useEffect(() => {
    if (!m || applied.current === m.id) return
    applied.current = m.id
    const w = initialWindow(m)
    if (w) setWindow(w.startH, w.hours)
  }, [m, setWindow])

  useEffect(() => {
    if (!m || !section) return
    const name = SECTIONS.find((s) => s.id === section)?.name
    document.title = `${m.name}${section === 'landing' && rest === '' ? '' : `, ${name}`} · POLAR WINDOW`
  }, [m, section, rest])

  if (!section) return <Navigate to={`/missions/${encodeURIComponent(id ?? '')}`} replace />

  if (q.isPending) {
    return (
      <div className="grid gap-6 p-4 lg:p-6 xl:grid-cols-12">
        <div className="flex flex-col gap-3 xl:col-span-5" aria-hidden="true">
          {/* Static skeleton lines: motion is reserved for data. */}
          <div className="h-8 w-2/3 bg-inset" />
          <div className="h-4 w-1/2 bg-inset" />
          <div className="h-24 w-full bg-inset" />
          <div className="h-32 w-full bg-inset" />
        </div>
        <div className="xl:col-span-7">
          <LoadingPanel
            done={0}
            total={1}
            title="Loading the mission record"
            unit="records"
            note="The record, its payloads and its sources, then the Sun and Earth at its target."
          />
        </div>
      </div>
    )
  }

  if (q.error || !m) {
    const notFound = q.error instanceof ApiError && q.error.status === 404
    return (
      <div className="mx-auto w-full max-w-2xl p-4 lg:p-8">
        <ProblemPanel
          error={q.error}
          fallbackTitle="That mission isn't in the list"
          onRetry={notFound ? undefined : () => void q.refetch()}
          action={{ label: 'Back to missions', onClick: () => navigate('/missions') }}
        />
      </div>
    )
  }

  const problem = sections.error ? ((sections.error as ApiError).title ?? 'the service did not answer') : undefined

  return (
    <div className="flex grow flex-col gap-5 p-4 lg:p-6">
      <HubHeader mission={m} />
      <JourneyBar
        missionId={m.id}
        current={section}
        statuses={sections.data?.data}
        loading={sections.isPending}
        problem={problem}
      />
      <OldFeedsNote />
      <div className="flex min-w-0 grow flex-col pt-1">
        {section === 'landing' && <LandingSection mission={m} />}
        <Suspense fallback={<div className="h-8 w-2/3 max-w-xl bg-inset" aria-hidden="true" />}>
          {section === 'ready' && <ReadySection mission={m} />}
          {section === 'launch' && <LaunchSection mission={m} />}
          {section === 'trip' && <TripSection mission={m} />}
          {section === 'contact' && <ContactSection mission={m} />}
          {section === 'return' && <ReturnSection mission={m} />}
        </Suspense>
      </div>
    </div>
  )
}

function HubHeader({ mission: m }: { mission: MissionDetail }) {
  return (
    <div className="flex flex-col gap-1">
      <Link to="/missions" className="inline-flex h-11 w-fit items-center text-body font-semibold">
        ← All CLPS missions
      </Link>
      <h1 className="text-heading-lg leading-9 font-semibold tracking-heading">
        {m.name}
        {m.vehicleName && <span className="font-normal text-ink-2"> · {m.vehicleName}</span>}
      </h1>
      <p className="text-body leading-6 text-ink-2">
        {[m.provider, m.lander, m.taskOrder ? `NASA task order ${m.taskOrder}` : null].filter(Boolean).join(' · ') ||
          'Provider not published'}
      </p>
    </div>
  )
}
