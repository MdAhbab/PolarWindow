import type React from 'react'
import { useId, type ReactNode } from 'react'
import { Icon } from './Icon'

/* Every control here is a real button, anchor or input with a label, so Tab
   reaches it and a screen reader has something to announce. Minimum target
   48x48 whatever the visible mark is. */

const BASE =
  'inline-flex items-center justify-center gap-2 rounded-control font-semibold ' +
  'transition-[background-color,border-color,color] duration-[var(--pw-dur-quick)] disabled:cursor-not-allowed select-none'

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
      // Ink, not amber: amber means sunlight in every chart, so a button in it
      // read as part of the data.
      'bg-ink text-canvas hover:bg-ink-2 active:brightness-90 disabled:bg-inset disabled:text-ink-3',
    secondary:
      'border border-line-strong text-ink hover:bg-inset hover:border-ink-3 active:bg-panel disabled:border-line disabled:text-ink-3',
    ghost: 'text-ink-2 hover:bg-inset hover:text-ink active:bg-line disabled:text-line-strong',
  }
  const sizes = { md: 'h-12 px-4 text-control', sm: 'h-12 px-3 text-body' }
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
  guide,
}: {
  name: Parameters<typeof Icon>[0]['name']
  label: string
  /** Where the guide bar can point (`data-guide`). */
  guide?: string
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
      data-guide={guide}
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
      className={`inline-flex h-12 shrink-0 items-center gap-2 rounded-control border px-4 text-body font-semibold whitespace-nowrap transition-colors ${
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
  guide,
}: {
  children: ReactNode
  className?: string
  elevated?: boolean
  as?: 'div' | 'section' | 'aside'
  /** Where the guide bar can point (`data-guide`). */
  guide?: string
}) {
  return (
    <As
      data-guide={guide}
      className={
        elevated
          ? `border border-line-strong bg-raised shadow-raised ${className}`
          : `border border-line bg-panel ${className}`
      }
    >
      {children}
    </As>
  )
}

/**
 * Detail on request: a closed row that opens in place. Every "more about this"
 * on every screen is one of these, so the pattern is learned once. `onOpen`
 * runs the first time it opens (an AI answer is asked for then, not on a
 * second click inside).
 */
export function Disclosure({
  title,
  meta,
  children,
  guide,
  onOpen,
  defaultOpen,
  className = '',
}: {
  title: ReactNode
  /** A short value beside the title, readable without opening it. */
  meta?: ReactNode
  children: ReactNode
  guide?: string
  onOpen?: () => void
  /** Open when it first appears: for a row whose own control puts the page back to work and brings it back. */
  defaultOpen?: boolean
  className?: string
}) {
  return (
    <details
      open={defaultOpen}
      data-guide={guide}
      className={`pw-row group border border-line bg-panel ${className}`}
      onToggle={(e) => {
        if ((e.currentTarget as HTMLDetailsElement).open) onOpen?.()
      }}
    >
      <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between gap-3 px-4 py-2.5 text-control font-medium text-ink transition-colors duration-[var(--pw-dur-quick)] hover:bg-inset sm:px-5 [&::-webkit-details-marker]:hidden">
        <span className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-0.5">
          <span>{title}</span>
          {meta && <span className="text-small font-normal text-ink-3">{meta}</span>}
        </span>
        <Icon
          name="chevron"
          size={16}
          strokeWidth={2}
          className="shrink-0 text-ink-3 transition-transform duration-[var(--pw-dur-base)] ease-[var(--ease-settle)] group-open:rotate-180"
        />
      </summary>
      <div className="pw-disclosure-body flex flex-col gap-4 px-4 pt-1 pb-5 sm:px-5">{children}</div>
    </details>
  )
}

/**
 * Closed rows that belong together, under one short heading: a section's
 * "Details", "How this was worked out" and "Sources". Inside a group the rows
 * share their borders, so three rows read as one list, not three boxes.
 */
export function RowGroup({ title, children, className = '' }: { title?: string; children: ReactNode; className?: string }) {
  const id = useId()
  return (
    <section aria-labelledby={title ? id : undefined} className={`flex min-w-0 flex-col gap-2 ${className}`}>
      {title && (
        <h3 id={id} className="text-small font-semibold text-ink-2">
          {title}
        </h3>
      )}
      <div className="pw-rows flex flex-col">{children}</div>
    </section>
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
    <As id={id} className={`text-small font-semibold tracking-title text-ink-2 ${className}`}>
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
export type Provenance = 'measured' | 'partial' | 'unavailable' | 'snapshot'

export const PROVENANCE_COPY: Record<Provenance, { label: string; title: string }> = {
  measured: {
    label: 'Measured',
    title:
      'Terrain from NASA’s laser-altimeter map of the pole (LOLA); Sun and Earth positions calculated with NASA’s SPICE tools (DE440). Every value shows how far it could be off.',
  },
  partial: {
    label: 'Partial data',
    title:
      'Some data is missing, so parts of this screen are worked out from less than usual. The values affected say so where they appear.',
  },
  snapshot: {
    label: 'Saved copy',
    title:
      'The live service is not answering, so these are saved answers from it, shown exactly as it gave them. Views that were not saved say so.',
  },
  unavailable: {
    label: 'No data',
    title:
      'The service has neither the Sun and Earth positions nor the terrain map loaded, so nothing on this screen can be worked out.',
  },
}

export function SampleDataBadge({ provenance = 'measured', note }: { provenance?: Provenance; note?: string }) {
  const copy = PROVENANCE_COPY[provenance]
  const title = note ? `${copy.title} ${note}` : copy.title
  return (
    // role="status" rather than a bare span: this is the one element on screen
    // that says how much to trust everything else, and it changes when the
    // service's own state changes. A `title` alone is announced inconsistently
    // and, in Chrome's tree, was winning the accessible name outright -- so a
    // screen reader heard the explanation and never heard the word.
    <span
      role="status"
      aria-label={`Data source: ${copy.label}. ${title}`}
      className="inline-flex h-7 items-center gap-2 border border-uncertain px-2.5 text-tag font-semibold tracking-caps text-ink-2 uppercase"
      title={title}
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
        className="min-w-0 grow bg-transparent text-body outline-none placeholder:text-ink-3"
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
            className={`h-11 shrink-0 rounded-pill px-4 text-small font-semibold whitespace-nowrap transition-colors ${
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
          className={`h-12 shrink-0 px-4 text-small font-semibold whitespace-nowrap transition-colors ${
            i > 0 ? 'border-l border-line-strong' : ''
          } ${value === o.value ? 'bg-ink text-canvas' : 'text-ink-2 hover:bg-inset hover:text-ink'}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

/**
 * A panel that scrolls sideways when its content is wider than the screen: a
 * named region that takes focus, so a keyboard user can scroll it with the
 * arrow keys (WCAG 2.1.1). Content with its own controls does not need one.
 */
export function ScrollRegion({
  label,
  children,
  className = '',
}: {
  label: string
  children: ReactNode
  className?: string
}) {
  return (
    <div role="region" aria-label={label} tabIndex={0} className={`relative overflow-x-auto ${className}`}>
      {children}
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

/**
 * Tabs: one row of choices, one panel. The keyboard pattern is the usual
 * one: Tab reaches the chosen tab, the arrow keys move and choose, Home and
 * End go to the ends. The caller draws the panel with `role="tabpanel"`,
 * `id={`${baseId}-panel`}` and `aria-labelledby={`${baseId}-${value}`}`.
 * Vertical from `md` when the caller's class makes it a column.
 */
export function Tabs<T extends string>({
  label,
  baseId,
  tabs,
  value,
  onChange,
  className = '',
}: {
  label: string
  baseId: string
  tabs: { id: T; label: string }[]
  value: T
  onChange: (v: T) => void
  className?: string
}) {
  const move = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const i = tabs.findIndex((t) => t.id === value)
    const next =
      e.key === 'ArrowRight' || e.key === 'ArrowDown'
        ? (i + 1) % tabs.length
        : e.key === 'ArrowLeft' || e.key === 'ArrowUp'
          ? (i - 1 + tabs.length) % tabs.length
          : e.key === 'Home'
            ? 0
            : e.key === 'End'
              ? tabs.length - 1
              : null
    if (next === null) return
    e.preventDefault()
    onChange(tabs[next].id)
    document.getElementById(`${baseId}-${tabs[next].id}`)?.focus()
  }
  return (
    <div role="tablist" aria-label={label} onKeyDown={move} className={`flex overflow-x-auto md:flex-col md:overflow-visible ${className}`}>
      {tabs.map((t) => {
        const on = t.id === value
        return (
          <button
            key={t.id}
            id={`${baseId}-${t.id}`}
            type="button"
            role="tab"
            aria-selected={on}
            aria-controls={`${baseId}-panel`}
            tabIndex={on ? 0 : -1}
            onClick={() => onChange(t.id)}
            className={`relative flex h-12 shrink-0 items-center px-4 text-body whitespace-nowrap transition-colors duration-[var(--pw-dur-quick)] md:px-5 ${
              on ? 'font-semibold text-ink' : 'font-medium text-ink-2 hover:bg-inset hover:text-ink'
            }`}
          >
            {on && <span aria-hidden="true" className="absolute inset-x-3 bottom-0 h-[3px] bg-ink md:inset-x-auto md:inset-y-2 md:left-0 md:h-auto md:w-[3px]" />}
            {t.label}
          </button>
        )
      })}
    </div>
  )
}
