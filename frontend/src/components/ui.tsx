import type React from 'react'
import type { ReactNode } from 'react'
import { Icon } from './Icon'

/* Every control here is a real button, anchor or input with a label, so Tab
   reaches it and a screen reader has something to announce. Minimum target
   48x48 whatever the visible mark is. */

const BASE =
  'inline-flex items-center justify-center gap-2 rounded-control font-semibold ' +
  'transition-colors duration-150 disabled:cursor-not-allowed select-none'

export function Button({
  children,
  variant = 'secondary',
  size = 'md',
  onClick,
  disabled,
  title,
  className = '',
  type = 'button',
  expanded,
  controls,
  describedBy,
  buttonRef,
}: {
  children: ReactNode
  variant?: 'primary' | 'secondary' | 'ghost'
  size?: 'md' | 'sm'
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void
  disabled?: boolean
  title?: string
  className?: string
  type?: 'button' | 'submit'
  expanded?: boolean
  controls?: string
  describedBy?: string
  buttonRef?: React.Ref<HTMLButtonElement>
}) {
  const variants = {
    primary:
      'bg-sun-fill text-on-sun hover:bg-sun-soft active:brightness-90 disabled:bg-inset disabled:text-ink-3',
    secondary:
      'border border-line-strong text-ink hover:bg-inset hover:border-ink-3 active:bg-panel disabled:border-line disabled:text-ink-3',
    ghost: 'text-ink-2 hover:bg-inset hover:text-ink active:bg-line disabled:text-line-strong',
  }
  const sizes = { md: 'h-12 px-4 text-[15px]', sm: 'h-12 px-3 text-[14px]' }
  return (
    <button
      ref={buttonRef}
      type={type}
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-expanded={expanded}
      aria-controls={controls}
      aria-describedby={describedBy}
      className={`${BASE} ${variants[variant]} ${sizes[size]} ${className}`}
    >
      {children}
    </button>
  )
}

export function IconButton({
  name,
  label,
  onClick,
  pressed,
  className = '',
  expanded,
  haspopup,
}: {
  name: Parameters<typeof Icon>[0]['name']
  label: string
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void
  pressed?: boolean
  className?: string
  expanded?: boolean
  haspopup?: 'dialog'
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={pressed}
      aria-expanded={expanded}
      aria-haspopup={haspopup}
      onClick={onClick}
      className={`inline-flex size-12 items-center justify-center rounded-control border border-line-strong text-ink hover:bg-inset ${className}`}
    >
      <Icon name={name} />
    </button>
  )
}

/** A filter chip. Selected state is never colour alone — it also gains a tick. */
export function Chip({
  children,
  selected,
  onClick,
  tone = 'neutral',
}: {
  children: ReactNode
  selected?: boolean
  onClick?: () => void
  tone?: 'neutral' | 'sun' | 'earth'
}) {
  const on =
    tone === 'sun'
      ? 'border-sun text-sun-soft bg-sun-deep'
      : tone === 'earth'
        ? 'border-earth text-earth-soft bg-earth-deep'
        : 'border-ink text-ink bg-inset'
  return (
    <button
      type="button"
      aria-pressed={!!selected}
      onClick={onClick}
      className={`inline-flex h-12 shrink-0 items-center gap-2 rounded-control border px-4 text-[14px] font-semibold whitespace-nowrap transition-colors ${
        selected ? on : 'border-line-strong text-ink-2 hover:bg-inset'
      }`}
    >
      {selected && <Icon name="check" size={16} strokeWidth={2.6} />}
      {children}
    </button>
  )
}

export function Panel({
  children,
  className = '',
  elevated = false,
  as: As = 'div',
}: {
  children: ReactNode
  className?: string
  elevated?: boolean
  as?: 'div' | 'section' | 'aside'
}) {
  return (
    <As
      className={
        elevated
          ? `border border-line-strong bg-raised shadow-[0_8px_24px_rgba(0,0,0,0.45)] ${className}`
          : `border border-line bg-panel ${className}`
      }
    >
      {children}
    </As>
  )
}

/**
 * A section's name. An `<h2>` (U9): panel titles were styled text, so each
 * page had one heading and screen-reader users could not move between
 * sections, which is how most of them navigate. Same classes, same look.
 * `as="div"` is for the rare label that names a control group, not a section.
 */
export function SectionLabel({
  children,
  className = '',
  as: As = 'h2',
  id,
}: {
  children: ReactNode
  className?: string
  as?: 'h2' | 'h3' | 'div'
  id?: string
}) {
  return (
    <As id={id} className={`text-[12px] font-semibold tracking-[0.12em] text-ink-3 uppercase ${className}`}>
      {children}
    </As>
  )
}

/**
 * A field no source confirms (§10.3). The word, in the uncertain ink, with the
 * reason as its title and accessible description. Never a dash, never blank,
 * never a value "for illustration".
 */
export function Unconfirmed({ asOf, className = '' }: { asOf?: string | null; className?: string }) {
  const why = `No source found for this field${asOf ? ` as of ${asOf}` : ''}`
  return (
    <span className={`text-uncertain ${className}`} title={why}>
      Unconfirmed
      <span className="sr-only">: {why.charAt(0).toLowerCase() + why.slice(1)}</span>
    </span>
  )
}

