import type React from 'react'
import { useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { Icon } from './Icon'
import { Indicator } from './ui/Indicator'
import { easeOut, useMotionClass, useReducedMotion } from '../hooks/useMotion'
import { durationMs } from '../lib/motion'

/* Every control here is a real button, anchor or input with a label, so Tab
   reaches it and a screen reader has something to announce. Minimum target
   48x48 whatever the visible mark is. */

/* Pills (decision D2). Every one gives a little under the finger (.pw-press). */
const BASE =
  'pw-press group inline-flex items-center justify-center gap-2 rounded-pill font-semibold disabled:cursor-not-allowed select-none'

const VARIANTS = {
  primary:
    // Ink, not amber: amber means sunlight in every chart, so a button in it
    // read as part of the data.
    'bg-ink text-canvas hover:bg-ink-2 active:brightness-90 disabled:bg-inset disabled:text-ink-3',
  secondary:
    'border border-line-strong bg-tray text-ink hover:bg-inset hover:border-ink-3 disabled:border-line disabled:text-ink-3',
  // A hairline, so a quiet button still reads as a control and not as plain text beside its neighbours.
  ghost: 'border border-line text-ink-2 hover:border-line-strong hover:bg-inset hover:text-ink disabled:text-line-strong',
}

/**
 * A link drawn as a pill button, for a router `Link` that takes the person to
 * another page. The primary one carries the arrow (`PillArrow`).
 */
export function pillClass(variant: 'primary' | 'secondary' | 'ghost' = 'secondary', arrow = false): string {
  return `${BASE} h-12 text-control no-underline ${arrow ? 'pl-5 pr-2' : 'px-5'} ${VARIANTS[variant]}`
}

/**
 * A label that keeps the width of its bold self (rule 3 of the motion
 * grammar), so a choice that turns bold when chosen moves nothing beside it.
 * The bold copy is generated content in a hidden, unannounced box.
 */
export function Hold({ text }: { text: string }) {
  return (
    <span className="pw-hold" data-pw-label="">
      <span>{text}</span>
      <span aria-hidden="true" className="pw-hold-wide" data-text={text} />
    </span>
  )
}

/**
 * A button's label that can change ("Work it out", "Working it out…") in a box
 * as wide as the widest of them (`room`: the others, up to two), so the button
 * keeps its place (rule 3). The new label settles into place at once, readable
 * at every frame. The others are generated content in a hidden, unannounced
 * box: the button's name is only the label in use.
 */
export function SwapLabel({ label, room }: { label: string; room: string[] }) {
  const first = useRef(label)
  const changed = useRef(false)
  if (label !== first.current) changed.current = true
  const settle = useMotionClass('pw-swap-in')
  return (
    <span className="pw-swap">
      <span key={label} className={changed.current ? settle : undefined}>
        {label}
      </span>
      <span aria-hidden="true" className="pw-swap-room" data-a={room[0] ?? ''} data-b={room[1] ?? ''} />
    </span>
  )
}

/** The arrow in its own circle, at the end of a primary pill. */
export function PillArrow() {
  return (
    <span className="pw-orb ml-1" aria-hidden="true">
      <Icon name="arrow" size={15} strokeWidth={2} />
    </span>
  )
}

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
  arrow = false,
  room,
}: {
  children: ReactNode
  /** A trailing arrow in its own circle: for the one button that takes the person onward. */
  arrow?: boolean
  /** The other labels this button can show (a string label only): it keeps the widest one's width (SwapLabel). */
  room?: string[]
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
  const sizes = arrow
    ? { md: 'h-12 pl-5 pr-2 text-control', sm: 'h-12 pl-4 pr-2 text-body' }
    : { md: 'h-12 px-5 text-control', sm: 'h-12 px-4 text-body' }
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
      className={`${BASE} ${VARIANTS[variant]} ${sizes[size]} ${className}`}
    >
      {room && typeof children === 'string' ? <SwapLabel label={children} room={room} /> : children}
      {arrow && <PillArrow />}
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
      className={`pw-press inline-flex size-12 items-center justify-center rounded-pill border border-line-strong bg-tray text-ink hover:border-ink-3 hover:bg-inset aria-pressed:bg-inset ${className}`}
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
      className={`pw-press inline-flex h-12 shrink-0 items-center gap-2 rounded-pill border px-4 text-body font-semibold whitespace-nowrap ${
        selected ? on : 'border-line-strong bg-tray text-ink-2 hover:bg-inset hover:text-ink'
      }`}
    >
      {selected && <Icon name="check" size={16} strokeWidth={2.6} />}
      {children}
    </button>
  )
}

