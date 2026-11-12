import { useEffect, useRef, useState, type RefObject } from 'react'
import { SECTIONS } from '../lifecycle/JourneyBar'
import { Icon } from '../Icon'
import { EnterLink } from './Enter'
import './landing.css'

/**
 * "What you can do", as an uneven group that shows the product: one wide card
 * that follows a mission through its six steps on the same curved line the
 * mission page draws, and three smaller ones, each with the question it
 * answers, one sentence and the page it lives on. At 390 px: one column, the
 * wide card first.
 */

const SMALL = [
  {
    title: 'Sunlight and contact at a site',
    asks: 'How much sun, and how much contact with Earth, does one place get?',
    body: 'For any site and dates: hours of sunlight and of contact with Earth. Also the longest night and the longest time without contact.',
    link: 'Open a site',
    to: '/site',
    span: 'lg:col-span-3',
  },
  {
    title: 'Compare sites, one measure at a time',
    asks: 'How do the sites line up on one measure?',
    body: 'Sites are ordered by one measure at a time. The page never merges them into one number.',
    link: 'Compare sites',
    to: '/compare',
    span: 'lg:col-span-2',
  },
  {
    title: 'Plan around the gaps',
    asks: 'When is the lander on its own, and for how long?',
    body: 'Every stretch without contact, longest first, what the lander must handle alone, and a spreadsheet to share.',
    link: 'See the gaps',
    to: '/plan',
    span: 'lg:col-span-5',
  },
] as const

export function FeatureGroup({ animate }: { animate: boolean }) {
  return (
    <ul className="grid gap-5 lg:grid-cols-5">
      <li data-reveal className="pw-card flex flex-col gap-6 p-6 sm:p-8 lg:col-span-5">
        <StepsCard animate={animate} />
      </li>
      {SMALL.map((c, i) => (
        <li
          key={c.title}
          data-reveal
          data-reveal-i={i + 1}
          className={`pw-card flex flex-col gap-3 p-6 sm:p-8 ${c.span} ${i === 2 ? 'lg:flex-row lg:items-start lg:gap-10' : ''}`}
        >
          <div className="flex flex-col gap-3 lg:max-w-sm lg:shrink-0">
            <h3 className="text-title-lg leading-6 font-semibold tracking-title">{c.title}</h3>
            <p className="text-small leading-5 text-ink-3">{c.asks}</p>
          </div>
          <div className="flex flex-col items-start gap-1">
            <p className="max-w-[62ch] text-body leading-6 text-ink-2 text-pretty">{c.body}</p>
            <EnterLink to={c.to}>{c.link}</EnterLink>
          </div>
        </li>
      ))}
    </ul>
  )
}

/* ---- The six steps, as the mission page draws them ----------------------------
   A static copy of JourneyPath's line (components/lifecycle/JourneyBar.tsx): the
   parabola from Earth to the Moon with six stops, over a width that is the
   drawing's own units and scales with the card. Nothing is fetched and no
   mission is read: the words are the mission page's own step names and
   questions (SECTIONS). Wide enough, the line is an arc across the card with
   each step's words under its stop; narrower, it runs down the page. */

const W = 960
const BAND = 116
const BASE = 92
const LIFT = 58
const PAD = 48
const END = 20
const COL = (W - 2 * PAD) / SECTIONS.length
const ARC = `M ${END} ${BASE} Q ${W / 2} ${BASE - 2 * LIFT} ${W - END} ${BASE}`
/** A stop sits 14 units in from its column's left edge (the mission page's mark is 28 wide). */
const STOPS = SECTIONS.map((s, i) => {
  const x = PAD + i * COL + 14
  const u = (x - END) / (W - 2 * END)
  return { ...s, x, y: BASE - 4 * LIFT * u * (1 - u), at: Math.round(160 + 720 * (x / W)) }
})

/** True once the element has been in the window; the line draws at that moment, once. */
function useSeenOnce(): [RefObject<HTMLDivElement | null>, boolean] {
  const ref = useRef<HTMLDivElement>(null)
  const [seen, setSeen] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el || typeof IntersectionObserver === 'undefined') return
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setSeen(true)
          io.disconnect()
        }
      },
      { rootMargin: '0px 0px -20% 0px' },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [])
  return [ref, seen]
}

