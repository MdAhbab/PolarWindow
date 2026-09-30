import { useEffect } from 'react'
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
}

let next = 1

export const useToasts = create<ToastState>((set) => ({
  toasts: [],
  show: (t) => {
    const id = next++
    // At most three at once; the oldest goes first.
    set((s) => ({ toasts: [...s.toasts.slice(-2), { ...t, id }] }))
    return id
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })),
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
      className={`pointer-events-auto flex w-full items-start gap-3 border bg-raised py-2 pr-2 pl-4 shadow-overlay sm:w-[380px] ${
        t.tone === 'problem' ? 'border-alert' : 'border-line-strong'
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
          className="h-12 shrink-0 rounded-control px-3 text-body font-semibold text-ink underline underline-offset-[3px] hover:bg-inset"
        >
          {t.action.label}
        </button>
      )}
      <button
        type="button"
        onClick={() => dismiss(t.id)}
        aria-label="Dismiss"
        className="inline-flex size-12 shrink-0 items-center justify-center rounded-control text-ink-3 hover:bg-inset hover:text-ink"
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
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="Notifications"
      className="pointer-events-none fixed inset-x-0 bottom-[calc(1rem+var(--pw-guide-h,0px))] z-50 flex justify-center px-4 sm:justify-end sm:px-6"
    >
      <ol className="flex w-full flex-col items-end gap-2 sm:w-auto">
        {toasts.map((t) => (
          <ToastItem key={t.id} t={t} />
        ))}
      </ol>
    </div>
  )
}
