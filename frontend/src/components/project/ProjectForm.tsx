import { useState } from 'react'
import type { ProjectOptionsDTO } from '../../lib/api/experience.types'
import { STATUS_LABEL } from '../../lib/missions'
import { Disclosure } from '../ui'
import { ProvTag } from '../surface/parts'
import { CheckGroup, DateRow, Group, NotesField, SelectField, TextField, TWO_COLUMNS } from './fields'
import { PayloadRows } from './PayloadRows'
import { SitePick } from './SitePick'
import type { Errors, ProjectFormState, Provenance } from './formModel'

const STATUSES = ['planned', 'in_transit', 'operating', 'completed'] as const

const TRANSFERS = [
  { value: 'direct', label: 'Direct' },
  { value: 'phasing_loops', label: 'Phasing loops' },
  { value: 'low_energy', label: 'Low energy' },
  { value: 'unknown', label: 'Not decided' },
] as const

const RETURNS = [
  { value: 'none', label: 'Nothing returns' },
  { value: 'sample_capsule', label: 'A sample capsule' },
  { value: 'crew', label: 'A crew' },
] as const

const withHint = (o: { value: string; label: string; hint?: string | null }) => ({
  value: o.value,
  label: o.hint ? `${o.label} · ${o.hint}` : o.label,
})

const RADIO_KEYS = ['eirp', 'eirpTol', 'gt', 'frequency', 'dataRates', 'ebn0', 'margin'] as const

