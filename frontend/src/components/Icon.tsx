import type { JSX } from 'react'

/**
 * The icon set: 24 grid, 1.6 stroke, round caps, no fills.
 * Never used without a text label or an aria-label.
 */
const PATHS: Record<string, JSX.Element> = {
  sun: (
    <>
      <circle cx="12" cy="14" r="4" />
      <path d="M2 18 H22" />
      <path d="M12 6 V3 M6 9 L4.5 7 M18 9 L19.5 7" />
    </>
  ),
  earth: (
    <>
      <circle cx="12" cy="12" r="7" />
      <path d="M5 12 H19" />
      <path d="M12 5 a10 10 0 0 0 0 14 a10 10 0 0 0 0 -14" />
    </>
  ),
  terminator: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 4 a8 8 0 0 0 0 16 Z" fill="currentColor" stroke="none" />
    </>
  ),
  pin: (
    <>
      <path d="M12 21 s7-6.5 7-11a7 7 0 1 0-14 0c0 4.5 7 11 7 11Z" />
      <circle cx="12" cy="10" r="2.4" />
    </>
  ),
  horizon: <path d="M2 19 L8 11 L12 15 L16 7 L22 19 Z" />,
  clocks: (
    <>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="4.5" />
      <path d="M12 3 V7.5" />
    </>
  ),
  gap: (
    <>
      <path d="M3 12 H8 M16 12 H21" />
      <path d="M10 8 V16 M14 8 V16" />
    </>
  ),
  compare: <path d="M5 20 V10 M12 20 V4 M19 20 V14" />,
  search: (
    <>
      <circle cx="11" cy="11" r="6.5" />
      <path d="M16 16 L21 21" />
    </>
  ),
  filter: <path d="M3 6 H21 L14 13 V20 L10 18 V13 Z" />,
  layers: (
    <>
      <path d="M12 3 L21 8 L12 13 L3 8 Z" />
      <path d="M3 13 L12 18 L21 13" />
    </>
  ),
  export: (
    <>
      <path d="M12 15 V4 M8 8 L12 4 L16 8" />
      <path d="M4 15 V20 H20 V15" />
    </>
  ),
  alert: (
    <>
      <path d="M12 3 L22 20 H2 Z" />
      <path d="M12 10 V14" />
      <path d="M12 17 h0.01" />
    </>
  ),
  table: (
    <>
      <rect x="3" y="5" width="18" height="14" />
      <path d="M3 10 H21 M9 5 V19 M15 5 V19" />
    </>
  ),
  play: <path d="M7 4 L19 12 L7 20 Z" />,
  pause: <path d="M9 5 V19 M15 5 V19" />,
  psr: (
    <>
      <rect x="3" y="10" width="18" height="10" />
      <path d="M7.5 10 V6.5 a4.5 4.5 0 0 1 9 0 V10" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11 V17" />
      <path d="M12 7.5 h0.01" />
    </>
  ),
  keyboard: (
    <>
      <rect x="2" y="6" width="20" height="12" />
      <path d="M6 10 h1 M10 10 h1 M14 10 h1 M18 10 h0.5 M7 14 h10" />
    </>
  ),
  uncertain: (
    <>
      <circle cx="12" cy="12" r="8.5" strokeDasharray="3 2.5" />
      <path d="M12 8 V13" />
      <path d="M12 16 h0.01" />
    </>
  ),
  back: <path d="M15 5 L8 12 L15 19" />,
  check: <path d="M4 12 L10 18 L20 6" />,
  chevron: <path d="M6 9 L12 15 L18 9" />,
  close: <path d="M6 6 L18 18 M18 6 L6 18" />,
  settings: (
    <>
      <path d="M4 7 H20 M4 12 H20 M4 17 H20" />
      <circle cx="9" cy="7" r="2" />
      <circle cx="15" cy="12" r="2" />
      <circle cx="8" cy="17" r="2" />
    </>
  ),
  log: (
    <>
      <path d="M8 6 H20 M8 12 H20 M8 18 H20" />
      <path d="M4 6 h0.01 M4 12 h0.01 M4 18 h0.01" />
    </>
  ),
  /* The six mission steps' states: shape, never colour alone. */
  dot: <circle cx="12" cy="12" r="5" fill="currentColor" />,
  ring: <circle cx="12" cy="12" r="5.5" />,
  quarter: (
    <>
      <circle cx="12" cy="12" r="6" />
      <path d="M12 12 V6 A6 6 0 0 1 18 12 Z" fill="currentColor" />
    </>
  ),
  pencil: (
    <>
      <path d="M15 5 L19 9 L9 19 H5 V15 Z" />
      <path d="M13 7 L17 11" />
    </>
  ),
  dash: <path d="M7 12 H17" />,
  link: (
    <>
      <path d="M10 14 L20 4 M14 4 H20 V10" />
      <path d="M18 14 V20 H4 V6 H10" />
    </>
  ),
  plus: <path d="M12 5 V19 M5 12 H19" />,
  speaker: (
    <>
      <path d="M11 5 L6 9 H3 V15 H6 L11 19 Z" />
      <path d="M15.5 8.5 a5 5 0 0 1 0 7" />
      <path d="M18.5 5.5 a9 9 0 0 1 0 13" />
    </>
  ),
}

export type IconName = keyof typeof PATHS

export function Icon({
  name,
  size = 20,
  className = '',
  strokeWidth = 1.6,
  label,
}: {
  name: IconName
  size?: number
  className?: string
  strokeWidth?: number
  label?: string
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      {PATHS[name]}
    </svg>
  )
}

/** The mark. A low sun sitting exactly on the horizon, framed by a window. */
export function Mark({ size = 26, className = '' }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} role="img" aria-label="Polar Window">
      <rect x="2.75" y="2.75" width="18.5" height="18.5" fill="var(--color-psr)" />
      <rect x="2.75" y="15" width="18.5" height="6.25" fill="var(--color-terrain-low)" />
      <path d="M8 15 a4 4 0 0 1 8 0 z" fill="var(--color-sun-fill)" />
      <path d="M2.75 15 H21.25" stroke="var(--color-terrain-high)" strokeWidth="1.1" />
      <rect x="2.75" y="2.75" width="18.5" height="18.5" fill="none" stroke="var(--color-ink)" strokeWidth="1.5" />
    </svg>
  )
}

export function Wordmark({ className = '' }: { className?: string }) {
  return (
    <span className={`text-body font-semibold tracking-caps-xl ${className}`}>
      POLAR<span className="font-normal text-sun">&nbsp;WINDOW</span>
    </span>
  )
}
