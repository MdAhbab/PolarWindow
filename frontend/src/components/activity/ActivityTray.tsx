import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import type { ActivityDTO, ActivityItemDTO } from '../../lib/api/experience.types'
import type { ApiError } from '../../lib/api/client'
import { Icon } from '../Icon'
import { ProgressTrack } from '../States'
import { Sheet } from '../Sheet'
import { Button } from '../ui'
import { STATUS_WORDS, progressWords, whenWords } from './model'

export const ACTIVITY_TRAY_ID = 'pw-activity-tray'

interface FeedState {
  data: ActivityDTO | undefined
  isPending: boolean
  error: unknown
  refetch: () => unknown
}

/** The tray: a sheet from the right, opened from the shell's ring. */
export function ActivityTray({
  open,
  onClose,
  live,
  feed,
}: {
  open: boolean
  onClose: () => void
  live: boolean
  feed: FeedState
}) {
  return (
    <Sheet open={open} onClose={onClose} title="Activity">
      <div id={ACTIVITY_TRAY_ID}>
        <ActivityList live={live} feed={feed} onNavigate={onClose} />
      </div>
    </Sheet>
  )
}

/** "Now" for the item ages, moved on every half minute while the list is shown. */
function useNowEvery(ms: number): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const h = window.setInterval(() => setNow(Date.now()), ms)
    return () => window.clearInterval(h)
  }, [ms])
  return now
}

/**
 * What is being worked out and what just finished, each with its state in a
 * shape and words, its progress, and a link to where the answer is shown.
 * A saved copy calls nothing, and says so.
 */
export function ActivityList({ live, feed, onNavigate }: { live: boolean; feed: FeedState; onNavigate?: () => void }) {
  const now = useNowEvery(30_000)

  if (!live) {
    return (
      <Note
        icon="offline"
        title="This is a saved copy"
        detail="Nothing is worked out in a saved copy, so there is no activity to show. With the live service, every calculation you start appears here with its progress."
      />
    )
  }
  if (feed.isPending) {
    return (
      <p role="status" className="px-5 py-6 text-body text-ink-3 md:px-6">
        Checking what is being worked out…
      </p>
    )
  }
  if (feed.error || !feed.data) {
    const e = feed.error as ApiError | null
    return (
      <div className="flex flex-col items-start gap-4 px-5 py-6 md:px-6">
        <Note
          icon="alert"
          title="The activity list could not be read"
          detail={`${e?.title ?? 'The service did not answer'}. Each page still shows the progress of its own calculation.`}
          flush
        />
        <Button size="sm" onClick={() => void feed.refetch()}>
          Try again
        </Button>
      </div>
    )
  }

  const { active, recent } = feed.data
  if (!active.length && !recent.length) {
    return (
      <Note
        icon="clocks"
        title="Nothing is being worked out"
        detail="Work in progress shows here: launch opportunities, a trip, contact, a new skyline and scenarios. Each stays 15 minutes after it is done. The other pages stay free to use meanwhile."
      />
    )
  }

  return (
    <div className="flex flex-col gap-6 px-5 py-5 md:px-6">
      <Group title="Being worked out" items={active} empty="Nothing right now." now={now} onNavigate={onNavigate} />
      <Group title="Just finished" items={recent} empty="Nothing in the last 15 minutes." now={now} onNavigate={onNavigate} />
    </div>
  )
}

function Note({ icon, title, detail, flush = false }: { icon: 'offline' | 'alert' | 'clocks'; title: string; detail: string; flush?: boolean }) {
  return (
    <div className={`flex items-start gap-3 ${flush ? '' : 'px-5 py-6 md:px-6'}`}>
      <Icon name={icon} size={20} strokeWidth={1.8} className="mt-0.5 shrink-0 text-ink-2" />
      <div className="flex min-w-0 flex-col gap-1">
        <p className="text-control font-semibold text-ink">{title}</p>
        <p className="text-body leading-6 text-ink-2">{detail}</p>
      </div>
    </div>
  )
}

function Group({
  title,
  items,
  empty,
  now,
  onNavigate,
}: {
  title: string
  items: ActivityItemDTO[]
  empty: string
  now: number
  onNavigate?: () => void
}) {
  return (
    <section className="flex flex-col gap-2" aria-label={title}>
      <h3 className="flex items-baseline gap-2 text-body font-semibold text-ink">
        {title}
        <span className="tnum font-normal text-ink-3">{items.length}</span>
      </h3>
      {items.length ? (
        <ul className="pw-card pw-card-quiet pw-rows flex flex-col">
          {items.map((it) => (
            <ActivityRow key={it.key} item={it} now={now} onNavigate={onNavigate} />
          ))}
        </ul>
      ) : (
        <p className="text-small text-ink-3">{empty}</p>
      )}
    </section>
  )
}

function ActivityRow({ item, now, onNavigate }: { item: ActivityItemDTO; now: number; onNavigate?: () => void }) {
  const state = STATUS_WORDS[item.status]
  const progress = progressWords(item)
  const when = whenWords(item, now)
  const working = item.status === 'queued' || item.status === 'running'
  return (
    <li className="pw-row flex flex-col gap-2 px-4 py-3.5">
      <div className="flex items-start gap-3">
        <Icon
          name={state.icon}
          size={16}
          strokeWidth={2.2}
          className={`mt-0.5 shrink-0 ${item.status === 'failed' ? 'text-alert' : 'text-ink-2'}`}
        />
        <div className="flex min-w-0 grow flex-col gap-0.5">
          <p className="text-body leading-5 font-semibold text-ink">{item.label}</p>
          <p className="text-small leading-5 text-ink-2">
            {state.words}
            {progress ? `, ${progress}` : ''}
            {item.mission_name ? ` · ${item.mission_name}` : ''}
            {when ? ` · ${when}` : ''}
          </p>
          {item.message && <p className="text-small leading-5 text-ink-3">{item.message}</p>}
        </div>
      </div>
      {working && (
        <div className="pl-7">
          <ProgressTrack
            label={`Progress of ${item.label}`}
            fraction={typeof item.progress === 'number' ? item.progress : null}
            now={typeof item.progress === 'number' ? Math.round(item.progress * 100) : undefined}
            valueText={progress ?? state.words}
          />
        </div>
      )}
      {item.href && (
        <Link
          to={item.href}
          onClick={onNavigate}
          className="ml-7 inline-flex min-h-11 w-fit items-center gap-1.5 text-body font-semibold text-ink underline underline-offset-[3px] hover:text-ink-2"
        >
          {working ? 'Go to where it will show' : item.status === 'done' ? 'Open the answer' : 'Go to the step'}
          <span className="sr-only">: {item.label}</span>
        </Link>
      )}
    </li>
  )
}
