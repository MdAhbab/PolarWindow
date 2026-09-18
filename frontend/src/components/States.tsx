import type { ReactNode } from 'react'
import { Icon } from './Icon'
import { Button, Panel, SectionLabel } from './ui'

/**
 * No state is allowed to be a shrug. Each one says what it knows, what it does
 * not, and what the person can do next.
 */

export function EmptyState({
  title,
  detail,
  primary,
  secondary,
}: {
  title: string
  detail: ReactNode
  primary?: { label: string; onClick: () => void }
  secondary?: { label: string; onClick: () => void }
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 px-8 py-16 text-center">
      <Icon name="filter" size={44} strokeWidth={1.4} className="text-terrain-mid" />
      <div className="text-[20px] font-semibold text-ink">{title}</div>
      <div className="max-w-[460px] text-[14px] leading-6 text-ink-2">{detail}</div>
      <div className="flex flex-wrap justify-center gap-3">
        {primary && (
          <Button variant="primary" onClick={primary.onClick}>
            {primary.label}
          </Button>
        )}
        {secondary && <Button onClick={secondary.onClick}>{secondary.label}</Button>}
      </div>
    </div>
  )
}

/**
 * No spinner. The bar tracks the real ray-cast, and the partial answer is on
 * screen with a note saying which way it can still move.
 */
export function LoadingPanel({ done = 0, total = 0 }: { done?: number; total?: number }) {
  const pct = total ? Math.round((done / total) * 100) : 0
  return (
    <Panel className="flex flex-col gap-4 p-6">
      <div className="flex items-baseline justify-between">
        <SectionLabel>Ray-casting the skyline</SectionLabel>
        <span className="font-mono text-[12px] text-ink">
          {done} / {total} sites · 360 bearings each
        </span>
      </div>
      <div className="flex h-2 bg-dark-fill">
        <div className="bg-terrain-high transition-[width] duration-200" style={{ width: `${pct}%` }} />
      </div>
      <p className="text-[13px] leading-5 text-ink-2">
        Each site is ray-cast once against its elevation model, then it is 360 numbers and everything the
        date slider touches is a lookup. Totals shown before this finishes can only fall as more terrain
        is found, never rise.
      </p>
    </Panel>
  )
}

export function ErrorPanel({
  title,
  detail,
  stillWorks,
  onRetry,
}: {
  title: string
  detail: ReactNode
  stillWorks: ReactNode
  onRetry?: () => void
}) {
  return (
    <Panel className="flex flex-col gap-4 border-alert p-6">
      <div className="flex items-start gap-3">
        <Icon name="alert" size={26} strokeWidth={2} className="shrink-0 text-alert" />
        <div className="flex flex-col gap-1.5">
          <div className="text-[18px] font-semibold text-ink">{title}</div>
          <div className="text-[14px] leading-6 text-ink-2">{detail}</div>
        </div>
      </div>
      <Panel className="flex flex-col gap-1.5 p-4">
        <SectionLabel>What still works</SectionLabel>
        <div className="text-[13px] leading-5 text-ink-2">{stillWorks}</div>
      </Panel>
      {onRetry && (
        <div className="flex gap-3">
          <Button variant="primary" onClick={onRetry}>
            Retry
          </Button>
        </div>
      )}
    </Panel>
  )
}

/** The margin is never behind a tooltip. */
export function UncertaintyNote({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <Panel className={`flex flex-col gap-2.5 border-dashed border-uncertain p-5 ${className}`}>
      <div className="flex items-center gap-2 text-[12px] font-semibold tracking-[0.12em] text-ink-2 uppercase">
        <Icon name="uncertain" size={14} strokeWidth={2.2} />
        How wrong could this be
      </div>
      <div className="text-[13px] leading-5 text-ink-2">{children}</div>
      <div className="flex items-center gap-2.5">
        <span className="hatch-uncertain h-3.5 w-16 border border-line" aria-hidden="true" />
        <span className="text-[12px] text-ink-3">drawn at every arc edge, in every view</span>
      </div>
    </Panel>
  )
}
