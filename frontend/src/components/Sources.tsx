import type { Meta } from '../lib/api/adapters'
import { Panel, SectionLabel } from './ui'

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
      <Panel className={`flex flex-col gap-2 p-5 ${className}`}>
        <SectionLabel>Sources</SectionLabel>
        <p className="text-tag leading-caption-tight text-ink-3">
          Not yet known — the figures on this screen have not finished computing.
        </p>
      </Panel>
    )
  }
  const r = meta.resolution
  const u = meta.uncertainty
  return (
    <Panel className={`flex flex-col gap-2 p-5 ${className}`}>
      <SectionLabel>Sources</SectionLabel>
      <p className="font-mono text-tag leading-caption text-ink-2">
        Elevation: {r.demProduct} at {r.demResolutionM.toFixed(0)} m
        <br />
        Ephemeris: {r.ephemeris}
        <br />
        Horizon mask: {r.azimuthCount} az × {(r.maxRangeM / 1000).toFixed(0)} km · sampled every{' '}
        {(r.timeStepS / 60).toFixed(0)} min
      </p>
      <p className="text-tag leading-caption-tight text-ink-3">
        Vertical accuracy ±{u.demVerticalErrorM.toFixed(0)} m.
        {u.partialCoverage
          ? ` Terrain covers ${(u.coverage * 100).toFixed(0)}% of the sampled bearings, so this site is modelled with gaps.`
          : ' Terrain covers every sampled bearing.'}{' '}
        Not an official product of any space agency.
      </p>
    </Panel>
  )
}

/** The same provenance as one line, for the printed report footer. */
export function SourcesLine({ meta }: { meta: Meta | undefined }) {
  if (!meta) return <>Provenance not yet available.</>
  const r = meta.resolution
  return (
    <>
      Elevation: {r.demProduct} at {r.demResolutionM.toFixed(0)} m · Ephemeris: {r.ephemeris} · mask{' '}
      {r.azimuthCount} az × {(r.maxRangeM / 1000).toFixed(0)} km
    </>
  )
}
