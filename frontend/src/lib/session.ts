import { create } from 'zustand'
import { DATA_MODE } from './api/snapshot'

/**
 * The dashboard's session: the project manager's token, from one button on the
 * landing page. No user name, no password: this is a judged demo, and the
 * server can turn the button off (`PW_DEMO_SIGN_IN=false`).
 *
 * The server is the authority. The token is only read here for what the
 * screen shows (the role and when the session ends); every call that needs it
 * is checked by the API. Map data is public and needs no token.
 *
 * An offline session has no token: a static copy has no server to sign in to,
 * and a live copy whose server is down answers from the saved copy. It reads
 * everything that was saved; the project settings say they need the service.
 *
 * Stored in `localStorage` under `pw-session`, always inside try/catch: a
 * private window or blocked site data means signing in again next visit.
 */
export interface Session {
  /** Null for an offline session. */
  token: string | null
  roleName: string
  /** Epoch milliseconds. */
  expiresAt: number
  offline: boolean
  /**
   * Who is signed in (ADR-17). Every change they enter carries this name.
   * Absent on a session from before named sign-in, and offline.
   */
  user?: { id: number; name: string; team: string | null }
}

/** The name the one-click sign-in gives when none is asked for (lifecycle-api.md). */
export const DEMO_NAME = 'Demo project manager'

/** A session whose changes would be recorded under a real person's name. */
export function hasOwnName(s: Session | null): boolean {
  return Boolean(s && !s.offline && s.user && s.user.name !== DEMO_NAME)
}

export const SESSION_KEY = 'pw-session'

const OFFLINE_HOURS = 12

function parse(raw: string | null): Session | null {
  if (!raw) return null
  try {
    const v = JSON.parse(raw) as Partial<Session>
    if (typeof v.expiresAt !== 'number' || typeof v.roleName !== 'string') return null
    if (v.token !== null && typeof v.token !== 'string') return null
    const u = v.user
    const user =
      u && typeof u.name === 'string' && typeof u.id === 'number'
        ? { id: u.id, name: u.name, team: typeof u.team === 'string' ? u.team : null }
        : undefined
    return { token: v.token ?? null, roleName: v.roleName, expiresAt: v.expiresAt, offline: Boolean(v.offline), user }
  } catch {
    return null
  }
}

function read(): Session | null {
  try {
    const s = parse(typeof localStorage === 'undefined' ? null : localStorage.getItem(SESSION_KEY))
    return s && s.expiresAt > Date.now() ? s : null
  } catch {
    return null
  }
}

function write(s: Session | null): void {
  try {
    if (s) localStorage.setItem(SESSION_KEY, JSON.stringify(s))
    else localStorage.removeItem(SESSION_KEY)
  } catch {
    /* storage refused: the session lasts for this page only */
  }
}

function offlineSession(): Session {
  return {
    token: null,
    roleName: 'Project manager',
    expiresAt: Date.now() + OFFLINE_HOURS * 3_600_000,
    offline: true,
  }
}

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? 'http://localhost:8000/api/v1'

/** Why signing in failed, in words the landing page can show as they are. */
export class SignInFailed extends Error {}

/** Who is signing in; nothing asked for gives the demo name. */
export interface SignInAs {
  name: string
  team?: string | null
}

async function requestSession(as?: SignInAs): Promise<Session> {
  if (DATA_MODE === 'snapshot') return offlineSession()
  let res: Response
  try {
    res = await fetch(`${API_BASE}/auth/demo`, {
      method: 'POST',
      ...(as
        ? {
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify({ name: as.name, ...(as.team ? { team: as.team } : {}) }),
          }
        : {}),
    })
  } catch {
    // Asked to sign in by name and nothing answered: saying so beats an
    // offline session that could not record the name anyway.
    if (as) throw new SignInFailed('Nothing answered, so the name could not be recorded. Try again when the service is running.')
    // No server answered: open the saved copy rather than a locked door.
    return offlineSession()
  }
  if (!res.ok) {
    let title = 'Signing in did not work'
    try {
      const body = (await res.json()) as { detail?: { title?: string; detail?: string } }
      title = body.detail?.detail ?? body.detail?.title ?? title
    } catch {
      /* the default says enough */
    }
    throw new SignInFailed(title)
  }
  const body = (await res.json()) as {
    token: string
    role_name: string
    expires_at: string
    user?: { id: number; name: string; team: string | null }
  }
  return {
    token: body.token,
    roleName: body.role_name,
    expiresAt: Date.parse(body.expires_at),
    offline: false,
    user: body.user ? { id: body.user.id, name: body.user.name, team: body.user.team ?? null } : undefined,
  }
}

interface SessionState {
  session: Session | null
  /** Without a name, the one-click demo session; with one, a named session (ADR-17). */
  signIn: (as?: SignInAs) => Promise<Session>
  signOut: () => void
}

export const useSession = create<SessionState>((set) => ({
  session: read(),
  signIn: async (as) => {
    const s = await requestSession(as)
    write(s)
    set({ session: s })
    return s
  },
  signOut: () => {
    write(null)
    set({ session: null })
  },
}))

/** The token for an API call, or null (offline, signed out, or ended). */
export function currentToken(): string | null {
  const s = useSession.getState().session
  if (!s || s.expiresAt <= Date.now()) return null
  return s.token
}

let renewing: Promise<string | null> | null = null

/**
 * The server refused the token (it restarted with a new secret, or the
 * session ended): sign in again, once, for every caller waiting on it. Null
 * when that fails too, and the session is cleared so the dashboard sends the
 * visitor back to the front page.
 */
export function renewToken(): Promise<string | null> {
  const user = useSession.getState().session?.user
  const again = user && user.name !== DEMO_NAME ? { name: user.name, team: user.team } : undefined
  renewing ??= useSession
    .getState()
    .signIn(again)
    .then((s) => s.token)
    .catch(() => {
      useSession.getState().signOut()
      return null
    })
    .finally(() => {
      renewing = null
    })
  return renewing
}
