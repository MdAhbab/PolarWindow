import { useId, useState, type ReactNode } from 'react'
import type React from 'react'
import { TextArea, TextInput } from '../lifecycle/Forms'
import { Icon } from '../Icon'
import { Select } from '../Select'
import type { DateField, GroupKey, Provenance } from './formModel'

/**
 * The form's field parts. Every control has a visible label; a hint and an
 * error are tied to it with aria-describedby; and a value that came from a
 * file carries a small mark whose evidence opens on hover, on focus and on a
 * press, and is read as part of the field.
 */

export { TextArea, TextInput }

type Source = Provenance[GroupKey]

/** What the reader said about one value, opened in place under the field. */
function SourceMark({ source, panelId }: { source: NonNullable<Source>; panelId: string }) {
  const [pinned, setPinned] = useState(false)
  const [hover, setHover] = useState(false)
  const [focus, setFocus] = useState(false)
  const open = pinned || hover || focus
  const { field, filename } = source
  const worked = field.confidence === 'inferred'
  const where = field.page !== null ? `page ${field.page}` : null
  return (
    <span className="contents" onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setPinned((p) => !p)}
        onFocus={() => setFocus(true)}
        onBlur={() => setFocus(false)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') {
            setPinned(false)
            setHover(false)
            setFocus(false)
          }
        }}
        className="pw-press inline-flex min-h-11 items-center gap-1.5 rounded-pill border border-line-strong bg-inset px-2.5 text-caption font-semibold text-ink-2 hover:text-ink sm:min-h-8"
      >
        <Icon name={worked ? 'info' : 'check'} size={13} strokeWidth={2.2} />
        {worked ? 'Worked out' : 'From the file'}
      </button>
      <span
        id={panelId}
        role="group"
        aria-label={worked ? 'How this was worked out' : 'Where the file says this'}
        hidden={!open}
        className="basis-full rounded-control border border-line bg-inset px-3 py-2 text-caption leading-caption text-ink-2"
      >
        {worked ? (
          <>
            <span className="font-semibold text-ink">Worked out from what the file says.</span>{' '}
            {field.note ?? 'The reader gave no note.'}
            {field.evidence && (
              <>
                {' '}
                It read: <q className="text-ink">{field.evidence}</q>
              </>
            )}
          </>
        ) : field.evidence ? (
          <>
            <q className="text-ink">{field.evidence}</q>
          </>
        ) : (
          <>The file states it; no wording was kept.</>
        )}
        <span className="mt-1 block text-ink-3">
          {filename}
          {where ? `, ${where}` : ''}
        </span>
      </span>
    </span>
  )
}

export function FieldShell({
  label,
  hint,
  error,
  source,
  required,
  children,
  className = '',
}: {
  label: string
  hint?: string
  error?: string
  source?: Source
  required?: boolean
  className?: string
  children: (props: { id: string; 'aria-describedby'?: string; 'aria-invalid'?: boolean }) => ReactNode
}) {
  const id = useId()
  const hintId = hint ? `${id}-hint` : undefined
  const errId = error ? `${id}-err` : undefined
  const srcId = `${id}-src`
  return (
    <div className={`flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1.5 ${className}`}>
      <label htmlFor={id} className="text-small font-semibold text-ink">
        {label}
        {required && <span className="font-normal text-ink-3"> (required)</span>}
      </label>
      {source && <SourceMark source={source} panelId={srcId} />}
      <div className="basis-full">
        {children({
          id,
          'aria-describedby': [hintId, errId].filter(Boolean).join(' ') || undefined,
          'aria-invalid': error ? true : undefined,
        })}
      </div>
      {hint && (
        <p id={hintId} className="basis-full text-caption leading-caption text-ink-3">
          {hint}
        </p>
      )}
      {error && (
        <p id={errId} className="basis-full text-caption leading-caption font-semibold text-alert">
          <span aria-hidden="true">▲ </span>
          {error}
        </p>
      )}
    </div>
  )
}

/** A text field; with `list`, the browser offers the catalogue's names and still takes any other. */
export function TextField({
  label,
  value,
  onChange,
  hint,
  error,
  source,
  required,
  list,
  placeholder,
  inputMode,
  className,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  hint?: string
  error?: string
  source?: Source
  required?: boolean
  list?: string[]
  placeholder?: string
  inputMode?: 'decimal' | 'text'
  className?: string
}) {
  const listId = useId()
  return (
    <FieldShell label={label} hint={hint} error={error} source={source} required={required} className={className}>
      {(p) => (
        <>
          <TextInput
            {...p}
            value={value}
            list={list ? listId : undefined}
            placeholder={placeholder}
            inputMode={inputMode}
            autoComplete="off"
            onChange={(e) => onChange(e.target.value)}
          />
          {list && (
            <datalist id={listId}>
              {list.map((o) => (
                <option key={o} value={o} />
              ))}
            </datalist>
          )}
        </>
      )}
    </FieldShell>
  )
}