/** The whole form, grouped as the journey. Only the name is needed. */
export function ProjectForm({
  form,
  options,
  errors,
  provenance,
  onChange,
}: {
  form: ProjectFormState
  options: ProjectOptionsDTO | undefined
  errors: Errors
  provenance: Provenance
  onChange: (patch: Partial<ProjectFormState>) => void
}) {
  const p = provenance
  // The radio figures stay closed until there is something in them or wrong in them; once open, they stay as the person leaves them.
  const radioWanted = RADIO_KEYS.some((k) => form[k].trim() !== '' || errors[k])
  const [radioSeen, setRadioSeen] = useState(false)
  if (radioWanted && !radioSeen) setRadioSeen(true)
  const rsrc = (k: (typeof RADIO_KEYS)[number]) => (form[k].trim() ? p.radio : undefined)
  return (
    <div className="flex flex-col gap-5">
      <Group title="Mission" intro="Who is flying what.">
        <div className={TWO_COLUMNS}>
          <TextField label="Mission name" required value={form.name} onChange={(v) => onChange({ name: v })} error={errors.name} source={p.name} className="sm:col-span-2" />
          <TextField label="Provider" value={form.provider} onChange={(v) => onChange({ provider: v })} list={options?.providers} source={p.provider} hint="The company flying it." />
          <TextField label="Lander" value={form.lander} onChange={(v) => onChange({ lander: v })} list={options?.landers} source={p.lander} hint="The lander’s type, such as Nova-C." />
          <TextField label="Spacecraft name" value={form.vehicleName} onChange={(v) => onChange({ vehicleName: v })} source={p.vehicleName} hint="Its own name, such as Athena." />
          <TextField label="Task order" value={form.taskOrder} onChange={(v) => onChange({ taskOrder: v })} source={p.taskOrder} />
          <SelectField
            label="Status"
            value={form.status}
            onChange={(v) => onChange({ status: (v || 'planned') as ProjectFormState['status'] })}
            options={STATUSES.map((s) => ({ value: s, label: STATUS_LABEL[s] }))}
            source={p.status}
          />
        </div>
      </Group>

      <Group
        title="Landing spot"
        intro="Choose a site that has already been surveyed, or type where it will land."
      >
        <SitePick form={form} options={options} errors={errors} provenance={p} onChange={onChange} />
      </Group>

      <Group title="Dates" intro="Give only the dates that are known. An empty date stays unknown.">
        <div className={TWO_COLUMNS}>
          <DateRow label="Launch" value={form.launch} onChange={(v) => onChange({ launch: v })} error={errors.launch} source={p.launch} />
          <DateRow label="Landing" value={form.landing} onChange={(v) => onChange({ landing: v })} error={errors.landing} source={p.landing} />
          <DateRow label="End of mission" value={form.endOfMission} onChange={(v) => onChange({ endOfMission: v })} error={errors.endOfMission} source={p.endOfMission} />
          <TextField
            label="Planned days on the surface"
            value={form.plannedDays}
            onChange={(v) => onChange({ plannedDays: v })}
            error={errors.plannedDays}
            source={p.plannedDays}
            inputMode="decimal"
            hint="A number above zero."
          />
        </div>
      </Group>

      <Group title="Launch" intro="From the catalogues. A choice you do not make stays unknown, and the Launch step offers a scenario.">
        <div className={TWO_COLUMNS}>
          <SelectField label="Launch vehicle" value={form.vehicleId} onChange={(v) => onChange({ vehicleId: v })} options={(options?.vehicles ?? []).map(withHint)} source={p.vehicleId} />
          <SelectField label="Launch pad" value={form.padId} onChange={(v) => onChange({ padId: v })} options={(options?.pads ?? []).map(withHint)} source={p.padId} />
        </div>
      </Group>

      <Group title="Spacecraft and radio" intro="What it weighs, how it travels and how it will talk to Earth.">
        <div className={TWO_COLUMNS}>
          <SelectField label="Transfer to the Moon" value={form.transfer} onChange={(v) => onChange({ transfer: v })} options={[...TRANSFERS]} source={p.transfer} />
          <SelectField label="What comes back" value={form.returns} onChange={(v) => onChange({ returns: v })} options={[...RETURNS]} source={p.returns} />
          <TextField label="Radio bands" value={form.bands} onChange={(v) => onChange({ bands: v })} source={p.bands} hint="Separate them with commas, such as S, X." />
          <TextField label="Mass, kg" value={form.mass} onChange={(v) => onChange({ mass: v })} error={errors.mass} source={p.mass} inputMode="decimal" hint="A number above zero." />
        </div>
        {(options?.relays.length ?? 0) > 0 && (
          <CheckGroup legend="Relays it may use" options={options!.relays} value={form.relays} onChange={(v) => onChange({ relays: v })} source={p.relays} />
        )}
        <Disclosure title="Radio figures" meta="optional" defaultOpen={radioSeen}>
          <div className={TWO_COLUMNS}>
            <TextField label="Radio power (EIRP, dBW)" value={form.eirp} onChange={(v) => onChange({ eirp: v })} error={errors.eirp} source={rsrc('eirp')} inputMode="decimal" hint="Optional. From −20 to 100." />
            <TextField label="Margin on radio power (EIRP ±, dB)" value={form.eirpTol} onChange={(v) => onChange({ eirpTol: v })} error={errors.eirpTol} source={rsrc('eirpTol')} inputMode="decimal" hint="Optional. From 0 to 30." />
            <TextField label="Ground dish sensitivity (G/T, dB/K)" value={form.gt} onChange={(v) => onChange({ gt: v })} error={errors.gt} source={rsrc('gt')} inputMode="decimal" hint="Optional. From −60 to 80." />
            <TextField label="Radio frequency, lander to Earth (downlink, MHz)" value={form.frequency} onChange={(v) => onChange({ frequency: v })} error={errors.frequency} source={rsrc('frequency')} inputMode="decimal" hint="Optional. Above 0, up to 300000." />
            <TextField label="Data rates (kbps, comma-separated)" value={form.dataRates} onChange={(v) => onChange({ dataRates: v })} error={errors.dataRates} source={rsrc('dataRates')} hint="Optional. Up to 20 rates, each above 0." className="sm:col-span-2" />
            <TextField label="Signal needed per bit (Eb/N0, dB)" value={form.ebn0} onChange={(v) => onChange({ ebn0: v })} error={errors.ebn0} source={rsrc('ebn0')} inputMode="decimal" hint="Optional. From −10 to 40." />
            <TextField label="Spare signal kept in hand (link margin, dB)" value={form.margin} onChange={(v) => onChange({ margin: v })} error={errors.margin} source={rsrc('margin')} inputMode="decimal" hint="Optional. From 0 to 30." />
          </div>
          <p className="max-w-2xl text-small leading-5 text-ink-2">
            Contact can work out the radio link once it has three of these. They are radio power (EIRP), an X-band frequency (8200 to 8600 MHz) and the signal per bit (Eb/N0). Without all three, Contact does not work out the radio link and names what is missing. Figures you type here are shown as <ProvTag p="entered" />.
          </p>
        </Disclosure>
      </Group>

      <Group title="Payloads" intro="What it carries. Add one row for each.">
        <PayloadRows rows={form.payloads} onChange={(v) => onChange({ payloads: v })} instrumentTypes={options?.instrument_types} errors={errors} provenance={p} />
      </Group>

      <Group title="Notes">
        <NotesField label="Notes" value={form.notes} onChange={(v) => onChange({ notes: v })} source={p.notes} hint="One note a line. They are kept with the mission." />
      </Group>
    </div>
  )
}
