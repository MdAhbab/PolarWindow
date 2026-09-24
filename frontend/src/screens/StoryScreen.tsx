import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { markVisited } from '../lib/firstVisit'
import { useMission } from '../lib/store'
import { useFocusedMetrics } from '../lib/mission'
import { siteById } from '../lib/sites'
import { Button } from '../components/ui'
import { bearing, compass, humanDuration } from '../lib/format'
import { TERRAIN_BLOCKER_MIN_EL_DEG } from '../components/TwoClockRings'

/** S7 — the public face. One idea per panel, and no caveat dropped to make a
 *  sentence shorter. */
export function StoryScreen() {
  const [step, setStep] = useState(0)
  // Having seen the story is what makes the next visit start on Missions (U1).
  useEffect(() => markVisited(), [])
  const metrics = useFocusedMetrics()
  const site = siteById(useMission((s) => s.siteId))

  const night = metrics?.sun.longestDownArc
  const nightText = night
    ? humanDuration(night.hours, 'public', metrics?.sun.longestDownOpen)
    : 'days at a time'
  const blockAz = night?.blockedByBearingDeg ?? 0
  const byTerrain =
    night?.blockedByElDeg !== undefined && night.blockedByElDeg > TERRAIN_BLOCKER_MIN_EL_DEG

  const panels = [
    {
      kicker: 'One',
      title: 'The Sun never climbs',
      body: 'At the Moon’s pole the Sun does not rise and set overhead. It circles the horizon, staying within a degree or two of it, all month long.',
      art: <SunPathArt />,
    },
    {
      kicker: 'Two',
      title: 'So a hill can switch off the Sun',
      body: byTerrain
        ? `Sunlight that low is easy to block. At ${site.name.split(',')[0]}, terrain to the ${compass(blockAz)} — bearing ${bearing(blockAz)} — puts the ground in shadow for ${nightText}, every single month.`
        : `Sunlight that low is easy to lose. At ${site.name.split(',')[0]} the Sun dips below the horizon itself for ${nightText}; at other spots near here a ridge does it instead.`,
      art: <RidgeArt />,
    },
    {
      kicker: 'Three',
      title: 'Earth is low down there too',
      body: 'Radio needs a straight line. From the pole, Earth also hangs near the horizon and swings above and below it as the Moon wobbles — so there are days when nothing can call home.',
      art: <EarthArt />,
    },
    {
      kicker: 'Four',
      title: 'The ice is in the dark. The power is in the light.',
      body: 'Water ice only survives where the Sun has never reached, in crater floors dark for billions of years. Solar power only works where it has. They are never the same place.',
      art: <IceArt />,
    },
  ]

  const p = panels[step]

  return (
    <div className="mx-auto flex w-full max-w-[1100px] grow flex-col gap-6 px-4 py-6 lg:px-8">
      <div className="flex items-end justify-between gap-6 border-b border-line pb-4">
        <div className="flex flex-col gap-2">
          <div className="text-[13px] font-semibold tracking-[0.14em] text-ink-3 uppercase">
            Why is the Moon’s south pole hard?
          </div>
          <h1 className="text-[32px] leading-10 font-semibold tracking-[-0.015em] lg:text-[40px] lg:leading-[46px]">
            {p.title}
          </h1>
        </div>
        <Link to="/missions" className="hidden h-12 shrink-0 items-center text-[14px] font-semibold sm:inline-flex">
          Skip to the missions →
        </Link>
      </div>

      <div className="flex gap-1.5" aria-hidden="true">
        {panels.map((_, i) => (
          <span key={i} className={`h-1.5 grow ${i <= step ? 'bg-sun-fill' : 'bg-line-strong'}`} />
        ))}
      </div>

      <div className="flex grow flex-col items-center gap-8 lg:flex-row lg:gap-14">
        <div className="w-full max-w-[560px] shrink-0 border border-line bg-panel p-6">{p.art}</div>
        <div className="flex flex-col gap-5">
          <div className="text-[12px] font-semibold tracking-[0.14em] text-sun uppercase">{p.kicker} of four</div>
          <p className="max-w-[520px] text-[19px] leading-8 text-ink text-pretty">{p.body}</p>
          {step === panels.length - 1 && (
            <p className="max-w-[520px] text-[16px] leading-7 text-ink-2">
              Which is why where you land matters down to about 500 metres — and why this tool refuses to
              give a site a single score.
            </p>
          )}
        </div>
      </div>

      <div className="flex gap-3 border-t border-line pt-5">
        <Button onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0}>
          Back
        </Button>
        {step < panels.length - 1 ? (
          <Button variant="primary" className="grow sm:grow-0" onClick={() => setStep((s) => s + 1)}>
            Next — {panels[step + 1].title.toLowerCase()}
          </Button>
        ) : (
          <Link
            to="/missions"
            className="inline-flex h-12 grow items-center justify-center rounded-control bg-sun-fill px-6 text-[15px] font-semibold text-on-sun no-underline sm:grow-0"
          >
            Browse CLPS missions
          </Link>
        )}
      </div>
    </div>
  )
}

