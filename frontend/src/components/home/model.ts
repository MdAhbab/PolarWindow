/**
 * Home's pure logic: which steps need the manager, a project's six steps as
 * a strip, the countdown to its next dated event, the clock, the feeds' ages
 * in one line, and the Ask suggestions. Every number here is a count of real
 * things or a date from the record; nothing is scored or guessed.
 */
import type { FeedDTO, SectionId, SectionState, SectionStatusDTO } from '../../lib/api/lifecycle'
import type { NextEvent } from '../../lib/api/home'
import { SECTIONS, sectionPath } from '../lifecycle/JourneyBar'

export interface ProjectRef {
  id: string
  name: string
}

export interface NeedItem {
  key: string
  missionId: string
  missionName: string
  section: SectionId
  stepName: string
  state: Extract<SectionState, 'needs_input' | 'no_data'>
  summary: string
  /** The one click: the form for missing input, a scenario for missing data. */
  href: string
  action: string
}

/**
 * The steps across the manager's projects that wait on them: `needs_input`
 * (something only a person can enter) and `no_data` (nothing published, so a
 * scenario can be explored). In project order, then journey order.
 */
export function needsYou(projects: ProjectRef[], sections: (SectionStatusDTO[] | undefined)[]): NeedItem[] {
  const out: NeedItem[] = []
  projects.forEach((p, i) => {
    const statuses = sections[i]
    if (!statuses) return
    for (const step of SECTIONS) {
      const s = statuses.find((x) => x.section === step.id)
      if (!s || (s.state !== 'needs_input' && s.state !== 'no_data')) continue
      const page = sectionPath(p.id, step.id)
      // Ready is entered on its own page; the other steps take their inputs
      // from the project form. Ready is never assumed, so it has no scenario.
      const href =
        s.state === 'no_data'
          ? step.id === 'ready'
            ? page
            : `${page}?scenario=new`
          : step.id === 'ready'
            ? page
            : `/projects/${encodeURIComponent(p.id)}/edit`
      const action =
        s.state === 'no_data' ? (step.id === 'ready' ? `Open ${step.name}` : 'Explore a scenario') : step.id === 'ready' ? 'Fill it in' : 'Fill in the form'
      out.push({
        key: `${p.id}:${step.id}`,
        missionId: p.id,
        missionName: p.name,
        section: step.id,
        stepName: step.name,
        state: s.state,
        summary: s.summary,
        href,
        action,
      })
    }
  })
  return out
}

export interface StripStep {
  id: SectionId
  name: string
  /** Null while the steps load or when the service did not say. */
  state: SectionState | null
}

/** The six steps in journey order, each with its state if known. */
export function journeySteps(statuses: SectionStatusDTO[] | undefined): StripStep[] {
  return SECTIONS.map((s) => ({ id: s.id, name: s.name, state: statuses?.find((x) => x.section === s.id)?.state ?? null }))
}

/** "Launch in 12 days", "Landing today", "Launch: Q4 2027": the next event as it is known. */
export function countdownWords(ev: NextEvent): string {
  if (ev.days === null) return `${ev.what}: ${ev.date.asPublished}`
  if (ev.days === 0) return `${ev.what} today`
  if (ev.days === 1) return `${ev.what} tomorrow`
  return `${ev.what} in ${ev.days} days`
}

const pad2 = (n: number) => String(n).padStart(2, '0')
const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

/** "14:32:07": the time in UTC. */
export function utcClock(ms: number): string {
  const d = new Date(ms)
  return `${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}:${pad2(d.getUTCSeconds())}`
}

/** "Wednesday 11 November 2026": the UTC date in words. */
export function utcDateWords(ms: number): string {
  const d = new Date(ms)
  return `${WEEKDAYS[d.getUTCDay()]} ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`
}

/** The start of the UTC minute: the terminator is drawn for this minute. */
export const minuteOf = (ms: number) => Math.floor(ms / 60_000) * 60_000

/**
 * The page's opening line, from counts of real things: what waits on the
 * manager and what is being worked out. Null while either is unknown.
 */
export function headline(needs: number | null, working: number | null): string | null {
  if (needs === null) return null
  const a =
    needs === 0 ? 'Nothing waits on you' : `${needs} ${needs === 1 ? 'step waits' : 'steps wait'} on you`
  if (working === null) return `${a}.`
  const b = working === 0 ? 'nothing is being worked out' : `${working} ${working === 1 ? 'thing is' : 'things are'} being worked out`
  return `${a}; ${b}.`
}

const ageShort = (s: number) =>
  s < 90 ? 'just now' : s < 3600 ? `${Math.round(s / 60)} min` : s < 48 * 3600 ? `${Math.round(s / 3600)} h` : `${Math.round(s / 86400)} days`

/**
 * The feeds' ages in one line: each provider's newest data, its age, and
 * "old" where the service says so. Null with no feeds.
 */
export function feedAgesLine(feeds: FeedDTO[]): string | null {
  const by = new Map<string, { age: number | null; stale: boolean }>()
  for (const f of feeds) {
    const name = f.provider_name ?? f.provider
    const cur = by.get(name)
    const age = typeof f.age_s === 'number' && Number.isFinite(f.age_s) ? f.age_s : null
    if (!cur) {
      by.set(name, { age, stale: f.stale })
      continue
    }
    const newer = age !== null && (cur.age === null || age < cur.age)
    by.set(name, { age: newer ? age : cur.age, stale: newer ? f.stale : cur.stale && f.stale })
  }
  if (!by.size) return null
  return [...by.entries()]
    .map(([name, v]) => `${name} ${v.age === null ? 'nothing yet' : ageShort(v.age)}${v.stale ? ' (old)' : ''}`)
    .join(', ')
}

/** Questions to start Ask with: about the manager's own projects first. */
export function askSuggestions(projects: ProjectRef[]): string[] {
  const first = projects[0]?.name
  const own = first
    ? [`What does ${first} still need?`, `When can ${first} launch?`]
    : ['How do I add my project?']
  return [...own, 'What is a scenario, and what does it assume?', 'Which sites keep contact with Earth longest?'].slice(0, 4)
}
