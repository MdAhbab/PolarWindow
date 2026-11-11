import { useRef, useState } from 'react'
import type { IntakeDTO, ProjectOptionsDTO } from '../../lib/api/experience.types'
import { Button } from '../ui'
import { Icon } from '../Icon'
import { ProgressTrack } from '../States'
import { intakeCounts } from './formModel'

export type ReadStage = 'sending' | 'reading' | 'filling'

const mb = (bytes: number) => (bytes / 1_048_576 >= 1 ? `${Math.round(bytes / 1_048_576)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`)

/** Why a file cannot be sent, in words; null when it can. Mirrors the service's stated limits. */
export function fileProblem(file: File, options: ProjectOptionsDTO | undefined): string | null {
  const ext = file.name.includes('.') ? file.name.split('.').pop()!.toLowerCase() : ''
  const accepted = options?.accepted_extensions
  if (accepted && !accepted.includes(ext)) {
    return `${file.name} is not a kind of file the reader takes. It takes ${accepted.map((a) => a.toUpperCase()).join(', ')}.`
  }
  if (options && file.size > options.max_upload_bytes) {
    return `${file.name} is ${mb(file.size)}, over the ${mb(options.max_upload_bytes)} the reader takes.`
  }
  if (file.size === 0) return `${file.name} is empty.`
  return null
}

/** Drop a file, or press the button. Several files may be given; they are read one after another. */
export function FileDrop({
  options,
  busy,
  onFiles,
  heldCount,
}: {
  options: ProjectOptionsDTO | undefined
  busy: boolean
  onFiles: (files: File[]) => void
  heldCount: number
}) {
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const kinds = options?.accepted_extensions.map((e) => e.toUpperCase()).join(', ')
  const take = (list: FileList | null) => {
    if (list && list.length) onFiles([...list])
  }
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        if (!busy) setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setOver(false)
        if (!busy) take(e.dataTransfer.files)
      }}
      className={`flex flex-col items-center gap-3 rounded-card border-2 border-dashed px-5 py-8 text-center transition-colors duration-[var(--pw-dur-quick)] ${
        over ? 'border-focus bg-inset' : 'border-line-strong bg-tray'
      }`}
    >
      <span className="flex size-12 items-center justify-center rounded-pill bg-inset text-ink-2" aria-hidden="true">
        <Icon name="export" size={22} strokeWidth={1.6} className="-rotate-90" />
      </span>
      <p className="text-control font-semibold text-ink">Drop a mission file here</p>
      <p className="max-w-md text-small leading-5 text-ink-2">
        A project brief, a press kit or a table of dates.{' '}
        {kinds ? `${kinds}, up to ${mb(options!.max_upload_bytes)}.` : 'The kinds it takes are loading.'} Drop more than one and
        they fill the same form; a later file only fills what is still empty.
      </p>
      <input
        ref={input}
        type="file"
        multiple
        tabIndex={-1}
        aria-hidden="true"
        className="sr-only"
        accept={options?.accepted_extensions.map((e) => `.${e}`).join(',')}
        onChange={(e) => {
          take(e.target.files)
          e.target.value = ''
        }}
      />
      <Button variant="primary" disabled={busy} onClick={() => input.current?.click()}>
        {busy ? 'Reading a file…' : 'Choose a file'}
      </Button>
      {heldCount > 0 && (
        <p className="text-caption text-ink-3">
          {heldCount} file{heldCount === 1 ? '' : 's'} waiting for your name.
        </p>
      )}
    </div>
  )
}

const STAGES: { id: ReadStage; label: string }[] = [
  { id: 'sending', label: 'Sending the file' },
  { id: 'reading', label: 'Reading the file and finding the mission facts' },
  { id: 'filling', label: 'Filling the form' },
]

/** What the reader is doing, in the order it does it. The percentage is only the upload's. */
export function ReadingProgress({ filename, stage, fraction }: { filename: string; stage: ReadStage; fraction: number | null }) {
  const at = STAGES.findIndex((s) => s.id === stage)
  return (
    <div role="status" aria-live="polite" className="flex flex-col gap-3 rounded-card border border-line bg-tray p-5">
      <p className="text-control font-semibold text-ink">
        <span className="sr-only">Working on </span>
        {filename}
      </p>
      <ol className="flex flex-col gap-1.5">
        {STAGES.map((s, i) => (
          <li
            key={s.id}
            aria-current={i === at ? 'step' : undefined}
            className={`flex items-center gap-2.5 text-small ${i === at ? 'font-semibold text-ink' : i < at ? 'text-ink-2' : 'text-ink-3'}`}
          >
            <span aria-hidden="true" className="flex size-5 items-center justify-center">
              {i < at ? <Icon name="check" size={14} strokeWidth={2.6} /> : <Icon name={i === at ? 'dot' : 'ring'} size={14} />}
            </span>
            {s.label}
            {i < at && <span className="sr-only"> (done)</span>}
            {i === at && s.id === 'sending' && fraction !== null && <span className="tnum text-ink-2">{Math.round(fraction * 100)}%</span>}
          </li>
        ))}
      </ol>
      <ProgressTrack
        label={`Reading ${filename}`}
        fraction={stage === 'sending' ? fraction : stage === 'filling' ? 1 : null}
        now={stage === 'sending' && fraction !== null ? Math.round(fraction * 100) : undefined}
      />
      <p className="text-caption text-ink-3">Nothing is saved until you press Save.</p>
    </div>
  )
}

/** What the reading found: how, how much, and anything it was unsure of. */
export function IntakeSummary({ readings }: { readings: IntakeDTO[] }) {
  if (readings.length === 0) return null
  return (
    <div className="flex flex-col gap-3" aria-live="polite">
      {readings.map((r) => {
        const { found, lookedFor } = intakeCounts(r)
        return (
          <section
            key={r.intake_id}
            aria-label={`Reading of ${r.filename}`}
            className="flex flex-col gap-2 rounded-card border border-line bg-tray p-4 sm:p-5"
          >
            <p className="text-control font-semibold text-ink">
              {r.filename}: {found} of {lookedFor} fields filled
            </p>
            <p className="text-small leading-5 text-ink-2">
              {r.method === 'model' ? (
                <>
                  Read by an AI model{r.model ? ` (${r.model})` : ''}. Every date and number it gave was checked against the
                  file’s own text. Check each value before you save.
                </>
              ) : (
                <>
                  No AI model is set up, so this file was read by rules: only dates, names and coordinates were looked
                  for. Everything else is left for you to fill in.
                </>
              )}
            </p>
            {r.warnings.length > 0 && (
              <ul className="flex flex-col gap-1 border-l-[3px] border-uncertain pl-3 text-small leading-5 text-ink-2">
                {r.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            )}
          </section>
        )
      })}
    </div>
  )
}
