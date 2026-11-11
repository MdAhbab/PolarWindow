import { describe, expect, it } from 'vitest'
import type { IntakeDTO } from '../../lib/api/experience.types'
import model from '../../lib/api/__fixtures__/experience/intake.model.json'
import rules from '../../lib/api/__fixtures__/experience/intake.rules.json'
import { emptyForm, intakeCounts, mergeIntake, toRequest, validate } from './formModel'

const modelRead = model as unknown as IntakeDTO
const rulesRead = rules as unknown as IntakeDTO

describe('merging files into the form', () => {
  it('fills an empty form and says where each value came from', () => {
    const m = mergeIntake(emptyForm(), {}, modelRead)
    expect(m.form.name).toBe('Aurora 1')
    expect(m.form.landing).toEqual({ date: '2027-10-14', precision: 'month' })
    expect(m.form.launch.date).toBe('')
    expect(m.provenance.landing?.field.confidence).toBe('inferred')
    expect(m.provenance.launch).toBeUndefined()
    expect(m.conflicts).toEqual([])
    expect(intakeCounts(modelRead)).toEqual({ found: 7, lookedFor: 9 })
  })

  it('a later file fills only what is empty and lists what differs', () => {
    const first = mergeIntake(emptyForm(), {}, modelRead)
    const second = mergeIntake(first.form, first.provenance, rulesRead)
    expect(second.form.provider).toBe('Firefly Aerospace')
    expect(second.conflicts).toContain('provider')
    expect(second.conflicts).toContain('landing')
    const over = mergeIntake(first.form, first.provenance, rulesRead, true)
    expect(over.form.provider).toBe('Intuitive Machines')
  })
})

describe('checking and sending', () => {
  it('needs only a name', () => {
    expect(validate(emptyForm()).name).toBeTruthy()
    const f = { ...emptyForm(), name: 'X' }
    expect(validate(f)).toEqual({})
    expect(toRequest(f).lifecycle).toBeNull()
    expect(toRequest(f).target).toBeNull()
  })

  it('checks dates, latitude, longitude and numbers as the server does', () => {
    const f = { ...emptyForm(), name: 'X', targetMode: 'coords' as const, lat: '-95', lon: '400', mass: '0', plannedDays: 'abc' }
    f.landing = { date: '2027-02-30', precision: 'day' }
    expect(Object.keys(validate(f)).sort()).toEqual(['landing', 'lat', 'lon', 'mass', 'plannedDays'])
  })

  it('turns a negative longitude into degrees east', () => {
    const f = { ...emptyForm(), name: 'X', targetMode: 'coords' as const, lat: '-85', lon: '-30' }
    expect(toRequest(f).target).toEqual({ name: null, lat_deg: -85, lon_deg: 330 })
  })
})
