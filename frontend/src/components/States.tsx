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
 * No spinner. The bar tracks sites as their answers arrive.
 *
 * The copy used to say the browser was ray-casting 360 bearings. That was the
 * old in-browser engine; skylines are now built once, offline, at a finer
 * resolution, and what the bar tracks is each site's Sun and Earth track being
 * worked out against its stored skyline.
 */
export function LoadingPanel({
  done = 0,
  total = 0,
  title = 'Working out sunlight and Earth contact',
  unit = 'sites',
  note,
}: {
  done?: number
  total?: number
  title?: string
  unit?: string
  note?: ReactNode
}) {
  const pct = total ? Math.round((done / total) * 100) : 0
  return (
    <Panel className="flex flex-col gap-4 p-6">
      <div className="flex items-baseline justify-between gap-3">
        <SectionLabel>{title}</SectionLabel>
        <span className="font-mono text-[12px] text-ink">
          {done} / {total} {unit}
        </span>
      </div>
      <div
        className="flex h-2 bg-dark-fill"
        role="progressbar"
        aria-label={`${unit.charAt(0).toUpperCase()}${unit.slice(1)} loaded`}
        aria-valuemin={0}
        aria-valuemax={total || 1}
        aria-valuenow={done}
      >
        <div className="bg-terrain-high transition-[width] duration-200" style={{ width: `${pct}%` }} />
      </div>
      <p className="text-[13px] leading-5 text-ink-2">
        {note ??
          'Each site’s skyline was ray-cast once, ahead of time, against its elevation model. What is happening now is the fast part: the Sun’s and Earth’s paths for this window, checked against that skyline. Each site appears as soon as its own answer arrives.'}
      </p>
    </Panel>
  )
}

export function ErrorPanel({
  title,
  detail,
  stillWorks,
  onRetry,
  action,
}: {
  title: string
  detail: ReactNode
  stillWorks: ReactNode
  onRetry?: () => void
  /** The server's own next step (`ui.action`), when it names one. */
  action?: { label: string; onClick: () => void }
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
      {(onRetry || action) && (
        <div className="flex flex-wrap gap-3">
          {action && (
            <Button variant="primary" onClick={action.onClick}>
              {action.label}
            </Button>
          )}
          {onRetry && (
            <Button variant={action ? 'secondary' : 'primary'} onClick={onRetry}>
              Retry
            </Button>
          )}
        </div>
      )}
    </Panel>
  )
}

/** The margin is never behind a tooltip. */
export function UncertaintyNote({
  children,
  className = '',
  title = 'How wrong could this be',
  hatchKey = true,
}: {
  children: ReactNode
  className?: string
  /** The note's heading; the default speaks about the geometry's margins. */
  title?: string
  /** The −45° hatch key, for notes about values drawn on a chart. */
  hatchKey?: boolean
}) {
  return (
    <Panel className={`flex flex-col gap-2.5 border-dashed border-uncertain p-5 ${className}`}>
      <div className="flex items-center gap-2 text-[12px] font-semibold tracking-[0.12em] text-ink-2 uppercase">
        <Icon name="uncertain" size={14} strokeWidth={2.2} />
        {title}
      </div>
      <div className="text-[13px] leading-5 text-ink-2">{children}</div>
      {hatchKey && (
        <div className="flex items-center gap-2.5">
          <span className="hatch-uncertain h-3.5 w-16 border border-line" aria-hidden="true" />
          <span className="text-[12px] text-ink-3">drawn at every arc edge, in every view</span>
        </div>
      )}
    </Panel>
  )
}

/**
 * `ErrorPanel` fed directly from a problem detail (§5): the server writes the
 * title, the detail and what still works, so the copy can be improved without
 * a frontend deploy. `fallback` is used only when the error is not an API
 * problem at all.
 */
export function ProblemPanel({
  error,
  fallbackTitle = 'Something failed',
  onRetry,
  action,
}: {
  error: unknown
  fallbackTitle?: string
  onRetry?: () => void
  action?: { label: string; onClick: () => void }
}) {
  const e = error as Partial<{ title: string; detail: string; stillWorks: string; retryable: boolean }>
  const isProblem = typeof e?.title === 'string'
  return (
    <ErrorPanel
      title={isProblem ? (e.title as string) : fallbackTitle}
      detail={isProblem ? (e.detail ?? '') : String((error as Error)?.message ?? error)}
      stillWorks={e?.stillWorks ?? 'Everything already on screen is unaffected.'}
      onRetry={onRetry && (isProblem ? e.retryable !== false : true) ? onRetry : undefined}
      action={action}
    />
  )
}
