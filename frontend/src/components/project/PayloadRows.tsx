import type { OptionDTO } from '../../lib/api/experience.types'
import { Button } from '../ui'
import { Icon } from '../Icon'
import { INSTRUMENT_LABEL } from '../../lib/missions'
import { CheckGroup, FieldShell, TextArea, TextField, TWO_COLUMNS } from './fields'
import { newPayload, type Errors, type PayloadRow, type Provenance } from './formModel'

/** What it carries: one row a payload, added and removed one at a time. */
export function PayloadRows({
  rows,
  onChange,
  instrumentTypes,
  errors,
  provenance,
}: {
  rows: PayloadRow[]
  onChange: (rows: PayloadRow[]) => void
  instrumentTypes: OptionDTO[] | undefined
  errors: Errors
  provenance: Provenance
}) {
  const types =
    instrumentTypes ??
    Object.entries(INSTRUMENT_LABEL).map(([value, label]) => ({ value, label }) as OptionDTO)
  const set = (i: number, patch: Partial<PayloadRow>) => onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  const src = provenance.payloads
  return (
    <div className="flex flex-col gap-4">
      {rows.length === 0 && (
        <p className="text-small leading-5 text-ink-2">
          No payloads yet. Leave this empty if they are not known; the mission then shows “payloads unconfirmed”.
        </p>
      )}
      <ol className="flex flex-col gap-4">
        {rows.map((r, i) => (
          <li key={r.key} className="flex flex-col gap-4 rounded-control border border-line bg-tray p-4">
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-control font-semibold text-ink">Payload {i + 1}</h3>
              <Button size="sm" variant="ghost" onClick={() => onChange(rows.filter((_, j) => j !== i))}>
                <Icon name="close" size={14} strokeWidth={2} />
                Remove<span className="sr-only"> payload {i + 1}</span>
              </Button>
            </div>
            <div className={TWO_COLUMNS}>
              <TextField
                label={`Name of payload ${i + 1}`}
                value={r.name}
                onChange={(v) => set(i, { name: v })}
                error={errors[`payload-${i}`]}
                source={i === 0 ? src : undefined}
              />
              <TextField label={`Short name of payload ${i + 1}`} value={r.acronym} onChange={(v) => set(i, { acronym: v })} hint="An acronym, if it has one." />
              <TextField label={`Organisation behind payload ${i + 1}`} value={r.organisation} onChange={(v) => set(i, { organisation: v })} className="sm:col-span-2" />
            </div>
            <CheckGroup
              legend={`What payload ${i + 1} is`}
              options={types.map((t) => ({ value: t.value, label: t.label, hint: t.hint }))}
              value={r.types}
              onChange={(v) => set(i, { types: v })}
            />
            <FieldShell label={`Purpose of payload ${i + 1}`} hint="One or two sentences, in your words.">
              {(p) => <TextArea {...p} rows={2} value={r.purpose} onChange={(e) => set(i, { purpose: e.target.value })} />}
            </FieldShell>
          </li>
        ))}
      </ol>
      <div>
        <Button onClick={() => onChange([...rows, newPayload()])}>
          <Icon name="plus" size={16} strokeWidth={2} />
          Add a payload
        </Button>
      </div>
    </div>
  )
}
