import type { Meta } from '../lib/api/adapters'
import { SectionLabel } from './ui'

/**
 * What these numbers were computed from — read from the response, never typed in.
 *
 * This block used to be hardcoded, and it said "synthetic DEM, seed 0" and
 * "mean-element analytic model". That was true then and became false the moment
 * the backend started answering with LOLA terrain and SPICE positions. A
 * hardcoded provenance line is the most dangerous literal in a product like
 * this: it is the one thing a reader relies on to know how much to trust
 * everything else, and it fails silently and in the flattering direction.
 *
 * So it is derived, like every other number on screen — `meta.resolution` and
 * `meta.uncertainty` come from the same response as the values they describe,
 * and cannot disagree with them.
 */
export function Sources({ meta, className = '' }: { meta: Meta | undefined; className?: string }) {
  if (!meta) {
    return (
      <div className={`flex flex-col gap-1.5 ${className}`}>
        <SectionLabel as="h3">Sources</SectionLabel>
        <p className="text-small text-ink-3">Not known yet: the numbers on this screen are still being worked out.</p>
      </div>
    )
  }
  const r = meta.resolution
  const u = meta.uncertainty
  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      <SectionLabel as="h3">Sources</SectionLabel>
      <ul className="flex flex-col gap-1 text-small leading-5 text-ink-2">
        <li>
          Terrain: {r.demProduct}, {r.demResolutionM.toFixed(0)} m detail, heights within ±
          {u.demVerticalErrorM.toFixed(0)} m.
          {u.partialCoverage ? ` It covers ${(u.coverage * 100).toFixed(0)}% of the directions around this spot.` : ''}
        </li>
        <li>Sun and Earth positions: NASA’s SPICE tools, {r.ephemeris.toUpperCase()}.</li>
        <li>
          Skyline: {r.azimuthCount.toLocaleString()} directions out to {(r.maxRangeM / 1000).toFixed(0)} km; times
          every {(r.timeStepS / 60).toFixed(0)} minutes.
        </li>
      </ul>
      <p className="text-caption text-ink-3">Not an official product of any space agency.</p>
    </div>
  )
}

/** The same provenance as one line, for the printed report footer. */
export function SourcesLine({ meta }: { meta: Meta | undefined }) {
  if (!meta) return <>Provenance not yet available.</>
  const r = meta.resolution
  return (
    <>
      Terrain: {r.demProduct} at {r.demResolutionM.toFixed(0)} m · Sun and Earth positions (SPICE): {r.ephemeris.toUpperCase()} · skyline{' '}
      {r.azimuthCount} directions out to {(r.maxRangeM / 1000).toFixed(0)} km
    </>
  )
}