/**
 * A card: a tray holding a lit core (`.pw-card` in globals.css). One element,
 * so callers lay it out exactly as before. `elevated` floats it over the page;
 * `quiet` drops its shadow (a group, a list); `flush` clips content that runs
 * to its edges (a list, a table) to the rounded core; `alert` is for a card
 * about something over the battery limit, always with the triangle and words.
 */
export function Panel({
  children,
  className = '',
  elevated = false,
  quiet = false,
  flush = false,
  alert = false,
  as: As = 'div',
  guide,
}: {
  children: ReactNode
  className?: string
  elevated?: boolean
  quiet?: boolean
  flush?: boolean
  alert?: boolean
  as?: 'div' | 'section' | 'aside'
  /** Where the guide bar can point (`data-guide`). */
  guide?: string
}) {
  const kind = [
    'pw-card',
    elevated ? 'pw-card-raised' : '',
    quiet ? 'pw-card-quiet' : '',
    flush ? 'pw-card-flush' : '',
    alert ? 'pw-card-alert' : '',
  ]
    .filter(Boolean)
    .join(' ')
  return (
    <As data-guide={guide} className={`${kind} ${className}`}>
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
      className={`pw-row pw-card pw-card-quiet pw-card-flush group ${className}`}
      onToggle={(e) => {
        if ((e.currentTarget as HTMLDetailsElement).open) onOpen?.()
      }}
    >
      <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-control font-semibold text-ink transition-colors duration-[var(--pw-dur-quick)] hover:bg-inset sm:px-5 [&::-webkit-details-marker]:hidden">
        <span className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-0.5">
          <span>{title}</span>
          {meta && <span className="text-small font-normal text-ink-3">{meta}</span>}
        </span>
        <span className="pw-turn flex size-8 shrink-0 items-center justify-center rounded-pill bg-inset text-ink-2 group-open:rotate-180 group-hover:bg-line-strong" aria-hidden="true">
          <Icon name="chevron" size={15} strokeWidth={2} />
        </span>
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
    <section aria-labelledby={title ? id : undefined} className={`flex min-w-0 flex-col gap-3 ${className}`}>
      {title && (
        <h3 id={id} className="pw-eyebrow px-1">
          {title}
        </h3>
      )}
      <div className="pw-rows pw-card pw-card-quiet pw-card-flush flex flex-col">{children}</div>
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
    <As id={id} className={`text-control font-semibold tracking-title text-ink ${className}`}>
      {children}
    </As>
  )
}

/**
 * The small capitals above a group or a page's answer: what the block below
 * is about. A heading when it names a section (`as`), a paragraph otherwise.
 */
export function Eyebrow({
  children,
  className = '',
  as: As = 'p',
  id,
}: {
  children: ReactNode
  className?: string
  as?: 'p' | 'h2' | 'h3' | 'div' | 'span'
  id?: string
}) {
  return (
    <As id={id} className={`pw-eyebrow ${className}`}>
      {children}
    </As>
  )
}

/**
 * A whole number that counts up to its value once, when it first appears, on
 * the settle curve over the arrival duration (`--pw-dur-arrive`). Assistive
 * technology reads only the value itself, never a number on the way to it;
 * the digits keep their width (tabular) so nothing beside them moves. After
 * the first count a new value is shown at once, and under reduced motion
 * there is no count at all. The count writes to its own text node, not to
 * React state (no frame loop re-renders anything).
 */
