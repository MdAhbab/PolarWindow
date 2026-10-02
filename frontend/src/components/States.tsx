import { Component, useSyncExternalStore, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useMotionClass, useReducedMotion } from '../hooks/useMotion'
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
    <div className="flex flex-col items-center justify-center gap-3.5 px-6 py-16 text-center">
      <span
        className="flex size-16 items-center justify-center rounded-pill bg-inset text-ink-2 shadow-[inset_0_1px_0_var(--color-hi),0_0_0_1px_var(--color-edge),0_0_0_5px_var(--color-tray),0_0_0_6px_var(--color-line)]"
        aria-hidden="true"
      >
        <Icon name="filter" size={26} strokeWidth={1.6} />
      </span>
      <div className="pt-2 text-title-lg font-semibold tracking-title text-ink sm:text-subhead">{title}</div>
      <div className="max-w-[460px] text-body leading-6 text-ink-2">{detail}</div>
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
        <span className="font-mono text-caption text-ink">
          {done} / {total} {unit}
        </span>
      </div>
      <ProgressTrack
        label={`${unit.charAt(0).toUpperCase()}${unit.slice(1)} loaded`}
        max={total || 1}
        now={done}
        fraction={pct / 100}
      />
      <p className="text-small leading-5 text-ink-2">
        {note ??
          'Each site’s skyline was measured once, ahead of time, from the terrain map. What happens now is the quick part: tracing the Sun and Earth across the sky for these dates and checking them against that skyline. Each site appears as soon as its own answer arrives.'}
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
    <Panel alert className="flex flex-col gap-4 p-5 sm:p-6">
      <div className="flex items-start gap-3">
        <Icon name="alert" size={22} strokeWidth={2} className="mt-0.5 shrink-0 text-alert" />
        <div className="flex flex-col gap-1.5">
          <div className="text-title-lg font-semibold text-ink">{title}</div>
          <div className="text-body leading-6 text-ink-2">{detail}</div>
        </div>
      </div>
      <div className="flex flex-col gap-1 border-l-2 border-line-strong pl-3 sm:ml-[34px]">
        <SectionLabel as="div">What still works</SectionLabel>
        <div className="text-small leading-5 text-ink-2">{stillWorks}</div>
      </div>
      {(onRetry || action) && (
        <div className="flex flex-wrap gap-3 sm:ml-[34px]">
          {action && (
            <Button variant="primary" onClick={action.onClick}>
              {action.label}
            </Button>
          )}
          {onRetry && (
            <Button variant={action ? 'secondary' : 'primary'} onClick={onRetry}>
              Try again
            </Button>
          )}
        </div>
      )}
    </Panel>
  )
}

/**
 * A caveat, said once where it applies: a hairline in the uncertain ink and a
 * sentence, not a box competing with the numbers. The margin is never behind a
 * tooltip.
 */