function SunPathArt() {
  return (
    <svg viewBox="0 0 320 220" className="w-full" role="img" aria-label="At the equator the Sun climbs in a high arc overhead. At the pole it circles just above the horizon.">
      <text x="78" y="18" textAnchor="middle" fill="var(--color-ink-3)" fontSize="12" fontWeight="600" letterSpacing="1.2">AT THE EQUATOR</text>
      <path d="M14 96 A64 64 0 0 1 142 96" fill="none" stroke="var(--color-sun)" strokeWidth="2.5" strokeDasharray="5 5" />
      <circle cx="78" cy="34" r="12" fill="var(--color-sun-fill)" />
      <path d="M8 96 H148" stroke="var(--color-terrain-high)" strokeWidth="2.5" />
      <rect x="8" y="96" width="140" height="18" fill="var(--color-terrain-low)" />
      <text x="78" y="136" textAnchor="middle" fill="var(--color-ink-2)" fontSize="14">up and over</text>
      <path d="M160 14 V200" stroke="var(--color-line)" />
      <text x="242" y="18" textAnchor="middle" fill="var(--color-ink-3)" fontSize="12" fontWeight="600" letterSpacing="1.2">AT THE POLE</text>
      <ellipse cx="242" cy="90" rx="66" ry="10" fill="none" stroke="var(--color-sun)" strokeWidth="2.5" strokeDasharray="5 5" />
      <circle cx="308" cy="90" r="12" fill="var(--color-sun-fill)" />
      <path d="M172 96 H312" stroke="var(--color-terrain-high)" strokeWidth="2.5" />
      <rect x="172" y="96" width="140" height="18" fill="var(--color-terrain-low)" />
      <text x="242" y="136" textAnchor="middle" fill="var(--color-ink)" fontSize="14" fontWeight="600">it just goes around</text>
      <text x="160" y="190" textAnchor="middle" fill="var(--color-ink-3)" fontSize="13">grey = the ground you are standing on</text>
    </svg>
  )
}

function RidgeArt() {
  return (
    <svg viewBox="0 0 320 220" className="w-full" role="img" aria-label="A lander on flat ground beside a ridge. When the Sun passes behind the ridge, a long shadow covers it.">
      <circle cx="34" cy="62" r="14" fill="var(--color-sun-fill)" />
      <g stroke="var(--color-sun)" strokeWidth="2.2" strokeLinecap="round">
        <path d="M54 62 H96 M54 53 L92 42 M54 71 L92 82" />
      </g>
      <path d="M120 156 L152 94 L176 122 L206 70 L240 156 Z" fill="var(--color-terrain-mid)" stroke="var(--color-terrain-high)" strokeWidth="2.2" />
      <path d="M206 70 L316 132 L316 156 L240 156 Z" fill="var(--color-dark-fill)" />
      <path d="M0 156 H320" stroke="var(--color-terrain-high)" strokeWidth="2.5" />
      <rect x="0" y="156" width="320" height="34" fill="var(--color-terrain-low)" />
      <rect x="256" y="156" width="64" height="34" fill="var(--color-dark-fill)" />
      <g transform="translate(274 132)">
        <rect x="-12" y="0" width="24" height="18" fill="var(--color-ink-2)" />
        <path d="M-12 0 L0 -11 L12 0" fill="var(--color-ink-3)" />
      </g>
      <text x="274" y="112" textAnchor="middle" fill="var(--color-ink-2)" fontSize="14" fontWeight="600">in shadow</text>
    </svg>
  )
}