export function SelectField<T extends string>({
  label,
  value,
  onChange,
  options,
  hint,
  error,
  source,
  unknown = 'Not known',
}: {
  label: string
  value: T | ''
  onChange: (v: T | '') => void
  options: { value: T; label: string }[]
  hint?: string
  error?: string
  source?: Source
  unknown?: string
}) {
  return (
    <FieldShell label={label} hint={hint} error={error} source={source}>
      {(p) => (
        <Select<string>
          {...p}
          value={value}
          placeholder={unknown}
          onChange={(v) => onChange(v as T | '')}
          options={[{ value: '', label: unknown }, ...options]}
        />
      )}
    </FieldShell>
  )
}

export function NotesField(props: {
  label: string
  value: string
  onChange: (v: string) => void
  hint?: string
  source?: Source
}) {
  return (
    <FieldShell label={props.label} hint={props.hint} source={props.source}>
      {(p) => <TextArea {...p} rows={4} value={props.value} onChange={(e) => props.onChange(e.target.value)} />}
    </FieldShell>
  )
}

const PRECISIONS: { value: DateField['precision']; label: string }[] = [
  { value: 'day', label: 'Exact day' },
  { value: 'month', label: 'Month' },
  { value: 'quarter', label: 'Quarter' },
  { value: 'year', label: 'Year' },
]

/** A date and how exactly it is known. A month, quarter or year is entered as its first day. */
export function DateRow({
  label,
  value,
  onChange,
  error,
  source,
}: {
  label: string
  value: DateField
  onChange: (v: DateField) => void
  error?: string
  source?: Source
}) {
  const pid = useId()
  const hint =
    value.precision === 'day'
      ? 'Leave empty if it is not known.'
      : `Enter the first day of the ${value.precision}. It is kept as a ${value.precision}, not a day.`
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <FieldShell label={label} hint={hint} error={error} source={source}>
        {(p) => (
          <TextInput
            {...p}
            type="date"
            value={value.date}
            onChange={(e) => onChange({ ...value, date: e.target.value })}
          />
        )}
      </FieldShell>
      <div className="flex flex-col gap-1">
        <span id={pid} className="text-caption text-ink-3">
          How exactly is the {label.toLowerCase()} known?
        </span>
        <div
          role="group"
          aria-labelledby={pid}
          className="inline-flex w-fit max-w-full overflow-x-auto rounded-pill border border-line-strong bg-tray"
        >
          {PRECISIONS.map((o) => {
            const on = value.precision === o.value
            return (
              <button
                key={o.value}
                type="button"
                aria-pressed={on}
                onClick={() => onChange({ ...value, precision: o.value })}
                className={`pw-press h-[44px] shrink-0 rounded-pill border-4 border-transparent bg-clip-padding px-3 text-small font-semibold whitespace-nowrap ${
                  on ? 'bg-ink text-canvas' : 'text-ink-2 hover:text-ink'
                }`}
              >
                {o.label}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}

/** Several of a list: real checkboxes in a labelled group. */
export function CheckGroup({
  legend,
  options,
  value,
  onChange,
  source,
}: {
  legend: string
  options: { value: string; label: string; hint?: string | null }[]
  value: string[]
  onChange: (v: string[]) => void
  source?: Source
}) {
  const srcId = useId()
  return (
    <fieldset className="flex min-w-0 flex-col gap-2">
      <legend className="flex flex-wrap items-center gap-x-2 gap-y-1.5 text-small font-semibold text-ink">
        {legend}
        {source && <SourceMark source={source} panelId={srcId} />}
      </legend>
      <div className="flex flex-wrap gap-2">
        {options.map((o) => {
          const on = value.includes(o.value)
          return (
            <label
              key={o.value}
              className={`pw-press inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-pill border px-3.5 text-small font-semibold has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-focus ${
                on ? 'border-ink bg-inset text-ink' : 'border-line-strong bg-tray text-ink-2 hover:text-ink'
              }`}
              title={o.hint ?? undefined}
            >
              <input
                type="checkbox"
                className="sr-only"
                checked={on}
                onChange={() => onChange(on ? value.filter((v) => v !== o.value) : [...value, o.value])}
              />
              {on && <Icon name="check" size={14} strokeWidth={2.6} />}
              {o.label}
            </label>
          )
        })}
      </div>
    </fieldset>
  )
}

/** A group of fields under one heading, with a line of what it is for. */
export function Group({
  title,
  intro,
  children,
  source,
}: {
  title: string
  intro?: ReactNode
  children: ReactNode
  source?: Source
}) {
  const id = useId()
  return (
    <section aria-labelledby={id} className="pw-card flex flex-col gap-5 p-5 sm:p-6">
      <div className="flex flex-col gap-1.5">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <h2 id={id} className="text-title-lg font-semibold tracking-title text-ink">
            {title}
          </h2>
          {source && <SourceMark source={source} panelId={`${id}-src`} />}
        </div>
        {intro && <p className="max-w-2xl text-small leading-5 text-ink-2">{intro}</p>}
      </div>
      {children}
    </section>
  )
}

export const TWO_COLUMNS = 'grid gap-x-5 gap-y-5 sm:grid-cols-2'

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>
