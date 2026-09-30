import { useEffect, useLayoutEffect, useRef } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { GUIDE_STEPS, isOnStepPage, useGuide } from '../lib/guide'
import { useReducedMotion } from '../hooks/useMotion'
import { Button } from './ui'
import { Icon } from './Icon'

/**
 * The guide: a bar along the bottom that introduces each major feature once.
 *
 * Not a dialog: the page stays usable while it is open, so a step can be
 * tried as it is read. "Next" and "Back" move between steps and take the
 * visitor to the page each one is about; the element it describes is outlined
 * and scrolled into view. Closing it leaves a "Guide" button in the header.
 *
 * Its height is published as `--pw-guide-h` so the page can leave room for it
 * and the Listen caption can sit above it.
 */
export function GuideBar() {
  const { open, step, setOpen, go } = useGuide()
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const reduced = useReducedMotion()
  const barRef = useRef<HTMLDivElement>(null)
  const current = GUIDE_STEPS[step]
  const here = isOnStepPage(current, pathname)
  const last = step === GUIDE_STEPS.length - 1

  // Leave room for the bar at the foot of the page.
  useLayoutEffect(() => {
    const root = document.documentElement
    const el = barRef.current
    if (!open || !el) {
      root.style.removeProperty('--pw-guide-h')
      return
    }
    const set = () => root.style.setProperty('--pw-guide-h', `${el.offsetHeight}px`)
    set()
    const ro = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(set)
    ro?.observe(el)
    return () => {
      ro?.disconnect()
      root.style.removeProperty('--pw-guide-h')
    }
  }, [open])

  // Outline the element this step is about, once it has rendered.
  useEffect(() => {
    if (!open || !here) return
    let found: Element | null = null
    let tries = 0
    const mark = () => {
      found = document.querySelector(`[data-guide="${current.target}"]`)
      if (found) {
        found.setAttribute('data-guide-active', '')
        found.scrollIntoView({ block: 'nearest', behavior: reduced ? 'auto' : 'smooth' })
        return true
      }
      return false
    }
    if (mark()) return () => found?.removeAttribute('data-guide-active')
    // The page may still be loading its data: look again for a few seconds.
    const timer = window.setInterval(() => {
      tries += 1
      if (mark() || tries > 40) window.clearInterval(timer)
    }, 150)
    return () => {
      window.clearInterval(timer)
      found?.removeAttribute('data-guide-active')
    }
  }, [open, here, current.target, reduced])

  if (!open) return null

  const goTo = (i: number) => {
    go(i)
    const next = GUIDE_STEPS[i]
    if (!isOnStepPage(next, pathname)) navigate(next.path)
  }

  const finish = () => {
    go(0)
    setOpen(false)
  }

  return (
    <div
      ref={barRef}
      role="region"
      aria-label="Guide"
      onKeyDown={(e) => {
        if (e.key === 'Escape') setOpen(false)
      }}
      className="fixed inset-x-0 bottom-[calc(4rem+env(safe-area-inset-bottom))] z-40 border-t border-line-strong bg-raised shadow-page lg:bottom-0"
    >
      <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-3 lg:flex-row lg:items-center lg:gap-6 lg:px-6">
        <div className="flex min-w-0 grow flex-col gap-1.5">
          <div className="flex items-center gap-3">
            <span className="shrink-0 text-caption font-semibold text-ink-3">
              Guide · {step + 1} of {GUIDE_STEPS.length}
            </span>
            <span className="flex grow gap-1" aria-hidden="true">
              {GUIDE_STEPS.map((s, k) => (
                <span key={s.id} className={`h-1 grow ${k <= step ? 'bg-ink-2' : 'bg-line-strong'}`} />
              ))}
            </span>
          </div>
          {/* Announced when the step changes. */}
          <div aria-live="polite" className="flex flex-col gap-0.5">
            <p className="text-control font-semibold text-ink">{current.title}</p>
            <p className="text-small leading-5 text-ink-2">{current.body}</p>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {!here && (
            <Button size="sm" onClick={() => navigate(current.path)}>
              Take me there
            </Button>
          )}
          <Button size="sm" variant="ghost" disabled={step === 0} onClick={() => goTo(step - 1)}>
            Back
          </Button>
          {last ? (
            <Button size="sm" variant="primary" onClick={finish}>
              Finish
            </Button>
          ) : (
            <Button size="sm" variant="primary" onClick={() => goTo(step + 1)}>
              Next
            </Button>
          )}
          {!last && (
            <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
              Skip the tour
            </Button>
          )}
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Close the guide"
            title="Close the guide. Reopen it from Guide at the top of the page."
            className="inline-flex size-12 items-center justify-center rounded-control text-ink-2 hover:bg-inset hover:text-ink"
          >
            <Icon name="close" />
          </button>
        </div>
      </div>
    </div>
  )
}
