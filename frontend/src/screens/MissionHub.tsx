import { lazy, Suspense, useEffect, useRef } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { PageHeader } from '../components/Page'
import { Icon } from '../components/Icon'
import { useMission as useMissionQuery } from '../lib/api/queries'
import { useSections } from '../lib/api/lifecycleQueries'
import { ApiError } from '../lib/api/client'
import type { SectionId } from '../lib/api/lifecycle'
import { JourneyBar, SECTIONS, StepCards, sectionPath } from '../components/lifecycle/JourneyBar'
import { OldFeedsNote } from '../components/lifecycle/OldFeeds'
import { ProblemPanel, SectionSkeleton, Skeleton } from '../components/States'
import { MissionRecord, SurfaceSection, initialWindow } from './MissionDetailScreen'
import { useMission as useStore } from '../lib/store'

/**
 * Five of the steps load when first opened, so the mission list and Surface
 * (the demo path) download none of their charts and forms.
 */
const ReadySection = lazy(() => import('./sections/ReadySection').then((m) => ({ default: m.ReadySection })))
const LaunchSection = lazy(() => import('./sections/LaunchSection').then((m) => ({ default: m.LaunchSection })))
const TripSection = lazy(() => import('./sections/TripSection').then((m) => ({ default: m.TripSection })))
const ContactSection = lazy(() => import('./sections/ContactSection').then((m) => ({ default: m.ContactSection })))
const ReturnSection = lazy(() => import('./sections/ReturnSection').then((m) => ({ default: m.ReturnSection })))

/** The address of each step, and the old name for Surface, so a saved link still works. */
const BY_SLUG = new Map<string, SectionId>(SECTIONS.map((s) => [s.slug, s.id]))
BY_SLUG.set('landing', 'landing')

/**
 * A mission's page (design-lifecycle.md, 2026-09-30): its home at
 * `/missions/:id`, with the record and the six steps as cards, each saying its
 * state and one-line answer; and one step at a time at `/missions/:id/<step>`,
 * under the same header with the step bar.
 */
