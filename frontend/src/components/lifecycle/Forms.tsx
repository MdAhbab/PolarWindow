import { useId, useState, type ReactNode } from 'react'
import type React from 'react'
import { hasOwnName, useSession, SignInFailed } from '../../lib/session'
import { ApiError } from '../../lib/api/client'
import type { AuditEntryDTO } from '../../lib/api/lifecycle'
import { dateTimeWords } from '../../lib/format'
import { Sheet } from '../Sheet'
import { toast } from '../Toast'
import { Button, SectionLabel } from '../ui'

/**
 * The project manager's forms (design-lifecycle.md §5): each is small, sits
 * in a sheet beside what it changes, has visible labels and 48 px controls,
 * and one primary button. What the server refuses is shown as it said it.
 */

const INPUT =
  'h-12 w-full min-w-0 rounded-control border border-field bg-panel px-3.5 text-body text-ink outline-none placeholder:text-ink-3 focus:border-focus'

export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string
  hint?: string
  error?: string
  children: (props: { id: string; 'aria-describedby'?: string; 'aria-invalid'?: boolean }) => ReactNode
}) {
  const id = useId()
  const hintId = hint ? `${id}-hint` : undefined
  const errId = error ? `${id}-err` : undefined
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-small font-semibold text-ink">
        {label}
      </label>
      {children({ id, 'aria-describedby': [hintId, errId].filter(Boolean).join(' ') || undefined, 'aria-invalid': error ? true : undefined })}
      {hint && (
        <p id={hintId} className="text-caption leading-caption text-ink-3">
          {hint}
        </p>
      )}
      {error && (
        <p id={errId} className="text-caption leading-caption font-semibold text-alert">
          {error}
        </p>
      )}
    </div>
  )
}

export function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input type="text" {...props} className={`${INPUT} ${props.className ?? ''}`} />
}

export function TextArea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea rows={3} {...props} className={`${INPUT} h-auto min-h-24 py-2.5 leading-5`} />
}

/** One of a list: the page's own list, in a field's box (components/Select). */
export { Select } from '../Select'

/**
 * ADR-17: every change carries a person's name. The demo session has only
 * the demo name, so the first form a visitor opens asks for theirs, and
 * saving signs in again with it before the change is sent.
 */
export function useNamedWriter() {
  const session = useSession((s) => s.session)
  const signIn = useSession((s) => s.signIn)
  const [name, setName] = useState('')
  const [team, setTeam] = useState('')
  const [error, setError] = useState<string | undefined>()
  const offline = !session || session.offline
  const needsName = !offline && !hasOwnName(session)

  const fields = offline ? (
    <p className="text-small leading-5 text-ink-2">
      This copy runs from saved answers, so entering records needs the live service.
    </p>
  ) : needsName ? (
    <fieldset className="flex flex-col gap-3 border-l-2 border-line-strong pl-3">
      <legend className="mb-2 text-small leading-5 text-ink-2">Every change is recorded with your name.</legend>
      <Field label="Your name" error={error}>
        {(p) => <TextInput {...p} autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />}
      </Field>
      <Field label="Team (optional)">
        {(p) => <TextInput {...p} autoComplete="organization" value={team} onChange={(e) => setTeam(e.target.value)} />}
      </Field>
    </fieldset>
  ) : (
    <p className="text-small leading-5 text-ink-2">
      Recorded as <span className="font-semibold text-ink">{session?.user?.name}</span>
      {session?.user?.team ? `, ${session.user.team}` : ''}.
    </p>
  )

  /** Signs in by name when needed; false (with the reason shown) when it cannot. */
  const ensure = async (): Promise<boolean> => {
    if (offline) return false
    if (!needsName) return true
    if (!name.trim()) {
      setError('Enter your name, so the change is recorded against it.')
      return false
    }
    try {
      await signIn({ name: name.trim(), team: team.trim() || null })
      setError(undefined)
      return true
    } catch (e) {
      setError(e instanceof SignInFailed ? e.message : 'Signing in with that name did not work.')
      return false
    }
  }
  return { fields, ensure, offline }
}

/** A write's refusal, in the server's own words; a 409 lists what is allowed. */
export function WriteProblem({ error }: { error: unknown }) {
  if (!error) return null
  const e = error as Partial<ApiError> & { message?: string }
  return (
    <div role="alert" className="flex flex-col gap-1 border-l-[3px] border-alert pl-3">
      <p className="text-small font-semibold text-ink">{e.title ?? 'The change was not saved'}</p>
      <p className="text-caption leading-caption text-ink-2">{e.detail ?? e.message}</p>
      {e.stillWorks && <p className="text-caption leading-caption text-ink-3">{e.stillWorks}</p>}
    </div>
  )
}

