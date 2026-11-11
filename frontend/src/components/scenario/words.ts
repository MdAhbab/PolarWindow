import type { AssumptionBasis, AssumptionFieldDTO, AssumptionFieldId, ScenarioSection } from '../../lib/api/experience.types'
import type { IconName } from '../Icon'
import { dateWords } from '../../lib/format'

/** The four bases, in words and shape (never colour alone). */
export const BASIS: Record<AssumptionBasis, { word: string; icon: IconName; means: string; line: 'solid' | 'dashed' | 'dotted' | 'double' }> = {
  you: { word: 'You', icon: 'pencil', means: 'Set by you, typed or said', line: 'solid' },
  published: { word: 'Published', icon: 'check', means: 'From the mission’s record', line: 'double' },
  live: { word: 'Live', icon: 'dot', means: 'Fetched for this scenario', line: 'dotted' },
  default: { word: 'Default', icon: 'ring', means: 'A named precedent or catalogue value', line: 'dashed' },
}

/** The step names as the step bar says them. */
export const STEP_NAME: Record<ScenarioSection, string> = {
  launch: 'Launch',
  trip: 'Trip',
  landing: 'Surface',
  contact: 'Contact',
  return: 'Return',
}

/** Where the step lives in the address. */
export const STEP_SLUG: Record<ScenarioSection, string> = {
  launch: 'launch',
  trip: 'trip',
  landing: 'surface',
  contact: 'contact',
  return: 'return',
}

export function stepsWords(sections: ScenarioSection[]): string {
  const names = sections.map((s) => STEP_NAME[s])
  if (names.length <= 1) return names.join('')
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
}

/** The address of a step, keeping its other parameters and setting `scenario`. */
export function withScenario(search: string, scenario: string | null, extra: Record<string, string | null> = {}): string {
  const p = new URLSearchParams(search)
  if (scenario === null) p.delete('scenario')
  else p.set('scenario', scenario)
  for (const [k, v] of Object.entries(extra)) {
    if (v === null) p.delete(k)
    else p.set(k, v)
  }
  const s = p.toString()
  return s ? `?${s}` : ''
}

/** A field's current value as the form holds it: text for a box. */
export type FieldValue = string | number | string[] | null

export function isEmptyValue(v: FieldValue | undefined): boolean {
  return v === null || v === undefined || v === '' || (Array.isArray(v) && v.length === 0)
}

/** The value in words for a field the person has just set. */
export function displayFor(f: AssumptionFieldDTO, v: FieldValue): string {
  if (isEmptyValue(v)) return 'Not set'
  switch (f.kind) {
    case 'choice':
      return f.options?.find((o) => o.value === v)?.label ?? String(v)
    case 'multi_choice': {
      const ids = v as string[]
      return ids.map((id) => f.options?.find((o) => o.value === id)?.label ?? id).join(', ')
    }
    case 'date': {
      const ms = Date.parse(`${String(v).slice(0, 10)}T00:00:00Z`)
      return Number.isNaN(ms) ? String(v) : dateWords(ms)
    }
    case 'number':
      return `${v}${f.unit ? ` ${f.unit}` : ''}`
  }
}

export const FIELD_IDS: AssumptionFieldId[] = [
  'vehicle_id',
  'pad_id',
  'site_id',
  'launch_from',
  'launch_to',
  'landing_date',
  'surface_days',
  'transfer_type',
  'sun_el_min_deg',
  'sun_el_max_deg',
  'relays',
]
