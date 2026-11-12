import { DispersionPanel } from './DispersionPanel'
import { EnergyPanel } from './EnergyPanel'
import { MeshPanel } from './MeshPanel'
import { ToolSection } from './parts'

/**
 * The lander tools for one site and window, below a page's own content:
 * each closed behind its heading, and each asks the service only when the
 * person presses "Work it out".
 */
export function SurfaceTools({
  siteId,
  siteName,
  startMs,
  endMs,
}: {
  siteId: string
  siteName: string
  startMs: number | null
  endMs: number | null
}) {
  const iso = (ms: number | null) => (ms === null || !Number.isFinite(ms) ? null : new Date(ms).toISOString())
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <ToolSection
        guide="surface-energy"
        title="Power and temperature for a lander"
        lede="Battery charge and temperature inside the lander's body (bus) through these dates, for a lander you describe."
      >
        <EnergyPanel key={siteId} siteId={siteId} siteName={siteName} startIso={iso(startMs)} endIso={iso(endMs)} />
      </ToolSection>
      <ToolSection
        guide="surface-dispersion"
        title="Landing area and slope"
        lede="How steep the ground is where a lander might come down. Type in a landing area (ellipse) and a lander."
      >
        <DispersionPanel key={siteId} siteId={siteId} siteName={siteName} />
      </ToolSection>
      <ToolSection
        guide="surface-mesh"
        title="Rovers relaying for each other"
        lede="How long a lander and up to five rovers go without a path to Earth. Alone, and when they pass each other's data on."
      >
        <MeshPanel key={siteId} siteId={siteId} siteName={siteName} startIso={iso(startMs)} endIso={iso(endMs)} />
      </ToolSection>
    </div>
  )
}
