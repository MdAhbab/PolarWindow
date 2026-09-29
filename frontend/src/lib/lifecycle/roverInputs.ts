/**
 * What can be asked of the rover's line of sight besides the rover: how far out from the lander,
 * the two antenna heights and the radio frequency. A box left empty is not sent, so the service
 * assumes that value and says so; the limits below are the service's own (docs/lifecycle-api.md,
 * `GET /missions/{id}/contact/rover`), checked here so a slip is met with a sentence at the box
 * rather than a refusal.
 */
import type { RoverOptions } from '../api/client'
import { formatValue } from './quantity'

export type RoverField = keyof RoverOptions

export interface RoverFieldSpec {
  key: RoverField
  /** What the box asks for, in words. */
  label: string
  /** The unit, in words for the label and as written for the limits. */
  unit: { words: string; short: string }
  min: number
  max: number
}

export const ROVER_FIELDS: readonly RoverFieldSpec[] = [
  { key: 'radius_m', label: 'How far from the lander', unit: { words: 'metres', short: 'm' }, min: 50, max: 5000 },
  { key: 'lander_antenna_m', label: 'Lander’s antenna above the ground', unit: { words: 'metres', short: 'm' }, min: 0, max: 50 },
  { key: 'rover_antenna_m', label: 'Rover’s antenna above the ground', unit: { words: 'metres', short: 'm' }, min: 0, max: 50 },
  { key: 'freq_mhz', label: 'Radio frequency', unit: { words: 'MHz', short: 'MHz' }, min: 30, max: 100_000 },
]

/** What is typed in each box. */
export type Draft = Record<RoverField, string>

export const EMPTY_DRAFT: Draft = { radius_m: '', lander_antenna_m: '', rover_antenna_m: '', freq_mhz: '' }

/** The boxes as they stand when these values are in force. */
export function draftOf(given: RoverOptions): Draft {
  const d = { ...EMPTY_DRAFT }
  for (const f of ROVER_FIELDS) if (given[f.key] !== undefined) d[f.key] = String(given[f.key])
  return d
}

/** The limits of a box in words: "Between 50 and 5,000 m." */
export const limitWords = (f: RoverFieldSpec) => `Between ${formatValue(f.min)} and ${formatValue(f.max)} ${f.unit.short}.`

/**
 * The boxes read as what to ask for (the empty ones left out) or, for each box that cannot be
 * used, the sentence that says why. A number is written as people write it: "2,400", "0.5".
 */
export function readDraft(d: Draft): { options: RoverOptions; errors: Partial<Record<RoverField, string>> } {
  const options: RoverOptions = {}
  const errors: Partial<Record<RoverField, string>> = {}
  for (const f of ROVER_FIELDS) {
    const text = d[f.key].replace(/[\s,]/g, '')
    if (!text) continue
    const n = Number(text)
    if (!Number.isFinite(n)) errors[f.key] = `Give a number. ${limitWords(f)}`
    else if (n < f.min || n > f.max) errors[f.key] = limitWords(f)
    else options[f.key] = n
  }
  return { options, errors }
}

/** Whether any value is given (so the answer on screen is not the one with every assumption). */
export const anyGiven = (o: RoverOptions) => ROVER_FIELDS.some((f) => o[f.key] !== undefined)

/**
 * The service's reason for an assumption, without its closing "Give lander_antenna_m.": that
 * names a field of the request, and here the box for it is on screen.
 */
export const plainReason = (text: string) => text.replace(/\s*Give [a-z]+(?:_[a-z]+)+\.$/, '')
