import { describe, expect, it } from 'vitest'
import type { IntakeDTO } from '../../lib/api/experience.types'
import model from '../../lib/api/__fixtures__/experience/intake.model.json'
import rules from '../../lib/api/__fixtures__/experience/intake.rules.json'
import { emptyForm, formFromDraft, intakeCounts, mergeIntake, toRequest, validate } from './formModel'

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

describe('the radio figures', () => {
  const named = { ...emptyForm(), name: 'X' }

  it('leaves out every radio figure that is empty, never sending 0', () => {
    expect(toRequest(named).lifecycle).toBeNull()
    const lc = toRequest({ ...named, mass: '300' }).lifecycle!
    for (const k of ['eirp_dbw', 'eirp_tol_db', 'gt_dbk', 'frequency_mhz', 'data_rates_kbps', 'required_ebn0_db', 'required_margin_db'])
      expect(k in lc).toBe(false)
  })

  it('sends only the figures that were typed, and keeps a typed 0', () => {
    const lc = toRequest({ ...named, eirp: '12.5', margin: '0' }).lifecycle!
    expect(lc.eirp_dbw).toBe(12.5)
    expect(lc.required_margin_db).toBe(0)
    expect('gt_dbk' in lc).toBe(false)
  })

  it('turns a typed list into numbers', () => {
    const f = { ...named, dataRates: '2, 64,256' }
    expect(validate(f)).toEqual({})
    expect(toRequest(f).lifecycle?.data_rates_kbps).toEqual([2, 64, 256])
  })

  it('says plainly what is wrong with a figure', () => {
    expect(validate({ ...named, dataRates: '2, fast, 256' }).dataRates).toMatch(/numbers above 0/)
    expect(validate({ ...named, dataRates: '2, 0' }).dataRates).toBeTruthy()
    expect(validate({ ...named, dataRates: Array(21).fill('1').join(',') }).dataRates).toMatch(/at most 20/)
    expect(validate({ ...named, eirp: '150' }).eirp).toMatch(/from -20 to 100 dBW/)
    expect(validate({ ...named, frequency: '0' }).frequency).toBeTruthy()
    expect(validate({ ...named, eirpTol: '-1', margin: 'x' })).toMatchObject({ eirpTol: expect.any(String), margin: expect.any(String) })
  })

  it('loads the stored figures into the form', () => {
    const f = formFromDraft({ name: 'X', lifecycle: { eirp_dbw: 14, data_rates_kbps: [2, 64], required_margin_db: 3 } })
    expect([f.eirp, f.dataRates, f.margin, f.gt]).toEqual(['14', '2, 64', '3', ''])
  })
})