/** Visible on every screen. No number in this build is a flight value. */
/**
 * What the numbers on this screen were computed from.
 *
 * This badge used to read SAMPLE DATA unconditionally, and that was correct
 * when the build ran on a synthetic height field and a mean-element ephemeris.
 * It no longer does: terrain is the LOLA polar DEM and positions come from
 * SPICE with de440, so a permanent "sample data" label would now be the
 * dishonest option -- it would understate the work and teach a viewer to
 * ignore the badge.
 *
 * So it reports the actual state, from `/healthz`:
 *
 *   MEASURED  — kernels loaded and the elevation model present
 *   PARTIAL   — one of the two is missing; numbers are shown with what is known
 *   NO DATA   — nothing to compute from
 *
 * The visual treatment is unchanged in all three: same box, same hairline, same
 * uncertain icon. Only the word and the tooltip differ.
 */
export type Provenance = 'measured' | 'partial' | 'unavailable'

export const PROVENANCE_COPY: Record<Provenance, { label: string; title: string }> = {
  measured: {
    label: 'Measured',
    title:
      'Terrain from the LOLA lunar polar elevation model; Sun and Earth positions from SPICE with the DE440 ephemeris. Every value carries its own margin.',
  },
  partial: {
    label: 'Partial data',
    title:
      'Some inputs are missing, so parts of this screen are computed from less than the full model. Affected values say so where they appear.',
  },
  unavailable: {
    label: 'No data',
    title:
      'The geometry service has neither an ephemeris nor an elevation model loaded, so nothing on this screen is computed.',
  },
}

export function SampleDataBadge({ provenance = 'measured' }: { provenance?: Provenance }) {
  const copy = PROVENANCE_COPY[provenance]
  return (
    // role="status" rather than a bare span: this is the one element on screen
    // that says how much to trust everything else, and it changes when the
    // service's own state changes. A `title` alone is announced inconsistently
    // and, in Chrome's tree, was winning the accessible name outright -- so a
    // screen reader heard the explanation and never heard the word.
    <span
      role="status"
      aria-label={`Data provenance: ${copy.label}. ${copy.title}`}
      className="inline-flex h-7 items-center gap-2 border border-uncertain px-2.5 text-[11px] font-semibold tracking-[0.12em] text-ink-2 uppercase"
      title={copy.title}
    >
      <Icon name="uncertain" size={12} strokeWidth={2.4} aria-hidden="true" />
      {copy.label}
    </span>
  )
}

export function SearchField({
  value,
  onChange,
  placeholder = 'Site, crater or lat, lon',
  id = 'site-search',
}: {
  value: string
  onChange: (v: string) => void
  placeholder?: string
  id?: string
}) {
  return (
    <div className="flex h-12 items-center gap-2.5 rounded-control border border-line-strong bg-panel px-3.5 focus-within:border-focus">
      <Icon name="search" size={18} strokeWidth={1.8} className="shrink-0 text-ink-3" />
      <label htmlFor={id} className="sr-only">
        Search landing sites
      </label>
      <input
        id={id}
        type="text"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="min-w-0 grow bg-transparent text-[14px] outline-none placeholder:text-ink-3"
      />
    </div>
  )
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
  pill = false,
}: {
  options: { value: T; label: string }[]
  value: T
  onChange: (v: T) => void
  label: string
  pill?: boolean
}) {
  if (pill) {
    return (
      <div role="group" aria-label={label} className="inline-flex w-fit max-w-full gap-1 overflow-x-auto rounded-pill border border-line-strong bg-inset p-1">
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            aria-pressed={value === o.value}
            onClick={() => onChange(o.value)}
            className={`h-11 shrink-0 rounded-pill px-4 text-[13px] font-semibold whitespace-nowrap transition-colors ${
              value === o.value ? 'bg-ink text-canvas' : 'text-ink-2 hover:text-ink'
            }`}
          >
            {o.label}
          </button>
        ))}
      </div>
    )
  }
  return (
    // Scrolls sideways rather than clipping a segment at 320 px (WCAG 1.4.10).
    <div role="group" aria-label={label} className="inline-flex w-fit max-w-full overflow-x-auto rounded-control border border-line-strong">
      {options.map((o, i) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
          className={`h-12 shrink-0 px-4 text-[13px] font-semibold whitespace-nowrap transition-colors ${
            i > 0 ? 'border-l border-line-strong' : ''
          } ${value === o.value ? 'bg-ink text-canvas' : 'text-ink-2 hover:bg-inset hover:text-ink'}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

/** Shared SVG pattern defs. Mounted once, referenced by url(#id) anywhere. */
export function SvgDefs() {
  return (
    <svg width="0" height="0" className="absolute" aria-hidden="true">
      <defs>
        <pattern id="pw-blocked" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="7" height="7" fill="var(--color-dark-fill)" />
          <path d="M0 0 V7" stroke="var(--color-hatch)" strokeWidth="2.2" />
        </pattern>
        <pattern id="pw-alert" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="8" height="8" fill="var(--color-alert-deep)" />
          <path d="M0 0 V8" stroke="var(--color-alert)" strokeWidth="2.5" />
        </pattern>
        <pattern id="pw-uncertain" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)">
          <rect width="7" height="7" fill="none" />
          <path d="M0 0 V7" stroke="var(--color-uncertain)" strokeWidth="1.5" />
        </pattern>
        <pattern id="pw-psr" width="12" height="12" patternUnits="userSpaceOnUse">
          <rect width="12" height="12" fill="var(--color-psr)" />
          <circle cx="6" cy="6" r="1.2" fill="var(--color-terrain-mid)" />
        </pattern>
      </defs>
    </svg>
  )
}
