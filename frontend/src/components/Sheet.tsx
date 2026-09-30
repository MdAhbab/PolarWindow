import { useEffect, useId, useRef, type ReactNode } from 'react'
import type React from 'react'
import { useReducedMotion } from '../hooks/useMotion'
import { Icon } from './Icon'
import { useToasts } from './Toast'

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])'

/**
 * A right-side modal sheet: a native `<dialog>` opened with `showModal()`.
 *
 * The native modal gives the three things a hand-rolled overlay gets wrong:
 * the page behind it is inert (focus cannot leave, a screen reader cannot
 * wander out), Esc closes it, and it sits in the top layer above everything.
 * Focus goes to the close button on open and back to whatever opened it on
 * close, which the browser does not do reliably on its own.
 *
 * Motion (§10.6): slides in on the move curve, and out in half the time;
 * under reduced motion it appears and goes at once, decided here in code as
 * well as by the CSS floor.
 */
export function Sheet({
  open,
  onClose,
  title,
  children,
  wide = false,
  size,
}: {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
  /** 480 px at ≥ 768 (the run log and the forms); 400 px otherwise. */
  wide?: boolean
  /** `xl`: 720 px at ≥ 768, for a sheet with its own tabs (Settings). */
  size?: 'xl'
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const opener = useRef<HTMLElement | null>(null)
  const titleId = useId()
  const reduced = useReducedMotion()
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  const reducedRef = useRef(reduced)
  reducedRef.current = reduced

  /**
   * Closing slides the sheet out (half the time it took to come in), then
   * closes the dialog; under reduced motion it closes at once. Esc, the close
   * button, a click on the backdrop and `open` turning false all come here.
   */
  const closing = useRef(false)
  const animateClose = () => {
    const d = ref.current
    if (!d || !d.open || closing.current) return
    if (reducedRef.current || typeof d.getAnimations !== 'function') {
      d.close()
      return
    }
    closing.current = true
    d.classList.remove('pw-sheet-in')
    d.classList.add('pw-sheet-out')
    const done = () => {
      if (!closing.current) return
      closing.current = false
      d.classList.remove('pw-sheet-out')
      d.close()
    }
    d.addEventListener('animationend', done, { once: true })
    // In case the animation never runs (a hidden tab), close anyway.
    window.setTimeout(done, 400)
  }

  // While open, toasts are drawn inside this sheet: the page behind is inert.
  useEffect(() => {
    const d = ref.current
    if (!open || !d) return
    useToasts.getState().addHost(d)
    return () => useToasts.getState().removeHost(d)
  }, [open])

  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) {
      closing.current = false
      d.classList.remove('pw-sheet-out')
      if (!reducedRef.current) d.classList.add('pw-sheet-in')
      opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
      d.showModal()
      closeRef.current?.focus()
    } else if (!open && d.open) {
      animateClose()
    }
    // animateClose reads refs only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  useEffect(() => {
    const d = ref.current
    if (!d) return
    // Fires for Esc, for the close button and for `close()` above alike.
    const onClosed = () => {
      onCloseRef.current()
      const o = opener.current
      opener.current = null
      if (o && document.contains(o)) o.focus()
    }
    // Esc: slide out first, then close.
    const onCancel = (e: Event) => {
      e.preventDefault()
      animateClose()
    }
    d.addEventListener('close', onClosed)
    d.addEventListener('cancel', onCancel)
    return () => {
      d.removeEventListener('close', onClosed)
      d.removeEventListener('cancel', onCancel)
    }
  }, [])

  // The native modal makes the page inert, but Tab can still walk out into
  // the browser's own controls; wrap it at both ends so focus stays here.
  const onKeyDown = (e: React.KeyboardEvent<HTMLDialogElement>) => {
    if (e.key !== 'Tab' || !ref.current) return
    const focusable = [...ref.current.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
      (el) => el.offsetParent !== null || el === document.activeElement,
    )
    if (!focusable.length) return
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault()
      first.focus()
    }
  }

  return (
    <dialog
      ref={ref}
      aria-modal="true"
      aria-labelledby={titleId}
      onKeyDown={onKeyDown}
      onClick={(e) => {
        // A click on the backdrop lands on the dialog element itself.
        if (e.target === ref.current) animateClose()
      }}
      className={`fixed inset-y-0 right-0 left-auto m-0 h-full max-h-none w-full max-w-none overflow-hidden border-0 border-l border-line-strong bg-raised p-0 text-ink shadow-overlay backdrop:bg-canvas/80 ${
        size === 'xl' ? 'md:w-[720px]' : wide ? 'md:w-[480px]' : 'md:w-[400px]'
      }`}
    >
      <div className="flex h-full flex-col">
        <div className="flex shrink-0 items-center gap-3 border-b border-line px-5 py-2">
          <h2 id={titleId} className="grow text-title font-semibold">
            {title}
          </h2>
          <button
            ref={closeRef}
            type="button"
            onClick={animateClose}
            aria-label={`Close: ${title}`}
            className="inline-flex size-12 items-center justify-center rounded-control border border-line-strong text-ink hover:bg-inset"
          >
            <Icon name="close" size={18} strokeWidth={1.8} />
          </button>
        </div>
        <div className="grow overflow-y-auto">{children}</div>
      </div>
    </dialog>
  )
}