export function CountUp({ value, className = '' }: { value: number; className?: string }) {
  const reduced = useReducedMotion()
  const digits = useRef<HTMLSpanElement>(null)
  const settled = useRef(false)
  useLayoutEffect(() => {
    const node = digits.current?.firstChild
    const plain = reduced || !Number.isFinite(value) || value <= 0 || typeof requestAnimationFrame === 'undefined'
    if (!(node instanceof Text)) return
    if (settled.current || plain) {
      settled.current = true
      node.nodeValue = String(value)
      return
    }
    const ms = durationMs('--pw-dur-arrive', 820)
    const t0 = performance.now()
    let raf = 0
    node.nodeValue = '0'
    const tick = (now: number) => {
      const k = easeOut(Math.min(1, (now - t0) / ms))
      node.nodeValue = String(Math.round(value * k))
      if (k < 1) raf = requestAnimationFrame(tick)
      else settled.current = true
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value, reduced])
  return (
    <span className={`tnum ${className}`}>
      <span ref={digits} aria-hidden="true" className="inline-block text-right" style={{ minWidth: `${String(value).length}ch` }}>
        {String(value)}
      </span>
      <span className="sr-only">{value}</span>
    </span>
  )
}

/**
 * A row opened by a button (rule 3), for bodies that are not a `<details>`:
 * the body sits in a `.pw-open-row` box that grows from nothing to its
 * content, pushing what is below, and closes the same way on the leave curve.
 * Put `ref` on that box and `hidden` on it (and on the body, where a caller
 * reads the body's own `hidden`): `hidden` turns true only once the row has
 * closed, and false at once on opening. The first open state is drawn
 * without motion. Under reduced motion it opens and closes at once.
 */
export function useOpenRow<T extends HTMLElement = HTMLDivElement>(open: boolean) {
  const ref = useRef<T>(null)
  const reduced = useReducedMotion()
  const [shown, setShown] = useState(open)
  const mounted = useRef(false)
  if (open && !shown) setShown(true)
  useLayoutEffect(() => {
    const el = ref.current
    const first = !mounted.current
    mounted.current = true
    if (!el) return
    if (open) {
      if (!el.hasAttribute('data-open')) {
        // From a drawn, closed box: read its closed height first, so the change is a transition.
        if (!first && !reduced) void getComputedStyle(el).gridTemplateRows
        el.setAttribute('data-open', '')
      }
      return
    }
    el.removeAttribute('data-open')
    if (!shown) return
    if (reduced || first) {
      setShown(false)
      return
    }
    const t = window.setTimeout(() => setShown(false), durationMs('--pw-dur-base', 240))
    return () => window.clearTimeout(t)
  }, [open, shown, reduced])
  return { ref, hidden: !shown }
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
      className="inline-flex h-7 shrink-0 items-center gap-2 rounded-pill border border-uncertain px-3 text-tag font-semibold tracking-caps text-ink-2 uppercase"
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
    <div className="flex h-12 items-center gap-2.5 rounded-pill border border-field bg-tray px-4 transition-colors duration-[var(--pw-dur-quick)] focus-within:border-focus hover:border-ink-3">
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
        className="h-full min-w-0 grow bg-transparent text-body outline-none placeholder:text-ink-3"
      />
    </div>
  )
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: T; label: string }[]
  value: T
  onChange: (v: T) => void
  label: string
  /** Kept for callers; every segmented control is a pill now (decision D2). */
  pill?: boolean
}) {
  return (
    // Scrolls sideways rather than clipping a segment at 320 px (WCAG 1.4.10).
    // Each segment is a full 48 px target; the chosen one is drawn as a pill
    // inset inside it (a clear 4 px border, the fill kept inside it), so the
    // target never shrinks to the drawing. The pill is one indicator that
    // slides to the segment chosen (rule 2).
    <div
      role="group"
      aria-label={label}
      className="pw-ind-host inline-flex w-fit max-w-full overflow-x-auto rounded-pill border border-line-strong bg-tray"
    >
      {options.map((o) => {
        const on = value === o.value
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={on}
            data-pw-item={o.value}
            data-pw-on={on || undefined}
            onClick={() => onChange(o.value)}
            className={`pw-press h-[46px] shrink-0 rounded-pill border-4 border-transparent bg-clip-padding px-3 text-small font-semibold whitespace-nowrap first-of-type:pl-4 last-of-type:pr-4 ${
              on ? 'text-ink' : 'text-ink-2 hover:text-ink'
            }`}
          >
            {o.label}
          </button>
        )
      })}
      <Indicator selected={value} inset={4} />
    </div>
  )
}

