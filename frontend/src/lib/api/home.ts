/**
 * The calls the shell and Home make (docs/experience-plan.md, stream C): the
 * quick Ask chat, the app-wide activity feed, every project's six steps at
 * once, and the small pure helpers Home and the dock share (what the person is
 * looking at, the next dated event). Shapes from ./experience.types.
 */
import { useQueries, useQuery } from '@tanstack/react-query'
import { api, apiRequest } from './client'
import { DATA_MODE } from './snapshot'
import { keys, setLifecycleEngines } from './queries'
import type { PublishedDate } from './adapters'
import type { SectionDTO, SectionId, SectionStatusDTO } from './lifecycle'
import type { ActivityDTO, ChatContextDTO, ChatRequest, ChatResponseDTO } from './experience.types'

/** A saved copy calls nothing: Ask and the activity feed say so instead of asking. */
export const LIVE_SERVICE = DATA_MODE !== 'snapshot'

export const homeApi = {
  chat: (body: ChatRequest, signal?: AbortSignal) =>
    apiRequest<ChatResponseDTO>('/agents/chat', { body, signal, method: 'POST' }),
  activity: (signal?: AbortSignal) => apiRequest<ActivityDTO>('/activity', { signal }),
}

export const ACTIVITY_KEY = ['activity'] as const

/**
 * How long to wait before asking `/activity` again: what the server asks for,
 * kept between 2 s and a minute; a minute after a failure.
 */
export function activityDelay(data: ActivityDTO | undefined, failed = false): number {
  if (failed) return 60_000
  const s = data?.poll_after_s
  const v = typeof s === 'number' && s > 0 ? s : 20
  return Math.min(60, Math.max(2, v)) * 1000
}

/** What is being worked out, app-wide. Asked again gently, and never while the tab is hidden. */
export function useActivity() {
  return useQuery<ActivityDTO>({
    queryKey: ACTIVITY_KEY,
    enabled: LIVE_SERVICE,
    staleTime: 1000,
    retry: false,
    refetchOnWindowFocus: true,
    refetchIntervalInBackground: false,
    refetchInterval: (q) =>
      typeof document !== 'undefined' && document.visibilityState === 'hidden'
        ? false
        : activityDelay(q.state.data, q.state.status === 'error'),
    queryFn: ({ signal }) => homeApi.activity(signal),
  })
}

/** The six steps of several missions at once, sharing the cache with each mission's own page. */
export function useSectionsFor(missionIds: string[]) {
  return useQueries({
    queries: missionIds.map((id) => ({
      queryKey: keys.sections(id),
      staleTime: 60_000,
      retry: false,
      queryFn: async ({ signal }: { signal: AbortSignal }): Promise<SectionDTO<SectionStatusDTO[]>> => {
        const dto = await api.sections(id, signal)
        setLifecycleEngines(dto.meta.engines)
        return dto
      },
    })),
  })
}

/** A step's address word to its id (Surface is `landing` to the service). */
const SLUG_TO_SECTION: Record<string, SectionId> = {
  ready: 'ready',
  launch: 'launch',
  trip: 'trip',
  surface: 'landing',
  landing: 'landing',
  contact: 'contact',
  return: 'return',
}

const SITE_PAGES = ['/map', '/site', '/compare', '/plan', '/skyline', '/report']

/**
 * Where the person is, for the chat: the mission and step a path is about,
 * the scenario open in it, or the site and dates on a site page.
 */
export function chatContextFor(
  pathname: string,
  search: string,
  opts: { siteId?: string | null; start?: string | null; end?: string | null } = {},
): ChatContextDTO {
  const ctx: ChatContextDTO = { path: pathname }
  const m = pathname.match(/^\/missions\/([^/]+)(?:\/([^/]+))?/)
  if (m) {
    ctx.mission_id = decodeURIComponent(m[1])
    const section = m[2] ? SLUG_TO_SECTION[m[2]] : undefined
    if (section) ctx.section = section
    const scenario = new URLSearchParams(search).get('scenario')
    if (scenario && scenario !== 'new') ctx.scenario_id = scenario
    if (opts.start && opts.end) {
      ctx.start = opts.start
      ctx.end = opts.end
    }
    return ctx
  }
  if (SITE_PAGES.some((p) => pathname.startsWith(p))) {
    if (opts.siteId) ctx.site_id = opts.siteId
    if (opts.start && opts.end) {
      ctx.start = opts.start
      ctx.end = opts.end
    }
  }
  return ctx
}

const DAY_MS = 86_400_000
const EXACT: PublishedDate['precision'][] = ['second', 'minute', 'day']

export interface NextEvent {
  what: 'Launch' | 'Landing' | 'End of mission'
  date: PublishedDate
  /** Whole days to go, when the date is known to the day or better; null for a month, quarter or year. */
  days: number | null
}

/**
 * The next dated event of a mission after `now`, from its published dates:
 * a countdown in days when the date is known to the day, otherwise the date
 * as it is written. Null when nothing dated lies ahead.
 *
 * The events come in the mission's own order (launch, landing, end), so the
 * next is the first still ahead. They are not sorted by date: a landing
 * published as "late 2027" starts on 1 January 2027 and would otherwise come
 * before a launch dated 20 January 2027.
 */
export function nextEvent(
  m: { launch: PublishedDate | null; landing: PublishedDate | null; endOfMission?: PublishedDate | null },
  now: number,
): NextEvent | null {
  const candidates: NextEvent[] = []
  const add = (what: NextEvent['what'], d: PublishedDate | null | undefined) => {
    if (!d) return
    const exact = EXACT.includes(d.precision)
    if (exact ? d.startMs <= now : d.endMs <= now) return
    candidates.push({ what, date: d, days: exact ? Math.max(0, Math.ceil((d.startMs - now) / DAY_MS)) : null })
  }
  add('Launch', m.launch)
  add('Landing', m.landing)
  add('End of mission', m.endOfMission)
  return candidates[0] ?? null
}