function EarthArt() {
  return (
    <svg viewBox="0 0 320 220" className="w-full" role="img" aria-label="Earth sits low over the horizon. One radio path is clear; a ridge blocks another.">
      <circle cx="46" cy="72" r="22" fill="var(--color-earth-fill)" />
      <path d="M30 60 q12 6 8 14 t10 12 M56 56 q10 10 4 18" fill="none" stroke="var(--color-earth-deep)" strokeWidth="3" strokeLinecap="round" />
      <text x="46" y="112" textAnchor="middle" fill="var(--color-earth)" fontSize="13" fontWeight="600">Earth</text>
      <path d="M0 150 H320" stroke="var(--color-terrain-high)" strokeWidth="2.5" />
      <rect x="0" y="150" width="320" height="32" fill="var(--color-terrain-low)" />
      <g transform="translate(150 132)">
        <rect x="-11" y="0" width="22" height="16" fill="var(--color-ink-2)" />
        <path d="M-11 0 L0 -10 L11 0" fill="var(--color-ink-3)" />
      </g>
      <path d="M138 126 L66 84" stroke="var(--color-earth)" strokeWidth="2.5" strokeDasharray="6 5" />
      <text x="96" y="132" fill="var(--color-earth)" fontSize="12" fontWeight="600">clear</text>
      <path d="M214 150 L240 104 L262 122 L288 150 Z" fill="var(--color-terrain-mid)" stroke="var(--color-terrain-high)" strokeWidth="2" />
      <g transform="translate(300 132)">
        <rect x="-11" y="0" width="22" height="16" fill="var(--color-ink-3)" />
        <path d="M-11 0 L0 -10 L11 0" fill="var(--color-terrain-mid)" />
      </g>
      <path d="M290 126 L246 106" stroke="var(--color-alert)" strokeWidth="2.5" strokeDasharray="6 5" />
      <path d="M238 98 L254 114 M254 98 L238 114" stroke="var(--color-alert)" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}

function IceArt() {
  return (
    <svg viewBox="0 0 320 220" className="w-full" role="img" aria-label="A crater floor in permanent shadow holds ice; a sunlit ridge a few kilometres away holds the power.">
      <path d="M0 150 H320" stroke="var(--color-terrain-high)" strokeWidth="2" />
      <path d="M0 150 L48 150 L84 190 L152 190 L188 150 L232 150 L268 92 L320 132 L320 216 L0 216 Z" fill="var(--color-terrain-low)" />
      <path d="M84 190 L152 190 L188 150 L48 150 Z" fill="url(#pw-psr)" />
      <path d="M0 150 L48 150 L84 190 L152 190 L188 150 L232 150 L268 92 L320 132" fill="none" stroke="var(--color-terrain-high)" strokeWidth="2" />
      <path d="M232 150 L268 92 L296 114 L320 132 L320 150 Z" fill="var(--color-sun-fill)" fillOpacity="0.35" />
      <path d="M232 150 L268 92 L296 114" fill="none" stroke="var(--color-sun)" strokeWidth="3" />
      <circle cx="306" cy="60" r="11" fill="var(--color-sun-fill)" />
      <text x="118" y="176" textAnchor="middle" fill="var(--color-earth-soft)" fontSize="13" fontWeight="600">ice · never lit</text>
      <text x="278" y="80" textAnchor="middle" fill="var(--color-sun-soft)" fontSize="13" fontWeight="600">power</text>
      <path d="M118 208 H272" stroke="var(--color-ink)" strokeWidth="1.5" />
      <path d="M118 202 V214 M272 202 V214" stroke="var(--color-ink)" strokeWidth="1.5" />
      <text x="195" y="200" textAnchor="middle" fill="var(--color-ink)" fontSize="13" fontWeight="600">about 3 km</text>
    </svg>
  )
}