export function MissionHub() {
  const params = useParams()
  const id = params.id
  const rest = (params['*'] ?? '').replace(/\/+$/, '')
  const section: SectionId | 'home' | null = rest === '' ? 'home' : (BY_SLUG.get(rest) ?? null)
  const q = useMissionQuery(id)
  const sections = useSections(id)
  const m = q.data
  const setWindow = useStore((s) => s.setWindow)
  const applied = useRef<string | null>(null)
  const navigate = useNavigate()

  // A mission sets the dates to its time on the surface (system-design
  // §10.6), once per mission and whichever step is opened first, so Surface
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
    document.title = `${m.name}${section === 'home' ? '' : `, ${name}`} · POLAR WINDOW`
  }, [m, section])

  const base = `/missions/${encodeURIComponent(id ?? '')}`
  if (!section) return <Navigate to={base} replace />
  if (rest === 'landing') return <Navigate to={`${base}/surface`} replace />

  if (q.isPending) return <HubSkeleton home={section === 'home'} />

  if (q.error || !m) {
    const notFound = q.error instanceof ApiError && q.error.status === 404
    return (
      <div className="pw-page mx-auto w-full max-w-2xl py-8">
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
  const step = section === 'home' ? null : SECTIONS.find((s) => s.id === section)!
  const i = step ? SECTIONS.indexOf(step) : -1
  const nextStep = i >= 0 && i < SECTIONS.length - 1 ? SECTIONS[i + 1] : null

  return (
    <div className="pw-page flex grow flex-col gap-6 py-5 lg:py-7">
      <PageHeader
        crumbs={
          step
            ? [
                { label: 'Missions', to: '/missions' },
                { label: m.name, to: base },
                { label: step.name },
              ]
            : [{ label: 'Missions', to: '/missions' }, { label: m.name }]
        }
        title={m.name}
        titleExtra={m.vehicleName ? `· ${m.vehicleName}` : undefined}
        lede={
          [m.provider, m.lander, m.taskOrder ? `NASA task order ${m.taskOrder}` : null].filter(Boolean).join(' · ') ||
          'Provider not published'
        }
      />
      {step ? (
        <>
          <JourneyBar
            missionId={m.id}
            current={step.id}
            statuses={sections.data?.data}
            loading={sections.isPending}
            problem={problem}
          />
          <OldFeedsNote />
          <div className="pw-content flex min-w-0 grow flex-col pt-1">
            {step.id === 'landing' && <SurfaceSection mission={m} />}
            <Suspense fallback={<SectionSkeleton />}>
              {step.id === 'ready' && <ReadySection mission={m} />}
              {step.id === 'launch' && <LaunchSection mission={m} />}
              {step.id === 'trip' && <TripSection mission={m} />}
              {step.id === 'contact' && <ContactSection mission={m} />}
              {step.id === 'return' && <ReturnSection mission={m} />}
            </Suspense>
          </div>
          <StepFooter missionId={m.id} base={base} next={nextStep} />
        </>
      ) : (
        <div className="pw-content grid gap-8 xl:grid-cols-12">
          <section aria-labelledby="steps-h" className="flex min-w-0 flex-col gap-3 xl:col-span-8">
            <h2 id="steps-h" className="text-body font-semibold text-ink-2">
              Six steps, from getting ready to coming home
            </h2>
            <StepCards missionId={m.id} statuses={sections.data?.data} loading={sections.isPending} problem={problem} />
            <OldFeedsNote />
          </section>
          <aside aria-label="The mission’s record" className="min-w-0 xl:col-span-4">
            <MissionRecord mission={m} />
          </aside>
        </div>
      )}
    </div>
  )
}

/** The end of a step: the way on to the next one, and back to the mission. */
function StepFooter({ base, next, missionId }: { base: string; missionId: string; next: (typeof SECTIONS)[number] | null }) {
  return (
    <nav aria-label="Next step" className="flex flex-col gap-3 border-t border-line pt-6 sm:flex-row sm:items-stretch sm:justify-between">
      <Link
        to={base}
        viewTransition
        className="inline-flex h-12 items-center gap-2 self-start rounded-control px-1 text-body font-semibold text-ink-2 no-underline hover:text-ink sm:self-center"
      >
        <Icon name="back" size={16} strokeWidth={2} />
        All six steps
      </Link>
      {next && (
        <Link
          to={sectionPath(missionId, next.id)}
          viewTransition
          className="group flex min-w-0 items-center justify-between gap-4 border border-line bg-panel px-5 py-3 no-underline transition-[border-color,box-shadow] duration-[var(--pw-dur-base)] hover:border-line-strong hover:shadow-lift sm:min-w-[340px]"
        >
          <span className="flex min-w-0 flex-col">
            <span className="text-caption text-ink-3">Next step</span>
            <span className="text-control font-semibold text-ink">
              {SECTIONS.indexOf(next) + 1} · {next.name}
            </span>
            <span className="truncate text-small text-ink-3">{next.question}</span>
          </span>
          <Icon
            name="arrow"
            size={18}
            strokeWidth={1.8}
            className="shrink-0 text-ink-3 transition-transform duration-[var(--pw-dur-base)] group-hover:translate-x-1 group-hover:text-ink"
          />
        </Link>
      )}
    </nav>
  )
}

/** The mission's page while its record loads, in the shape it will take. */
function HubSkeleton({ home }: { home: boolean }) {
  return (
    <div className="pw-page flex flex-col gap-6 py-5 lg:py-7" aria-busy="true">
      <span className="sr-only" role="status">
        Loading the mission record
      </span>
      <div className="flex flex-col gap-2">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-9 w-64 max-w-full" />
        <Skeleton className="h-5 w-80 max-w-full" />
      </div>
      {home ? (
        <div className="grid gap-8 xl:grid-cols-12">
          <div className="grid gap-3 sm:grid-cols-2 xl:col-span-8 xl:grid-cols-3">
            {Array.from({ length: 6 }, (_, i) => (
              <Skeleton key={i} className="h-44" />
            ))}
          </div>
          <Skeleton className="h-64 xl:col-span-4" />
        </div>
      ) : (
        <>
          <Skeleton className="h-14" />
          <SectionSkeleton />
        </>
      )}
    </div>
  )
}
