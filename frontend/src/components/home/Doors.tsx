import { Link } from 'react-router-dom'
import { Icon, type IconName } from '../Icon'

const DOORS: { to: string; icon: IconName; title: string; line: string }[] = [
  { to: '/missions', icon: 'moon', title: 'Follow a mission', line: 'Open a CLPS mission and walk its six steps.' },
  { to: '/map', icon: 'pin', title: 'Check a landing site', line: 'See sunlight and contact at any site near the pole.' },
  { to: '/projects/new', icon: 'plus', title: 'Plan my own mission', line: 'Drop a file or fill in a short form.' },
]

const HOW: { icon: IconName; words: string }[] = [
  { icon: 'pin', words: 'Pick a mission or a site' },
  { icon: 'clocks', words: 'See the four numbers' },
  { icon: 'quarter', words: 'Try a what-if' },
]

/**
 * Home's three ways in, each one sentence, and how the app works in three
 * pictures. One tap from Home to each of the three things people come for.
 */
export function Doors() {
  return (
    <section aria-labelledby="home-doors" className="flex min-w-0 flex-col gap-4">
      <h2 id="home-doors" className="sr-only">
        Where to start
      </h2>
      <ul className="grid gap-3 sm:grid-cols-3">
        {DOORS.map((d) => (
          <li key={d.to} className="flex min-w-0">
            <Link
              to={d.to}
              className="pw-press pw-card group flex w-full min-w-0 items-start gap-3 p-4 text-ink no-underline hover:bg-inset sm:p-5"
            >
              <span aria-hidden="true" className="flex size-10 shrink-0 items-center justify-center rounded-pill bg-ink text-canvas">
                <Icon name={d.icon} size={18} strokeWidth={2} />
              </span>
              <span className="flex min-w-0 flex-col gap-0.5">
                <span className="text-control font-semibold">{d.title}</span>
                <span className="text-small leading-5 text-ink-2">{d.line}</span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
      <ol aria-label="How it works" className="flex flex-wrap items-center gap-x-2 gap-y-2 text-small text-ink-2">
        {HOW.map((h, i) => (
          <li key={h.words} className="flex items-center gap-2">
            <span aria-hidden="true" className="flex size-8 items-center justify-center rounded-pill border border-line-strong bg-tray text-ink">
              <Icon name={h.icon} size={15} strokeWidth={2} />
            </span>
            <span>
              <span className="sr-only">Step {i + 1}: </span>
              {h.words}
            </span>
            {i < HOW.length - 1 && (
              <Icon name="arrow" size={14} strokeWidth={2} className="text-ink-3" />
            )}
          </li>
        ))}
      </ol>
    </section>
  )
}