/**
 * A form in a sheet: the fields, the name when needed, one Save, and the
 * change history under it. `onSave` returns when the server has the change.
 */
export function FormSheet({
  open,
  onClose,
  title,
  intro,
  children,
  onSave,
  saving,
  error,
  history,
  saveLabel = 'Save',
  savingLabel = 'Saving…',
}: {
  open: boolean
  onClose: () => void
  title: string
  intro?: ReactNode
  children: ReactNode
  onSave: () => Promise<boolean | void>
  saving: boolean
  error?: unknown
  history?: ReactNode
  saveLabel?: string
  savingLabel?: string
}) {
  const writer = useNamedWriter()
  return (
    <Sheet open={open} onClose={onClose} title={title} wide>
      {/* Our own messages, beside the field they are about, instead of the browser's bubble. */}
      <form
        noValidate
        className="flex flex-col gap-5 p-5"
        onSubmit={async (e) => {
          e.preventDefault()
          if (!(await writer.ensure())) return
          const ok = await onSave()
          // Said in a toast, drawn inside this sheet while it is open.
          if (ok !== false) toast('Saved.')
        }}
      >
        {intro && <div className="text-small leading-5 text-ink-2">{intro}</div>}
        {writer.fields}
        {children}
        <WriteProblem error={error} />
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" variant="primary" disabled={saving || writer.offline}>
            {saving ? savingLabel : saveLabel}
          </Button>
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>

        </div>
      </form>
      {history && <div className="flex flex-col gap-3 border-t border-line p-5">{history}</div>}
    </Sheet>
  )
}

/** A record's change history, newest first: who, when, from what to what. */
export function HistoryList({
  entries,
  pending,
  error,
  describe,
}: {
  entries: AuditEntryDTO[] | undefined
  pending: boolean
  error: unknown
  describe?: (e: AuditEntryDTO) => string
}) {
  return (
    <>
      <SectionLabel as="h3">Change history</SectionLabel>
      {pending ? (
        <p className="text-small text-ink-3">Loading the history…</p>
      ) : error ? (
        <p className="text-small text-ink-2">
          {error instanceof ApiError && error.status === 404
            ? 'This server does not keep a history for this record yet.'
            : `The history could not be loaded: ${(error as ApiError).title ?? String(error)}`}
        </p>
      ) : !entries?.length ? (
        <p className="text-small text-ink-2">No changes recorded yet.</p>
      ) : (
        <ol className="flex flex-col divide-y divide-line border-y border-line">
          {entries.map((e, i) => (
            <li key={`${e.at}-${i}`} className="flex flex-col gap-0.5 py-2.5">
              <span className="text-small font-semibold text-ink">{describe ? describe(e) : changeWords(e)}</span>
              <span className="text-caption leading-caption text-ink-3">
                {e.by} · {dateTimeWords(Date.parse(e.at))}
              </span>
              {e.note && <span className="text-small leading-5 text-ink-2">{e.note}</span>}
            </li>
          ))}
        </ol>
      )}
    </>
  )
}

/** "state: in test → blocked" for each field that changed. */
export function changeWords(e: AuditEntryDTO): string {
  const before = (e.before ?? {}) as Record<string, unknown>
  const after = (e.after ?? {}) as Record<string, unknown>
  const keys = [...new Set([...Object.keys(before), ...Object.keys(after)])].filter(
    (k) => JSON.stringify(before[k]) !== JSON.stringify(after[k]),
  )
  if (!keys.length) return e.action ? e.action.charAt(0).toUpperCase() + e.action.slice(1).replace(/_/g, ' ') : e.before === null ? 'Created' : 'Changed'
  const show = (v: unknown) => (v === null || v === undefined ? 'none' : String(v).replace(/_/g, ' '))
  return keys.map((k) => `${k.replace(/_/g, ' ')}: ${show(before[k])} → ${show(after[k])}`).join('; ')
}

/** Today in UTC as YYYY-MM-DD, the value a date field starts at. */
export function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

/** A URL a person typed, checked the way the server will. */
export function isHttpUrl(s: string): boolean {
  try {
    const u = new URL(s)
    return u.protocol === 'https:' || u.protocol === 'http:'
  } catch {
    return false
  }
}
