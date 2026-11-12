import { useState, type ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Icon } from '../Icon'
import { SignInFailed, useSession } from '../../lib/session'

/**
 * Ways into the dashboard from the front page. All of them go through the same
 * one-click sign-in (no password: the button signs in as the project manager)
 * and then open a page: the one the visitor asked for (`?next=`) or Home for
 * the main button, the page that shows the idea for a card's link.
 */

/** The one name for the one intent: the main button, the island's, the close and the signed-in state all say it. */
export const ENTER_WORDS = 'Go to the dashboard'

/** The page the visitor was sent here from (`?next=`), if it is a page of this app. */
export function nextFromSearch(search: string): string {
  const n = new URLSearchParams(search).get('next')
  return n && n.startsWith('/') && !n.startsWith('//') ? n : '/home'
}

function useEnter(target?: string) {
  const session = useSession((s) => s.session)
  const signIn = useSession((s) => s.signIn)
  const navigate = useNavigate()
  const { search } = useLocation()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const next = target ?? nextFromSearch(search)
  const signedIn = Boolean(session && session.expiresAt > Date.now())

  const go = async () => {
    setError(null)
    if (signedIn) return navigate(next)
    setBusy(true)
    try {
      await signIn()
      navigate(next)
    } catch (e) {
      setError(e instanceof SignInFailed ? e.message : 'Signing in did not work. Try again in a moment.')
    } finally {
      setBusy(false)
    }
  }
  return { go, busy, error }
}

/** Signs in (one click, no password) and opens the page the visitor asked for. */
export function EnterButton({ compact = false }: { compact?: boolean }) {
  const { go, busy, error } = useEnter()
  return (
    <span className="inline-flex flex-col gap-2">
      <button
        type="button"
        onClick={() => void go()}
        disabled={busy}
        className={`pw-press group inline-flex h-12 items-center justify-center gap-2 rounded-pill bg-sun-fill font-semibold whitespace-nowrap text-on-sun hover:bg-sun-soft disabled:bg-inset disabled:text-ink-3 ${
          compact ? 'pr-1.5 pl-4 text-body' : 'pr-2 pl-6 text-control'
        }`}
      >
        {busy ? 'Signing in…' : ENTER_WORDS}
        {!busy && (
          <span className={`pw-orb ml-1 ${compact ? 'size-9' : ''}`} aria-hidden="true">
            <Icon name="arrow" size={15} strokeWidth={2} />
          </span>
        )}
      </button>
      {error && (
        <span role="alert" className="text-small text-ink">
          {error}
        </span>
      )}
    </span>
  )
}

/**
 * A card's way to the page that shows its idea: a quiet text link (a real
 * address, so it opens in a new tab too), through the same sign-in.
 */
export function EnterLink({ to, children }: { to: string; children: ReactNode }) {
  const { go, busy, error } = useEnter(to)
  return (
    <span className="inline-flex flex-col">
      <a
        href={to}
        onClick={(e) => {
          // A new tab or window keeps the browser's own behaviour: the dashboard sends it back here to sign in.
          if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return
          e.preventDefault()
          void go()
        }}
        aria-busy={busy || undefined}
        className="inline-flex min-h-11 items-center gap-1.5 text-control font-semibold text-ink underline decoration-line-strong decoration-1 underline-offset-[5px] hover:decoration-ink"
      >
        {children}
        <Icon name="arrow" size={14} strokeWidth={2} className="shrink-0" />
      </a>
      {error && (
        <span role="alert" className="text-small text-ink">
          {error}
        </span>
      )}
    </span>
  )
}
