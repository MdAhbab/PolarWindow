import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { create } from 'zustand'
import { useMotionClass } from '../hooks/useMotion'
import { Icon } from './Icon'

export interface Toast {
  id: number
  /** One sentence: what happened. */
  message: string
  /** One step the person can take next ("Undo", "Open"). */
  action?: { label: string; run: () => void }
  tone?: 'done' | 'problem'
}

interface ToastState {
  toasts: Toast[]
  show: (t: Omit<Toast, 'id'>) => number
  dismiss: (id: number) => void
  /**
   * Open sheets, innermost last. A modal sheet makes the page behind it
   * inert, so while one is open the toasts are drawn inside it.
   */
  hosts: HTMLElement[]
  addHost: (el: HTMLElement) => void
  removeHost: (el: HTMLElement) => void
}

let next = 1

export const useToasts = create<ToastState>((set) => ({
  toasts: [],
  show: (t) => {
    const id = next++
    // At most three at once; the oldest goes first.
    // The same words again replace the older toast rather than stack under it.
    set((s) => ({ toasts: [...s.toasts.filter((x) => x.message !== t.message).slice(-2), { ...t, id }] }))
    return id
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })),
  hosts: [],
  addHost: (el) => set((s) => ({ hosts: [...s.hosts.filter((h) => h !== el), el] })),
  removeHost: (el) => set((s) => ({ hosts: s.hosts.filter((h) => h !== el) })),
}))

/** Say that something was saved (or refused), from anywhere. */
export function toast(message: string, opts: Omit<Toast, 'id' | 'message'> = {}): number {
  return useToasts.getState().show({ message, ...opts })
}

/** How long a toast stays: long enough to read and reach its action (WCAG 2.2.1 allows it to be closed sooner). */
const STAY_MS = 8000

function ToastItem({ t }: { t: Toast }) {
  const dismiss = useToasts((s) => s.dismiss)
  const arrive = useMotionClass('pw-toast-in')
  useEffect(() => {
    const h = window.setTimeout(() => dismiss(t.id), t.action ? STAY_MS * 1.5 : STAY_MS)
    return () => window.clearTimeout(h)
  }, [t.id, t.action, dismiss])
  return (
    <li
      className={`pw-card pw-card-raised pointer-events-auto flex w-full items-start gap-3 py-2 pr-2 pl-4 [--pw-elev:var(--shadow-overlay)] sm:w-[380px] ${
        t.tone === 'problem' ? 'pw-card-alert' : ''
      } ${arrive}`}
    >
      <Icon
        name={t.tone === 'problem' ? 'alert' : 'check'}
        size={18}
        strokeWidth={2.2}
        className={`mt-3 shrink-0 ${t.tone === 'problem' ? 'text-alert' : 'text-ink-2'}`}
      />
      <p className="grow py-2.5 text-body leading-5 text-ink">{t.message}</p>
      {t.action && (
        <button
          type="button"
          onClick={() => {
            t.action?.run()
            dismiss(t.id)
          }}
          className="pw-press h-12 shrink-0 rounded-pill px-4 text-body font-semibold text-ink underline underline-offset-[3px] hover:bg-inset"
        >
          {t.action.label}
        </button>
      )}
      <button
        type="button"
        onClick={() => dismiss(t.id)}
        aria-label="Dismiss"
        className="pw-press inline-flex size-12 shrink-0 items-center justify-center rounded-pill text-ink-3 hover:bg-inset hover:text-ink"
      >
        <Icon name="close" size={16} strokeWidth={1.8} />
      </button>
    </li>
  )
}

/**
 * Where toasts appear: bottom right on a wide screen, across the bottom on a
 * phone, above the guide bar. The region is a polite live region, so a screen
 * reader hears each one once without losing its place.
 */
export function Toaster() {
  const toasts = useToasts((s) => s.toasts)
  const host = useToasts((s) => s.hosts[s.hosts.length - 1] ?? null)
  const region = (
    <div
      role="status"
      aria-live="polite"
      aria-label="Notifications"
      className={
        host
          ? 'pointer-events-none absolute inset-x-0 bottom-0 z-50 flex justify-center p-4'
          : 'pointer-events-none fixed inset-x-0 bottom-[calc(5rem+var(--pw-guide-h,0px))] z-50 flex justify-center px-4 sm:justify-end sm:px-6 lg:bottom-[calc(1.5rem+var(--pw-guide-h,0px))]'
      }
    >
      <ol className={`flex w-full flex-col items-end gap-2 ${host ? '' : 'sm:w-auto'}`}>
        {toasts.map((t) => (
          <ToastItem key={t.id} t={t} />
        ))}
      </ol>
    </div>
  )
  return host ? createPortal(region, host) : region
}