export function UncertaintyNote({
  children,
  className = '',
  title,
  hatchKey = false,
}: {
  children: ReactNode
  className?: string
  /** A short lead-in, in bold, before the sentence. */
  title?: string
  /** The −45° hatch key, for notes about a band drawn on the chart beside them. */
  hatchKey?: boolean
}) {
  return (
    <div className={`flex gap-2.5 border-l-2 border-uncertain py-0.5 pl-3 ${className}`}>
      <Icon name="uncertain" size={14} strokeWidth={2.2} className="mt-[3px] shrink-0 text-ink-3" />
      <div className="flex flex-col gap-1.5 text-small leading-5 text-ink-2">
        <div>
          {title && (
            <>
              <span className="font-semibold text-ink">{title}</span>.{' '}
            </>
          )}
          {children}
        </div>
        {hatchKey && (
          <div className="flex items-center gap-2.5">
            <span className="hatch-uncertain h-3 w-10 border border-line" aria-hidden="true" />
            <span className="text-caption text-ink-3">hatched: how far off it could be</span>
          </div>
        )}
      </div>
    </div>
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

/**
 * A progress bar: the fill is scaled, never resized, so it moves on the
 * compositor and nothing around it shifts. With no figure yet (a job still
 * queued) a short band slides along the track instead, and stands still under
 * reduced motion.
 */
export function ProgressTrack({
  label,
  max = 100,
  now,
  fraction,
  valueText,
}: {
  label: string
  max?: number
  now?: number
  /** 0–1, or null when there is no figure yet. */
  fraction: number | null
  valueText?: string
}) {
  const reduced = useReducedMotion()
  return (
    <div
      className="relative h-1.5 overflow-hidden rounded-pill bg-line"
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={now}
      aria-valuetext={valueText}
    >
      {fraction === null ? (
        <div className={`absolute inset-y-0 left-0 w-1/4 bg-terrain-high ${reduced ? 'opacity-60' : 'pw-indeterminate'}`} />
      ) : (
        <div
          className="absolute inset-0 origin-left bg-terrain-high transition-transform duration-[var(--pw-dur-slow)] ease-[var(--ease-settle)]"
          style={{ transform: `scaleX(${Math.max(0, Math.min(1, fraction))})` }}
        />
      )}
    </div>
  )
}

/**
 * A grey block standing in for content that is on its way, the size of what
 * will replace it, so nothing moves when the content arrives. It breathes
 * (opacity only) unless motion is reduced.
 */
export function Skeleton({ className = '' }: { className?: string }) {
  const pulse = useMotionClass('pw-skeleton')
  return <div aria-hidden="true" className={`bg-inset ${pulse} ${className}`} />
}

/**
 * The shape of a section while its answer loads: the answer's lines, four
 * tiles and a chart, at their final sizes.
 */
export function SectionSkeleton({ tiles = 4, chart = true }: { tiles?: number; chart?: boolean }) {
  return (
    <div className="flex flex-col gap-6" aria-hidden="true">
      <div className="flex flex-col gap-2">
        <Skeleton className="h-7 w-full max-w-3xl" />
        <Skeleton className="h-7 w-2/3 max-w-xl" />
        <Skeleton className="mt-1 h-4 w-32" />
      </div>
      {tiles > 0 && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {Array.from({ length: tiles }, (_, i) => (
            <Skeleton key={i} className="h-[136px]" />
          ))}
        </div>
      )}
      {chart && <Skeleton className="h-64" />}
    </div>
  )
}

/**
 * Said once, under the header, whenever the numbers on screen are not live:
 * the browser is offline, or the app is answering from its saved copy. Each
 * says what it means for the numbers and what the person can do.
 */
export function ConnectionBanner({
  offline,
  saved,
  savedOn,
  badge,
}: {
  /** The browser says it has no network. */
  offline: boolean
  /** The app is answering from the saved copy. */
  saved: boolean
  /** When the saved copy was taken, in words. */
  savedOn?: string
  /** The data-source badge, which names the state for assistive technology. */
  badge?: ReactNode
}) {
  if (!offline && !saved && !badge) return null
  return (
    // One quiet note under the island, in the page's flow: it scrolls away.
    <div className="pw-page flex justify-center pt-3">
    <div className="flex w-fit max-w-full flex-wrap items-center justify-center gap-x-3 gap-y-1.5 rounded-[22px] border border-line bg-tray py-1.5 pr-4 pl-1.5 text-center text-caption leading-caption text-ink-2 sm:text-left sm:text-small sm:leading-5">
      {offline && (
        <span className="flex items-center gap-2 pl-2.5">
          <Icon name="offline" size={16} strokeWidth={1.8} className="shrink-0 text-ink" />
          <span>
            <span className="font-semibold text-ink">You are offline.</span> Pages already opened still work; new ones
            come from the saved copy where it has them.
          </span>
        </span>
      )}
      {!offline && badge}
      {!offline && saved && (
        <span>
          The live service is not answering: these are its answers{savedOn ? ` saved ${savedOn}` : ''}. Pages not saved
          say so.
        </span>
      )}
    </div>
    </div>
  )
}

/** Whether the browser has a network, kept up to date. */
export function useOnline(): boolean {
  return useSyncExternalStore(
    (l) => {
      window.addEventListener('online', l)
      window.addEventListener('offline', l)
      return () => {
        window.removeEventListener('online', l)
        window.removeEventListener('offline', l)
      }
    },
    () => navigator.onLine,
    () => true,
  )
}

/** An address that is not a page: say so, and offer the two ways on. */
export function NotFound({ what = 'page' }: { what?: string }) {
  return (
    <div className="pw-page mx-auto flex w-full max-w-2xl flex-col gap-5 py-16">
      <p className="pw-eyebrow">Not found · 404</p>
      <h1 className="pw-display text-[32px] leading-[36px] text-ink sm:text-[44px] sm:leading-[48px]">There is no {what} at this address</h1>
      <p className="text-body leading-6 text-ink-2">
        The link may be old, or the address mistyped. Nothing else is affected: every mission and every landing site is
        where it was.
      </p>
      <div className="flex flex-wrap gap-3">
        <Link
          to="/missions"
          className="pw-press group inline-flex h-12 items-center gap-2 rounded-pill bg-ink pr-2 pl-5 text-control font-semibold text-canvas no-underline hover:bg-ink-2"
        >
          Go to the missions
          <span className="pw-orb ml-1" aria-hidden="true">
            <Icon name="arrow" size={15} strokeWidth={2} />
          </span>
        </Link>
        <Link
          to="/map"
          className="pw-press inline-flex h-12 items-center gap-2 rounded-pill border border-line-strong bg-tray px-5 text-control font-semibold text-ink no-underline hover:border-ink-3 hover:bg-inset"
        >
          Go to the landing sites
        </Link>
      </div>
    </div>
  )
}

/**
 * A screen that throws is replaced by this, not by a blank page: what
 * happened, that nothing was changed, and a way back. The header and
 * navigation around it keep working. `resetKey` (the address) clears it when
 * the person moves on.
 */
export class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string }, { error: Error | null }> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidUpdate(prev: { resetKey?: string }) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null })
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="pw-page mx-auto w-full max-w-2xl py-10">
        <ErrorPanel
          title="This page stopped working"
          detail={
            <>
              Something on it failed while drawing: <span className="font-mono text-small">{this.state.error.message}</span>
            </>
          }
          stillWorks="Nothing was saved or changed. The other pages, and this one after a reload, work as usual."
          onRetry={() => this.setState({ error: null })}
          action={{ label: 'Reload the page', onClick: () => window.location.reload() }}
        />
      </div>
    )
  }
}
