import type { InstrumentType } from '../lib/api/adapters'
import { INSTRUMENT_LABEL } from '../lib/missions'

/**
 * One small line drawing per kind of payload, drawn in the ink colour on a
 * 16 px grid. A picture beside its label, never in place of it.
 */
const PATHS: Record<InstrumentType, string> = {
  // A drop of water.
  volatiles: 'M8 2.5C8 2.5 3.5 7.5 3.5 10a4.5 4.5 0 0 0 9 0C12.5 7.5 8 2.5 8 2.5Z',
  // Layers of rock.
  geology_geophysics: 'M2 11.5h12M3.5 8h9M5 4.5h6M2 11.5 5 4.5M14 11.5 11 4.5',
  // A thermometer.
  heat_flow: 'M7 2.5h2v7.2a2.8 2.8 0 1 1-2 0Z',
  // A radiating point.
  radiation_space_weather: 'M8 6.5v3M6.5 8h3M8 2v2M8 12v2M2 8h2M12 8h2M3.8 3.8l1.4 1.4M10.8 10.8l1.4 1.4M3.8 12.2l1.4-1.4M10.8 5.2l1.4-1.4',
  // Dust grains over the ground.
  exosphere_dust: 'M2 13h12M4.5 9.5h.01M8 7h.01M11.5 9.5h.01M6 4.5h.01M10.5 4h.01',
  // A camera.
  imaging: 'M2.5 5h2.5l1-1.5h4l1 1.5h2.5v7.5h-11Z M8 10.8a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z',
  // A lander's legs.
  landing_navigation: 'M5 3.5h6v4H5Z M5 7.5 2.5 12.5M11 7.5l2.5 5M8 7.5v5M1.5 12.5h3M11.5 12.5h3',
  // An antenna dish.
  communications: 'M3 4.5a7 7 0 0 0 8.5 8.5Z M7.3 8.7 12 4M12 4h.01',
  // A corner cube.
  laser_retroreflector: 'M3 3h10v10H3Z M3 3l10 10M13 3 8 8',
  // A rover.
  rover_mobility: 'M3.5 6h9v3.5h-9Z M5 12.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3ZM11 12.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z M8 6V3.5h2',
  // A gear.
  technology_demo: 'M8 5.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5Z M8 2v2M8 12v2M2 8h2M12 8h2M3.8 3.8l1.4 1.4M10.8 10.8l1.4 1.4M3.8 12.2l1.4-1.4M10.8 5.2l1.4-1.4',
  // A plain box.
  other: 'M3 3.5h10v9H3Z',
}

export function PayloadIcon({ type, size = 14 }: { type: InstrumentType; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="shrink-0"
    >
      <path d={PATHS[type]} />
    </svg>
  )
}

/** At most three payload kinds as small icon chips, then how many more. */
export function PayloadChips({ types }: { types: InstrumentType[] }) {
  if (!types.length) return <span className="text-caption leading-caption text-ink-3">Payloads not published yet</span>
  const shown = types.slice(0, 3)
  const more = types.length - shown.length
  return (
    <span className="flex flex-wrap items-center gap-1.5">
      {shown.map((t) => (
        <span
          key={t}
          className="inline-flex items-center gap-1 rounded-pill border border-line bg-tray px-2 py-0.5 text-caption leading-caption text-ink-2"
        >
          <PayloadIcon type={t} size={12} />
          {INSTRUMENT_LABEL[t]}
        </span>
      ))}
      {more > 0 && <span className="text-caption leading-caption text-ink-3">{more} more</span>}
    </span>
  )
}
