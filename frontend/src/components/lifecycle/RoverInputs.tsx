import { useState } from 'react'
import type { RoverOptions } from '../../lib/api/client'
import type { RoverSightDTO } from '../../lib/api/lifecycle'
import { formatValue } from '../../lib/lifecycle/quantity'
import {
  EMPTY_DRAFT,
  ROVER_FIELDS,
  anyGiven,
  draftOf,
  limitWords,
  readDraft,
  type Draft,
  type RoverField,
  type RoverFieldSpec,
} from '../../lib/lifecycle/roverInputs'
import { Button } from '../ui'
import { Field, TextInput } from './Forms'

/** The value the answer on screen used for a box, with its unit; null when the answer does not say. */
function inUse(a: RoverSightDTO, f: RoverFieldSpec): number | null {
  const v = f.key === 'radius_m' ? a.radius_m : f.key === 'freq_mhz' ? a.assumptions?.radio_mhz.value : a.assumptions?.[f.key]?.value
  return v === undefined || v === null ? null : v
}

/**
 * How far out, the two antenna heights and the radio frequency the line of sight is worked out
 * for (design-lifecycle.md §4). A box left empty keeps the service's assumption, which the
 * answer names as assumed; a box filled in is asked for as given. Nothing is worked out by
 * typing: the button asks, and the map and numbers come back for those values.
 */
export function RoverInputs({ answer, given, onApply }: { answer: RoverSightDTO; given: RoverOptions; onApply: (o: RoverOptions) => void }) {
  const [draft, setDraft] = useState<Draft>(() => draftOf(given))
  const [errors, setErrors] = useState<Partial<Record<RoverField, string>>>({})
  const read = readDraft(draft)
  // Anything typed that differs from what is in force: even a slip can be sent, to be told what is wrong.
  const started = draftOf(given)
  const changed = ROVER_FIELDS.some((f) => draft[f.key].trim() !== started[f.key])
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    setErrors(read.errors)
    if (!Object.keys(read.errors).length) onApply(read.options)
  }
  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-3 border-t border-line pt-4" data-testid="rover-inputs">
      <p className="text-body font-semibold text-ink">Try other values</p>
      <p className="text-small text-ink-2">
        Leave a box empty to keep the assumed value. The map and the numbers are worked out again for the values you give.
      </p>
      {ROVER_FIELDS.map((f) => {
        const now = inUse(answer, f)
        const mine = given[f.key] !== undefined
        return (
          <Field
            key={f.key}
            label={`${f.label}, ${f.unit.words}`}
            hint={`${limitWords(f)}${now === null ? '' : ` In use: ${formatValue(now)} ${f.unit.short}, ${mine ? 'as you gave it' : 'assumed'}.`}`}
            error={errors[f.key]}
          >
            {(p) => (
              <TextInput
                {...p}
                inputMode="decimal"
                autoComplete="off"
                placeholder={mine || now === null ? undefined : formatValue(now)}
                value={draft[f.key]}
                onChange={(e) => {
                  setDraft({ ...draft, [f.key]: e.target.value })
                  if (errors[f.key]) setErrors({ ...errors, [f.key]: undefined })
                }}
              />
            )}
          </Field>
        )
      })}
      <div className="flex flex-wrap gap-3">
        <Button variant="primary" type="submit" disabled={!changed}>
          Work it out with these
        </Button>
        {anyGiven(given) && (
          <Button
            onClick={() => {
              setDraft(EMPTY_DRAFT)
              setErrors({})
              onApply({})
            }}
          >
            Back to the assumed values
          </Button>
        )}
      </div>
    </form>
  )
}
