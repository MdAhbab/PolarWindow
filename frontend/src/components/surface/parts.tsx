/**
 * Small pieces the lander tools share: the closed heading each tool sits
 * behind, the provenance tag beside every figure, and a number with its margin.
 */
import { useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import type { ProvenanceWord, QuantityDTO } from '../../lib/api/surface.types'
import { quantityWords } from './helpers'
import { Icon } from '../Icon'
import { useOpenRow } from '../ui'

const PROV_TITLE: Record<ProvenanceWord, string> = {
  computed: 'Worked out by this service from the data and the figures given',
  published: 'Published by the source linked beside it',
  entered: 'Typed in by you',
  assumed: 'Assumed: not a published or measured figure',
}

/**
 * Where a figure came from, in words. Shape tells them apart without colour:
 * assumed wears the dashed scenario hatch, entered a solid outline, published
 * an underline, computed nothing extra.
 */
export function ProvTag({ p, detail, className = '' }: { p: ProvenanceWord; detail?: string; className?: string }) {
  const shape =
    p === 'assumed'
      ? 'pw-scenario rounded-sm px-1'
      : p === 'entered'
        ? 'rounded-sm border border-ink-2 px-1 text-ink-2'
        : p === 'published'
          ? 'underline decoration-dotted underline-offset-2'
          : ''
  return (
    <span
      title={detail ? `${PROV_TITLE[p]}: ${detail}` : PROV_TITLE[p]}
      className={`inline-block font-mono text-micro leading-4 tracking-caps-sm whitespace-nowrap text-ink-3 uppercase ${shape} ${className}`}
    >
      {p}
    </span>
  )
}

/** A key quantity: its label, number and unit, the margin (or why it has none) and the provenance. */
export function QuantityCell({
  label,
  q,
  digits,
  note,
}: {
  label: string
  q: QuantityDTO
  digits?: number
  note?: ReactNode
}) {
  const w = quantityWords(q, digits)
  return (
    <div className="flex min-w-0 flex-col gap-1 border-t border-line pt-3">
      <dt className="text-caption leading-caption text-ink-2">{label}</dt>
      <dd className="flex flex-wrap items-baseline gap-x-1.5">
        <span className="font-mono text-figure-sm tracking-figure-sm text-ink tabular-nums">{w.value}</span>
        {w.unit && <span className="text-small text-ink-2">{w.unit}</span>}
      </dd>
      <dd className={`text-caption leading-caption ${w.marginIsReason ? 'text-ink-3' : 'font-mono text-ink-2 tabular-nums'}`}>
        {w.margin}
      </dd>
      {note && <dd className="text-caption leading-caption text-ink-2">{note}</dd>}
      <dd>
        <ProvTag p={w.provenance} />
      </dd>
    </div>
  )
}

/**
 * A tool closed behind its heading until opened: the heading is a real `<h2>`
 * (screen-reader users move by headings) holding the button that opens it.
 */
export function ToolSection({
  title,
  lede,
  children,
  guide,
}: {
  title: string
  lede: string
  children: ReactNode
  guide?: string
}) {
  const [open, setOpen] = useState(false)
  const row = useOpenRow(open)
  const id = useId()
  return (
    <section data-guide={guide} aria-labelledby={`${id}-h`} className="pw-card pw-card-quiet flex min-w-0 flex-col">
      <h2 id={`${id}-h`} className="m-0">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={`${id}-body`}
          onClick={() => setOpen((o) => !o)}
          className="flex min-h-14 w-full cursor-pointer items-center justify-between gap-3 rounded-[inherit] px-4 py-3 text-left hover:bg-inset sm:px-5"
        >
          <span className="flex min-w-0 flex-col gap-0.5">
            <span className="text-title font-semibold tracking-title text-ink">{title}</span>
            <span className="text-small font-normal text-ink-3">{lede}</span>
          </span>
          <span
            aria-hidden="true"
            className={`pw-turn flex size-8 shrink-0 items-center justify-center rounded-pill bg-inset text-ink-2 ${open ? 'rotate-180' : ''}`}
          >
            <Icon name="chevron" size={15} strokeWidth={2} />
          </span>
        </button>
      </h2>
      {/* Opens by its height and closes the same way (rule 3); its content stays until it has closed. */}
      <div ref={row.ref} hidden={row.hidden} className="pw-open-row">
        <div id={`${id}-body`} hidden={row.hidden} className="flex min-w-0 flex-col gap-5 px-4 pt-1 pb-5 sm:px-5">
          {!row.hidden && children}
        </div>
      </div>
    </section>
  )
}

/** The width of an element, followed as it changes, so a chart draws in real pixels and its text stays legible. */
export function useWidth<T extends HTMLElement>(fallback = 640): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null)
  const [w, setW] = useState(fallback)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const read = () => {
      const r = el.getBoundingClientRect().width
      if (r > 0) setW(Math.round(r))
    }
    read()
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(read)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, w]
}

/** What the person sees in a saved copy instead of a tool that would call the service. */
export function SavedCopyNote({ what }: { what: string }) {
  return (
    <p className="pw-scenario rounded-md px-3 py-2 text-small leading-5 text-ink-2">
      This is a saved copy of the page, so it cannot ask the service to work out {what}. Open the live app to use it.
    </p>
  )
}