/**
 * A panel that scrolls sideways when its content is wider than the screen: a
 * named region that takes focus, so a keyboard user can scroll it with the
 * arrow keys (WCAG 2.1.1). Content with its own controls does not need one.
 *
 * While there is more to reach, the edge it can be scrolled towards fades
 * (a mask, so no colour of its own) and the words "Scrolls sideways" stand
 * under it, so a table cut at the screen's edge is not taken for a whole one.
 * The fade steps aside while the region has the keyboard's focus, so the
 * focus ring is whole.
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
  const ref = useRef<HTMLDivElement>(null)
  const [more, setMore] = useState({ before: false, after: false })
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = () => {
      const room = el.scrollWidth - el.clientWidth
      const before = room > 1 && el.scrollLeft > 1
      const after = room > 1 && el.scrollLeft < room - 1
      setMore((m) => (m.before === before && m.after === after ? m : { before, after }))
    }
    measure()
    el.addEventListener('scroll', measure, { passive: true })
    if (typeof ResizeObserver === 'undefined') return () => el.removeEventListener('scroll', measure)
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    if (el.firstElementChild) ro.observe(el.firstElementChild)
    return () => {
      el.removeEventListener('scroll', measure)
      ro.disconnect()
    }
  }, [])
  const fade = more.before || more.after
  // Opaque in the middle, clear at an edge with more beyond it (only the shape of a mask counts, not its colour).
  const edge = '2.5rem'
  const solid = 'var(--color-ink)'
  const mask = fade
    ? `linear-gradient(to right, ${more.before ? 'transparent' : solid}, ${solid} ${more.before ? edge : '0%'}, ${solid} calc(100% - ${more.after ? edge : '0px'}), ${more.after ? 'transparent' : solid})`
    : undefined
  return (
    <>
      <div
        ref={ref}
        role="region"
        aria-label={label}
        tabIndex={0}
        style={mask ? ({ '--pw-scroll-fade': mask } as React.CSSProperties) : undefined}
        className={`relative overflow-x-auto [mask-image:var(--pw-scroll-fade,none)] focus-visible:[mask-image:none] ${className}`}
      >
        {children}
      </div>
      {fade && (
        <p aria-hidden="true" className="text-caption leading-caption text-ink-3">
          Scrolls sideways
        </p>
      )}
    </>
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
    <div
      role="tablist"
      aria-label={label}
      onKeyDown={move}
      className={`pw-ind-host flex overflow-x-auto md:flex-col md:overflow-visible ${className}`}
    >
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
            data-pw-item={t.id}
            data-pw-on={on || undefined}
            onClick={() => onChange(t.id)}
            // A pill, the chosen one in ink: the same language as the page's other switches.
            // The ink is one indicator that slides to the tab chosen (rule 2), and the
            // name is drawn over it in the canvas colour at every frame, so it is never
            // on a ground it cannot be read against. Each name keeps its bold width.
            className={`pw-press flex h-12 shrink-0 items-center rounded-pill border-4 border-transparent bg-clip-padding px-4 text-body whitespace-nowrap ${
              on ? 'font-semibold text-ink' : 'font-medium text-ink-2 hover:bg-inset hover:text-ink'
            }`}
          >
            <Hold text={t.label} />
          </button>
        )
      })}
      <Indicator selected={value} inset={4} />
    </div>
  )
}
