import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { ApiError } from '../../lib/api/client'
import type { ActivityDTO } from '../../lib/api/experience.types'
import { useFeeds, useSpaceWeather } from '../../lib/api/lifecycleQueries'
import { Icon } from '../Icon'
import { ProgressTrack, Skeleton } from '../States'
import { Button } from '../ui'
import { STATE_WORDS } from '../lifecycle/JourneyBar'
import { spaceWeatherSentence } from '../lifecycle/SpaceWeather'
import { STATUS_WORDS, progressWords, useActivityTray } from '../activity/model'
import { feedAgesLine, type NeedItem } from './model'

/** A block's heading, with the count of what is in it when that is known. */
export function BlockHeading({ id, children, count }: { id: string; children: ReactNode; count?: number | null }) {
  return (
    <h2 id={id} className="flex items-baseline gap-2.5 text-title-lg font-semibold tracking-title text-ink">
      {children}
      {typeof count === 'number' && <span className="tnum text-body font-normal text-ink-3">{count}</span>}
    </h2>
  )
}

/** Steps across the manager's projects that wait on them, each one click from the form or a scenario. */
export function NeedsYou({ items, loading, hasProjects }: { items: NeedItem[]; loading: boolean; hasProjects: boolean }) {
  return (
    <section aria-labelledby="home-needs" className="flex min-w-0 flex-col gap-3">
      <BlockHeading id="home-needs" count={loading ? null : items.length}>
        Needs you
      </BlockHeading>
      {loading ? (
        <Skeleton className="h-28 rounded-card" />
      ) : !items.length ? (
        <p className="text-body leading-6 text-ink-2">
          {hasProjects
            ? 'Nothing waits on you: every step of your projects has what it needs, or does not apply.'
            : 'Nothing yet. Once you add a project, any step that is missing an input or has no published data is listed here.'}
        </p>
      ) : (
        <ul className="pw-card pw-card-quiet pw-rows flex flex-col">
          {items.map((n) => {
            const w = STATE_WORDS[n.state]
            return (
              <li key={n.key} className="pw-row flex flex-col gap-2 px-4 py-3.5 sm:flex-row sm:items-center sm:gap-4">
                <div className="flex min-w-0 grow items-start gap-3">
                  <Icon name={w.icon} size={16} strokeWidth={2.2} className="mt-0.5 shrink-0 text-ink" />
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <p className="text-body leading-5 text-ink">
                      <span className="font-semibold">{n.missionName}</span>, {n.stepName}: {w.words.toLowerCase()}
                    </p>
                    {n.summary && <p className="text-small leading-5 text-ink-3">{n.summary}</p>}
                  </div>
                </div>
                <Link
                  to={n.href}
                  className="pw-press ml-7 inline-flex h-11 shrink-0 items-center gap-2 self-start rounded-pill border border-line-strong bg-tray px-4 text-body font-semibold text-ink no-underline hover:bg-inset sm:ml-0 sm:self-center"
                >
                  {n.action}
                  <span className="sr-only">
                    : {n.missionName}, {n.stepName}
                  </span>
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

/** What is being worked out right now, from the same feed as the shell's ring. */
export function BeingWorkedOut({
  live,
  data,
  pending,
  error,
}: {
  live: boolean
  data: ActivityDTO | undefined
  pending: boolean
  error: unknown
}) {
  const setTray = useActivityTray((s) => s.setOpen)
  const active = data?.active ?? []
  return (
    <section aria-labelledby="home-working" className="flex min-w-0 flex-col gap-3">
      <BlockHeading id="home-working" count={live && data ? active.length : null}>
        Being worked out
      </BlockHeading>
      {!live ? (
        <p className="text-body leading-6 text-ink-2">Nothing is worked out in a saved copy, so there is nothing to follow here.</p>
      ) : pending ? (
        <Skeleton className="h-20 rounded-card" />
      ) : error || !data ? (
        <p className="text-body leading-6 text-ink-2">
          The activity list could not be read: {(error as ApiError | null)?.title ?? 'the service did not answer'}. Each page still shows its
          own progress.
        </p>
      ) : !active.length ? (
        <p className="text-body leading-6 text-ink-2">
          Nothing right now.
          {data.recent.length ? ` ${data.recent.length} finished in the last 15 minutes.` : ''}
        </p>
      ) : (
        <ul className="pw-card pw-card-quiet pw-rows flex flex-col">
          {active.slice(0, 4).map((a) => {
            const p = progressWords(a)
            return (
              <li key={a.key} className="pw-row flex flex-col gap-2 px-4 py-3.5">
                <p className="flex items-start gap-3 text-body leading-5 text-ink">
                  <Icon name={STATUS_WORDS[a.status].icon} size={16} strokeWidth={2.2} className="mt-0.5 shrink-0 text-ink-2" />
                  <span className="min-w-0">
                    {a.href ? (
                      <Link to={a.href} className="font-semibold text-ink underline underline-offset-[3px]">
                        {a.label}
                      </Link>
                    ) : (
                      <span className="font-semibold">{a.label}</span>
                    )}
                    <span className="text-ink-2">
                      , {STATUS_WORDS[a.status].words.toLowerCase()}
                      {p ? `, ${p}` : ''}
                    </span>
                  </span>
                </p>
                <div className="pl-7">
                  <ProgressTrack
                    label={`Progress of ${a.label}`}
                    fraction={typeof a.progress === 'number' ? a.progress : null}
                    now={typeof a.progress === 'number' ? Math.round(a.progress * 100) : undefined}
                    valueText={p ?? STATUS_WORDS[a.status].words}
                  />
                </div>
              </li>
            )
          })}
        </ul>
      )}
      {live && (
        <Button size="sm" variant="ghost" className="self-start" onClick={() => setTray(true)}>
          Open activity
        </Button>
      )}
    </section>
  )
}

/** Space weather now and the feeds' ages, one line each. A saved copy has neither, and says so. */
export function LiveLines({ live }: { live: boolean }) {
  const sw = useSpaceWeather(live)
  const feeds = useFeeds(live)
  const swLine = !live
    ? 'Not in a saved copy: space weather is read live.'
    : sw.isPending
      ? 'Reading…'
      : sw.data
        ? spaceWeatherSentence(sw.data.data, sw.data.meta)
            .replace(/^Now: /, '')
            .replace(/ Each says why below\.$/, '')
        : `Could not be read: ${(sw.error as ApiError | null)?.title ?? 'the service did not answer'}.`
  const ages = feeds.data ? feedAgesLine(feeds.data.feeds) : null
  const feedLine = !live
    ? 'Not in a saved copy: the saved data carries its own date.'
    : feeds.isPending
      ? 'Reading…'
      : feeds.data
        ? (ages ?? 'No feeds are listed yet.')
        : `Could not be read: ${(feeds.error as ApiError | null)?.title ?? 'the service did not answer'}.`
  return (
    <section aria-labelledby="home-live" className="flex min-w-0 flex-col gap-3">
      <BlockHeading id="home-live">Live</BlockHeading>
      <dl className="pw-card pw-card-quiet grid grid-cols-1 gap-x-5 gap-y-3 p-4 text-body leading-6 sm:grid-cols-[max-content_minmax(0,1fr)] sm:p-5">
        <dt className="font-semibold text-ink">Space weather</dt>
        <dd className="text-ink-2">{swLine}</dd>
        <dt className="font-semibold text-ink">Data age</dt>
        <dd className="text-ink-2">{feedLine}</dd>
      </dl>
    </section>
  )
}
