import type React from 'react'
import { useNavigate, type NavigateOptions, type To } from 'react-router-dom'
import { useReducedMotion } from '../hooks/useMotion'

/**
 * Page and step changes through the View Transitions API.
 *
 * React Router's own `viewTransition` works only with a data router, and this
 * app uses `<BrowserRouter>`, so a link asks for the transition itself: the
 * browser keeps a picture of the old page, the route changes inside the
 * transition, and the CSS in globals.css cross-fades the content
 * (`.pw-content`) and slides the step bar's mark. Under reduced motion, in a
 * browser without the API, or for a click that opens a new tab, the link does
 * what a link does.
 *
 * React Router 7's `<BrowserRouter>` applies a new location inside a React
 * transition, which `flushSync` does not hurry: the browser used to take the
 * old page for the new one, and the real change, landing mid-animation, made
 * it drop the whole transition. So the change now waits for the shell to say
 * the new location is drawn (`routeDrawn`, from AppShell's layout effect), for
 * at most `ROUTE_MS`; until then the old picture simply stays.
 *
 * `carry` (rule 5 of the motion grammar) names, for this one change, the
 * element in the link marked `data-pw-carry` (else the page's element marked
 * `data-pw-carry` with that name, else the link itself), so it moves into the
 * element of the same name on the new page: a mission's name into its header,
 * a site's name into its title. Only the pressed link carries it, so the name
 * is never on two elements of one page. The new page is caught when the place
 * the name goes to (`data-pw-arrive`) is on it: at once when it is, or after
 * its record arrives, for at most `WAIT_MS` (then the name simply goes with
 * the old page, as content does).
 */
const WAIT_MS = 400
const ROUTE_MS = 1000

let drawnWaiters: (() => void)[] = []

/** The shell calls this as each new location is drawn (a layout effect). */
export function routeDrawn(): void {
  const w = drawnWaiters
  drawnWaiters = []
  w.forEach((f) => f())
}

/** Resolves when the next location is drawn, or after `ms`. */
function nextRouteDrawn(ms: number): Promise<void> {
  return new Promise((resolve) => {
    const done = () => {
      window.clearTimeout(t)
      drawnWaiters = drawnWaiters.filter((f) => f !== done)
      resolve()
    }
    const t = window.setTimeout(done, ms)
    drawnWaiters.push(done)
  })
}

/** Resolves once an element marked `data-pw-arrive={name}` is in the page, or after `ms`. */
function arrival(name: string, ms: number): Promise<void> | undefined {
  const sel = `[data-pw-arrive="${name}"]`
  if (document.querySelector(sel)) return undefined
  return new Promise((resolve) => {
    const done = () => {
      mo.disconnect()
      window.clearTimeout(t)
      resolve()
    }
    const mo = new MutationObserver(() => {
      if (document.querySelector(sel)) done()
    })
    mo.observe(document.body, { childList: true, subtree: true })
    const t = window.setTimeout(done, ms)
  })
}

export function useTransitionClick() {
  const navigate = useNavigate()
  const reduced = useReducedMotion()
  return (to: To, opts?: NavigateOptions, carry?: string) => (e: React.MouseEvent<HTMLAnchorElement>) => {
    const start = (
      document as Document & { startViewTransition?: (cb: () => void | Promise<void>) => { finished?: Promise<unknown> } }
    ).startViewTransition
    if (reduced || !start || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
    e.preventDefault()
    const link = e.currentTarget
    const named = carry
      ? (link.querySelector<HTMLElement>('[data-pw-carry]') ??
        document.querySelector<HTMLElement>(`[data-pw-carry="${carry}"]`) ??
        link)
      : null
    if (named && carry) named.style.viewTransitionName = carry
    const t = start.call(document, async () => {
      const drawn = nextRouteDrawn(ROUTE_MS)
      navigate(to, opts)
      await drawn
      if (carry) await arrival(carry, WAIT_MS)
    })
    if (named) void t?.finished?.finally(() => named.style.removeProperty('view-transition-name'))
  }
}
