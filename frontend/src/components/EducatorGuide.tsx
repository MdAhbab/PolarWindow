import { useState } from 'react'
import type { Meta } from '../lib/api/adapters'
import type { SiteMetrics } from '../lib/types'
import { SURVIVAL_LIMIT_H } from '../lib/geometry/metrics'
import { bearing, compass, degrees, hoursWithUnit, percent, plusMinus } from '../lib/format'
import { TERRAIN_BLOCKER_MIN_EL_DEG } from './TwoClockRings'
import { Button, Panel, SectionLabel } from './ui'

interface Step {
  title: string
  body: string
  ask: string
  caveat: string
}

/**
 * The educator face's guided path: the four numbers, one at a time.
 *
 * The same layout pieces the story screen uses (progress segments, Back/Next,
 * "n of 4"), placed where the planner face has its technical sidebar. Every
 * figure is read from the site's metrics and `meta` -- the path changes the
 * pacing and the vocabulary, never the data, and each step keeps its caveat:
 * simplifying the words never simplifies the claim.
 */
export function EducatorGuide({
  siteName,
  metrics,
  meta,
}: {
  siteName: string
  metrics: SiteMetrics
  meta?: Meta
}) {
  const [i, setI] = useState(0)
  const steps = buildSteps(siteName, metrics, meta)
  const step = steps[i]

  return (
    <Panel className="flex flex-col gap-4 p-5" as="section">
      <div className="flex items-baseline justify-between gap-4">
        <SectionLabel>Guided walk-through</SectionLabel>
        <span className="font-mono text-caption text-ink-2">
          step {i + 1} of {steps.length}
        </span>
      </div>
      <div className="flex gap-1.5" aria-hidden="true">
        {steps.map((_, k) => (
          <span key={k} className={`h-1.5 grow ${k <= i ? 'bg-sun-fill' : 'bg-line-strong'}`} />
        ))}
      </div>

      {/* Announced when the step changes, so a screen-reader user hears the
          new step rather than only the new button label. */}
      <div aria-live="polite" className="flex flex-col gap-3">
        <h2 className="text-title-lg leading-6 font-semibold">{step.title}</h2>
        <p className="text-body leading-6 text-ink">{step.body}</p>
        <div className="flex flex-col gap-1 border-l-[3px] border-earth-fill pl-3">
          <span className="text-tag font-semibold tracking-caps-md text-ink-3 uppercase">Ask the class</span>
          <p className="text-body leading-6 text-ink-2">{step.ask}</p>
        </div>
        <p className="text-caption leading-caption text-ink-3">{step.caveat}</p>
      </div>

      <div className="flex gap-3 border-t border-line pt-4">
        <Button onClick={() => setI((k) => Math.max(0, k - 1))} disabled={i === 0}>
          Back
        </Button>
        {i < steps.length - 1 && (
          <Button variant="primary" className="grow" onClick={() => setI((k) => k + 1)}>
            Next — {steps[i + 1].title.toLowerCase()}
          </Button>
        )}
      </div>
    </Panel>
  )
}

function buildSteps(siteName: string, m: SiteMetrics, meta?: Meta): Step[] {
  const u = meta?.uncertainty
  const edge = u
    ? u.grazing
      ? 'At least one crossing is too shallow to time, so its hour is not knowable from this data.'
      : !u.terrainModelled
        ? 'Terrain is not modelled here, so the crossing times assume a smooth Moon and carry no stated margin.'
        : u.edgeTimingH !== null
        ? `Each crossing time is known to about ${plusMinus(u.edgeTimingH, 1)} h, because the terrain heights are known to about ±${u.demVerticalErrorM} m.`
        : ''
    : ''
  const night = m.sun.longestDownArc
  const terrain = night?.blockedByElDeg !== undefined && night.blockedByElDeg > TERRAIN_BLOCKER_MIN_EL_DEG
  const nightOpen = Boolean(m.sun.longestDownOpen)
  const over = m.sun.longestDownH > SURVIVAL_LIMIT_H

  return [
    {
      title: 'The outer ring is sunlight',
      body:
        `At ${siteName} the Sun is above the site’s own skyline for ${hoursWithUnit(m.sun.upHours)} ` +
        `of this ${hoursWithUnit(m.windowHours)} window — ${percent(m.sun.fractionUp)} of the time. ` +
        'Filled amber is sunlit; hatched is dark.',
      ask: 'Why might a spot very close to the pole get more sunlight than one further away from it?',
      caveat: edge,
    },
    {
      title: 'The inner ring is Earth',
      body:
        `Earth is above the skyline for ${hoursWithUnit(m.earth.upHours)} (${percent(m.earth.fractionUp)}). ` +
        'A radio link needs a straight line to Earth, so this is when a lander could talk to home.',
      ask: 'Earth hardly moves across this sky. What could make it sink below the horizon for days?',
      caveat:
        'This is line of sight only. It says nothing about antennas, power or which ground station is free.',
    },
    {
      title: 'The longest night',
      body: night
        ? `The longest unbroken dark stretch is ${hoursWithUnit(m.sun.longestDownH, 0, nightOpen)}` +
          (terrain
            ? `, caused by terrain to the ${compass(night.blockedByBearingDeg ?? 0)} (bearing ${bearing(
                night.blockedByBearingDeg ?? 0,
              )}) standing ${degrees(night.blockedByElDeg ?? 0, 2)} above a flat horizon`
            : ', with the Sun simply below the horizon') +
          (nightOpen ? ' — and the window cuts it short, so the real night is longer' : '') +
          `. A lander that can last ${SURVIVAL_LIMIT_H} h in the dark would be ${
            over ? 'out of energy before it ends' : 'within its limit'
          }.`
        : 'There is no dark stretch in this window: the Sun stays above the skyline throughout.',
      ask: 'What would a lander need to carry to survive the whole night, and what would that cost it?',
      caveat: `The ${SURVIVAL_LIMIT_H} h survival limit is a placeholder, not a real lander’s rating. ${edge}`,
    },
    {
      title: 'When both are gone',
      body:
        `The longest time without Earth is ${hoursWithUnit(m.earth.longestDownH, 0, m.earth.longestDownOpen)}. ` +
        `The worst stretch with neither sunlight nor Earth is ${hoursWithUnit(m.worstCompoundH)}: ` +
        'the lander is in the dark and on its own at the same time.',
      ask: 'If you had to choose between more sunlight and more contact with Earth, which would you pick for a rover? For a weather station?',
      caveat:
        'These four numbers are never averaged into one score. A score would hide which of them a site gives up, and that trade is the whole decision.',
    },
  ]
}
