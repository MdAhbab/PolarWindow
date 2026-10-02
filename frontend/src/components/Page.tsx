import type { ReactNode } from 'react'
import { useTransitionClick } from '../lib/viewTransition'
import { Link } from 'react-router-dom'

export interface Crumb {
  label: string
  /** Absent on the page itself, the last crumb. */
  to?: string
}

/**
 * Where this page sits, and the way back: every page below the top views has
 * one. The last crumb is the page itself and is not a link.
 */
export function Breadcrumbs({ items }: { items: Crumb[] }) {
  const go = useTransitionClick()
  return (
    <nav aria-label="Breadcrumb" className="min-w-0">
      <ol className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5 text-small text-ink-3">
        {items.map((c, i) => {
          const last = i === items.length - 1
          return (
            <li key={`${c.label}-${i}`} className="flex min-w-0 items-center gap-1.5">
              {c.to && !last ? (
                <Link
                  to={c.to}
                  onClick={go(c.to)}
                  className="-mx-1 inline-flex min-h-8 items-center rounded-control px-1 font-medium text-ink-2 underline decoration-line-strong underline-offset-[3px] hover:text-ink hover:decoration-current"
                >
                  {c.label}
                </Link>
              ) : (
                <span aria-current={last ? 'page' : undefined} className={last ? 'truncate text-ink-2' : ''}>
                  {c.label}
                </span>
              )}
              {!last && (
                <span aria-hidden="true" className="text-line-strong">
                  /
                </span>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

/**
 * The top of every page: the way back, the page's name, one line on what it
 * answers, and at most a couple of actions. The same shape everywhere, so a
 * reader learns it once.
 */
export function PageHeader({
  crumbs,
  title,
  titleExtra,
  lede,
  actions,
  children,
  compact = false,
}: {
  crumbs?: Crumb[]
  /** A step back in size, for a page whose hero is below the header (a step's answer). */
  compact?: boolean
  title: ReactNode
  /** Quieter words after the title on the same line ("· Athena"). */
  titleExtra?: ReactNode
  lede?: ReactNode
  actions?: ReactNode
  children?: ReactNode
}) {
  return (
    <header className="flex flex-col gap-3">
      {crumbs && crumbs.length > 0 && <Breadcrumbs items={crumbs} />}
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="flex min-w-0 flex-col gap-2">
          {/* Display scale, unless the page's hero is under it: then one step back, so the answer leads. */}
          <h1
            className={`pw-display text-ink ${
              compact
                ? 'text-[26px] leading-[30px] sm:text-[30px] sm:leading-[34px]'
                : 'text-[32px] leading-[34px] sm:text-[44px] sm:leading-[46px] lg:text-[52px] lg:leading-[54px]'
            }`}
          >
            {title}
            {titleExtra && <span className="font-normal tracking-heading text-ink-2 [font-stretch:100%]"> {titleExtra}</span>}
          </h1>
          {lede && <p className={`max-w-3xl text-ink-2 ${compact ? 'text-body leading-6' : 'text-lede leading-7'}`}>{lede}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children}
    </header>
  )
}
