import type React from 'react'
import { flushSync } from 'react-dom'
import { useNavigate, type NavigateOptions, type To } from 'react-router-dom'
import { useReducedMotion } from '../hooks/useMotion'

/**
 * Page and step changes through the View Transitions API.
 *
 * React Router's own `viewTransition` works only with a data router, and this
 * app uses `<BrowserRouter>`, so a link asks for the transition itself: the
 * browser keeps a picture of the old page, the route changes synchronously
 * inside the transition, and the CSS in globals.css cross-fades the content
 * (`.pw-content`) and slides the step bar's mark. Under reduced motion, in a
 * browser without the API, or for a click that opens a new tab, the link does
 * what a link does.
 */
export function useTransitionClick() {
  const navigate = useNavigate()
  const reduced = useReducedMotion()
  return (to: To, opts?: NavigateOptions) => (e: React.MouseEvent<HTMLAnchorElement>) => {
    const start = (document as Document & { startViewTransition?: (cb: () => void) => unknown }).startViewTransition
    if (reduced || !start || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
    e.preventDefault()
    start.call(document, () => {
      flushSync(() => navigate(to, opts))
    })
  }
}
