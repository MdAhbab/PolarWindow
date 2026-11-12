import { useMemo } from 'react'
import { adaptMission, type Mission } from '../lib/api/adapters'
import { LIVE_SERVICE, nextEvent, useActivity, useSectionsFor } from '../lib/api/home'
import { PROJECTS_OFFLINE, useProjects } from '../lib/api/projects'
import { useMissions } from '../lib/api/queries'
import type { ApiError } from '../lib/api/client'
import { Skeleton } from '../components/States'
import { AskBar } from '../components/home/AskBar'
import { BeingWorkedOut, BlockHeading, LiveLines, NeedsYou } from '../components/home/Blocks'
import { NowOnTheMoon } from '../components/home/NowOnTheMoon'
import { NewProjectCard, ProjectCard, ProjectsEmpty } from '../components/home/ProjectCards'
import { askSuggestions, headline, needsYou, utcDateWords } from '../components/home/model'
import { useNow } from '../components/home/useSunNow'
import { MarkLegend } from '../components/StepStrip'
import { Doors } from '../components/home/Doors'

/** Three CLPS missions worth opening first: the ones still ahead, soonest first, then the rest. */
function toExplore(missions: Mission[], now: number): Mission[] {
  const ahead = missions
    .map((m) => ({ m, ev: nextEvent(m, now) }))
    .filter((x) => x.ev && x.m.origin !== 'project')
    .sort((a, b) => (a.ev?.date.startMs ?? 0) - (b.ev?.date.startMs ?? 0))
    .map((x) => x.m)
  const rest = missions.filter((m) => m.origin !== 'project' && !ahead.includes(m))
  return [...ahead, ...rest].slice(0, 3)
}

/**
 * Home (`/home`, where sign-in lands): what needs the manager today, on one
 * screen. The Moon this minute, their projects with the next dated event and
 * six steps each, what waits on them, what is being worked out, the live
 * feeds, and Ask.
 */
export function HomeScreen() {
  const now = useNow(60_000)
  const projectsQ = useProjects()
  const projects = useMemo(() => (projectsQ.data?.items ?? []).map(adaptMission), [projectsQ.data])
  const ids = useMemo(() => projects.map((p) => p.id), [projects])
  const sections = useSectionsFor(ids)
  const statuses = sections.map((q) => q.data?.data)
  const sectionsLoading = sections.some((q) => q.isPending)
  const activity = useActivity()
  const missions = useMissions({})

  const projectsLoading = !PROJECTS_OFFLINE && projectsQ.isPending
  const needs = needsYou(projects, statuses)
  const needsLoading = projectsLoading || (projects.length > 0 && sectionsLoading)
  const title = PROJECTS_OFFLINE
    ? 'A saved copy of the CLPS missions.'
    : projectsQ.isError
      ? 'Your projects could not be read.'
      : headline(needsLoading ? null : needs.length, LIVE_SERVICE && activity.data ? activity.data.active.length : null)

  return (
    <div className="pw-page flex w-full flex-col gap-12 pt-6 pb-4 lg:gap-14 lg:pt-10">
      <section aria-labelledby="home-title" className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.92fr)] lg:gap-10">
        <div className="flex min-w-0 flex-col gap-7">
          <div className="flex flex-col gap-3">
            <p className="text-small text-ink-2">{utcDateWords(now)}</p>
            <h1 id="home-title" className="pw-display max-w-[22ch] text-display-sm leading-[1.08] text-ink lg:text-display lg:leading-display">
              {title ?? <span className="text-ink-3">Checking your projects…</span>}
            </h1>
            {projectsQ.isError && (
              <p className="max-w-[60ch] text-body leading-6 text-ink-2">
                {(projectsQ.error as ApiError).title ?? 'The service did not answer.'} The missions, sites and Ask still work.
              </p>
            )}
          </div>
          <AskBar suggestions={askSuggestions(projects)} />
          <NeedsYou items={needs} loading={needsLoading} hasProjects={projects.length > 0} />
        </div>
        <NowOnTheMoon projects={projects} />
      </section>

      <Doors />

      <section aria-labelledby="home-projects" className="flex min-w-0 flex-col gap-4">
        <BlockHeading id="home-projects" count={projectsLoading || PROJECTS_OFFLINE ? null : projects.length}>
          Your projects
        </BlockHeading>
        <MarkLegend />
        {projectsLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <Skeleton className="h-52 rounded-card" />
            <Skeleton className="h-52 rounded-card" />
          </div>
        ) : projectsQ.isError ? (
          <ul className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
            <NewProjectCard />
          </ul>
        ) : projects.length ? (
          <ul className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
            {projects.map((p, i) => (
              <ProjectCard key={p.id} project={p} statuses={statuses[i]} loading={sections[i]?.isPending ?? false} now={now} />
            ))}
            <NewProjectCard />
          </ul>
        ) : (
          <ProjectsEmpty explore={toExplore(missions.data?.items ?? [], now)} offline={PROJECTS_OFFLINE} />
        )}
      </section>

      <div className="grid gap-10 lg:grid-cols-2 lg:gap-10">
        <BeingWorkedOut live={LIVE_SERVICE} data={activity.data} pending={activity.isPending} error={activity.error} />
        <LiveLines live={LIVE_SERVICE} />
      </div>
    </div>
  )
}
