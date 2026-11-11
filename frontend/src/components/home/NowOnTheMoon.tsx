import { useMemo } from 'react'
import { PolarMap, type MissionPin } from '../PolarMap'
import { useMission } from '../../lib/store'
import type { Mission } from '../../lib/api/adapters'
import { useNow, useSunNow } from './useSunNow'
import { utcClock, utcDateWords } from './model'

/**
 * The south pole for this minute: the terminator from the same SPICE Sun as
 * every number, the manager's project targets pinned on it, and the time in
 * UTC, which is the time every date in the app is written in.
 */
export function NowOnTheMoon({ projects }: { projects: Mission[] }) {
  const { sun, atMs, state } = useSunNow()
  const siteId = useMission((s) => s.siteId)
  const pins = useMemo<MissionPin[]>(
    () =>
      projects
        .filter((p) => p.target)
        .map((p) => ({
          key: p.id,
          latDeg: p.target!.latDeg,
          lonDeg: p.target!.lonDeg,
          dashed: true,
          label: `${p.name}: target, ${p.target!.name}`,
          highlighted: true,
        })),
    [projects],
  )
  const outside = projects.filter((p) => p.target && p.target.latDeg > -80).length
  const at = utcClock(atMs).slice(0, 5)

  return (
    <section aria-labelledby="home-moon" className="pw-card flex min-w-0 flex-col gap-4 p-4 sm:p-5">
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <h2 id="home-moon" className="text-title-lg font-semibold tracking-title text-ink">
          Now on the Moon
        </h2>
        <UtcClock />
      </div>
      <div className="mx-auto w-full max-w-[520px]">
        <PolarMap sun={sun} selectedSiteId={siteId} siteMarks="dots" missionPins={pins} size={520} />
      </div>
      <p className="text-small leading-5 text-ink-2">
        {state === 'shown'
          ? `Shade where the Sun is below a flat horizon at ${at} UTC. Ridges and craters cast no shadow on this map; each site’s skyline does.`
          : state === 'unavailable'
            ? 'The Sun’s position for this minute could not be read, so no shadow is drawn. The sites and targets are where they are.'
            : 'Reading the Sun’s position for this minute…'}
        {pins.length
          ? ` Diamonds: your project targets${outside ? `; ${outside} lie${outside === 1 ? 's' : ''} north of 80°S, off this map` : ''}.`
          : ''}
      </p>
    </section>
  )
}

/** The time in UTC, to the second. Read once a minute by a screen reader, not every second. */
function UtcClock() {
  const now = useNow(1000)
  const clock = utcClock(now)
  return (
    <p className="flex flex-col items-end text-right">
      <span className="text-caption leading-caption text-ink-2">{utcDateWords(now)}</span>
      <time
        dateTime={new Date(now).toISOString()}
        className="font-mono text-figure-sm leading-none font-medium tracking-figure-sm text-ink tabular-nums sm:text-figure"
      >
        <span aria-hidden="true">
          {clock}
          <span className="ml-1.5 font-sans text-small font-semibold tracking-normal text-ink-3">UTC</span>
        </span>
        <span className="sr-only">{clock.slice(0, 5)} UTC</span>
      </time>
    </p>
  )
}