function StepsCard({ animate }: { animate: boolean }) {
  const [ref, seen] = useSeenOnce()
  // Waiting (paused at its first frame) until the card is in view; without motion, no class at all.
  const state = { animationPlayState: seen ? ('running' as const) : ('paused' as const) }
  return (
    <div ref={ref} className="@container flex flex-col gap-6">
      <div className="flex max-w-2xl flex-col gap-2">
        <h3 className="pw-display text-[26px] leading-[1.12] sm:text-[30px]">Follow a mission through six steps</h3>
        <p className="text-lede leading-7 text-ink-2 text-pretty">
          One path from Earth to the Moon, with a question at each stop. Every mission in the list has its own page for each step.
        </p>
      </div>

      {/* Wide: the arc, then each step under its stop. */}
      <div className="hidden @4xl:block">
        <svg
          viewBox={`0 0 ${W} ${BAND}`}
          role="img"
          aria-label="A curved line from Earth to the Moon with six numbered stops: Ready, Launch, Trip, Surface, Contact, Return."
          className={`w-full ${animate ? 'pw-path-draw' : ''}`}
          style={animate ? state : undefined}
        >
          <path d={ARC} fill="none" strokeWidth={1.5} className="stroke-line-strong" />
          <path d={ARC} fill="none" strokeWidth={2} className="stroke-ink" />
          <circle cx={END} cy={BASE} r={10} fill="var(--color-earth-fill)" />
          <text x={END} y={BAND - 2} textAnchor="middle" fontSize={12} fill="var(--color-ink-3)">
            Earth
          </text>
          <circle cx={W - END} cy={BASE} r={10} fill="none" stroke="var(--color-ink-2)" strokeWidth={2} />
          <text x={W - END} y={BAND - 2} textAnchor="middle" fontSize={12} fill="var(--color-ink-3)">
            Moon
          </text>
          {STOPS.map((s, i) => (
            <g
              key={s.id}
              className={animate ? 'pw-stop-in' : ''}
              style={{
                transformBox: 'fill-box',
                transformOrigin: 'center',
                ['--pw-at' as string]: `${s.at}ms`,
                ...(animate ? state : {}),
              }}
            >
              <circle cx={s.x} cy={s.y} r={14} fill="var(--color-panel)" stroke="var(--color-ink)" strokeWidth={2} />
              <text x={s.x} y={s.y + 4.5} textAnchor="middle" fontSize={13} fontWeight={500} fontFamily="var(--font-mono)" fill="var(--color-ink)">
                {i + 1}
              </text>
            </g>
          ))}
        </svg>
        <ol className="grid grid-cols-6" style={{ paddingInline: `${(PAD / W) * 100}%` }}>
          {STOPS.map((s) => (
            <li key={s.id} className="flex min-w-0 flex-col gap-1.5 pr-3">
              <span className="text-title-lg font-semibold tracking-title text-ink">{s.name}</span>
              <span className="text-small leading-5 text-ink-3 text-pretty">{s.question}</span>
            </li>
          ))}
        </ol>
      </div>

      {/* Narrow: down the page, the line on the left. */}
      <ol className="flex flex-col @4xl:hidden">
        <li className="relative flex items-center gap-4 pb-6">
          <span className="relative z-[1] flex size-7 items-center justify-center text-earth" aria-hidden="true">
            <Icon name="earth" size={22} strokeWidth={1.7} />
          </span>
          <span className="text-small text-ink-3">Earth</span>
          <span aria-hidden="true" className="absolute top-7 bottom-0 left-[13px] w-0.5 bg-line-strong" />
        </li>
        {STOPS.map((s, i) => (
          <li key={s.id} className="relative flex gap-4 pb-6">
            <span className="relative z-[1] flex size-7 shrink-0 items-center justify-center rounded-pill border-2 border-ink bg-panel font-mono text-caption font-medium text-ink">
              {i + 1}
            </span>
            <span className="flex min-w-0 flex-col gap-1">
              <span className="text-title-lg leading-7 font-semibold tracking-title text-ink">{s.name}</span>
              <span className="text-small leading-5 text-ink-3">{s.question}</span>
            </span>
            <span aria-hidden="true" className="absolute top-7 bottom-0 left-[13px] w-0.5 bg-line-strong" />
          </li>
        ))}
        <li className="relative flex items-center gap-4">
          <span className="relative z-[1] flex size-7 items-center justify-center text-ink-2" aria-hidden="true">
            <Icon name="moon" size={22} strokeWidth={1.7} />
          </span>
          <span className="text-small text-ink-3">The Moon</span>
        </li>
      </ol>

      <EnterLink to="/missions">Open the missions</EnterLink>
    </div>
  )
}
