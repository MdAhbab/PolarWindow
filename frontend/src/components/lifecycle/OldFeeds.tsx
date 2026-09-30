import type { FeedDTO } from '../../lib/api/lifecycle'
import { useSettingsTab } from '../../lib/settingsTab'
import { useHealth } from '../../lib/api/queries'
import { useFeeds } from '../../lib/api/lifecycleQueries'
import { useSnapshotActive } from '../../lib/api/snapshot'
import { useMission } from '../../lib/store'
import { Icon } from '../Icon'

const joined = (names: string[]) =>
  names.length < 2 ? (names[0] ?? '') : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`

/** A product that has stopped answering: its circuit is open, or its last tries failed. */
const notAnswering = (f: FeedDTO) => f.breaker === 'open' || (typeof f.errors === 'number' && f.errors > 0)

/**
 * Which live feeds are old, by provider, in one quiet sentence; null when none
 * is. Old is the service's own `stale`; a provider whose data is still recent
 * but whose last tries failed is named apart, since its numbers are not old yet.
 */
export function oldFeedsWords(feeds: FeedDTO[]): string | null {
  const name = (f: FeedDTO) => f.provider_name ?? f.provider
  const old = [...new Set(feeds.filter((f) => f.stale).map(name))]
  const failing = [...new Set(feeds.filter((f) => !f.stale && notAnswering(f)).map(name))].filter((n) => !old.includes(n))
  if (!old.length && !failing.length) return null
  const parts = [
    old.length ? `Some live data is older than usual: ${joined(old)}.` : null,
    failing.length
      ? `${joined(failing)} ${failing.length === 1 ? 'is' : 'are'} not answering right now; ${failing.length === 1 ? 'its' : 'their'} data is still recent.`
      : null,
    'Each number from them says how old it is, or why it is missing.',
  ]
  return parts.filter(Boolean).join(' ')
}

/**
 * The hub's note when the service reports itself degraded by its feeds
 * (`/healthz`): which ones, never an alarm. Everything else keeps working, and
 * each number already carries its own age.
 */
export function OldFeedsNote() {
  const live = !useSnapshotActive()
  const health = useHealth()
  const counts = health.data?.feeds
  const show = live && health.data?.status === 'degraded' && Boolean(counts && counts.stale + counts.failing > 0)
  const feeds = useFeeds(show)
  const setSettingsOpen = useMission((s) => s.setSettingsOpen)
  const words = feeds.data ? oldFeedsWords(feeds.data.feeds) : null
  if (!show || !words) return null
  return (
    <p className="flex flex-wrap items-start gap-x-2 gap-y-1 text-small leading-5 text-ink-2">
      <Icon name="uncertain" size={14} strokeWidth={2.2} className="mt-0.5 shrink-0 text-ink-3" aria-hidden="true" />
      <span className="min-w-0 flex-1">
        {words}{' '}
        <button type="button" onClick={() => {
            useSettingsTab.getState().setTab('sources')
            setSettingsOpen(true)
          }} className="min-h-11 font-semibold text-ink underline underline-offset-2 sm:min-h-0">
          See the data sources
        </button>
      </span>
    </p>
  )
}
