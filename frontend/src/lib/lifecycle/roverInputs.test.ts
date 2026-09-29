import { describe, expect, it } from 'vitest'
import { EMPTY_DRAFT, ROVER_FIELDS, anyGiven, draftOf, limitWords, plainReason, readDraft } from './roverInputs'

describe('the rover’s line of sight, asked for other values', () => {
  it('says each limit as the service holds it', () => {
    expect(ROVER_FIELDS.map(limitWords)).toEqual(['Between 50 and 5,000 m.', 'Between 0 and 50 m.', 'Between 0 and 50 m.', 'Between 30 and 100,000 MHz.'])
  })

  it('reads only the boxes filled in, as people write numbers, and leaves the rest for the service to assume', () => {
    expect(readDraft(EMPTY_DRAFT)).toEqual({ options: {}, errors: {} })
    expect(readDraft({ radius_m: '1,200', lander_antenna_m: '', rover_antenna_m: ' 0.5 ', freq_mhz: '8 400' })).toEqual({
      options: { radius_m: 1200, rover_antenna_m: 0.5, freq_mhz: 8400 },
      errors: {},
    })
    // A limit is a value that can be asked for: both ends are in.
    expect(readDraft({ radius_m: '50', lander_antenna_m: '0', rover_antenna_m: '50', freq_mhz: '100000' }).errors).toEqual({})
  })

  it('names, at the box, what cannot be used: a number outside the limits, or no number at all', () => {
    const { options, errors } = readDraft({ radius_m: '10', lander_antenna_m: '51', rover_antenna_m: '-1', freq_mhz: 'fast' })
    expect(options).toEqual({})
    expect(errors).toEqual({
      radius_m: 'Between 50 and 5,000 m.',
      lander_antenna_m: 'Between 0 and 50 m.',
      rover_antenna_m: 'Between 0 and 50 m.',
      freq_mhz: 'Give a number. Between 30 and 100,000 MHz.',
    })
    expect(readDraft({ ...EMPTY_DRAFT, radius_m: '5001' }).errors.radius_m).toBe('Between 50 and 5,000 m.')
    expect(readDraft({ ...EMPTY_DRAFT, freq_mhz: '29.9' }).errors.freq_mhz).toBe('Between 30 and 100,000 MHz.')
  })

  it('puts what is in force back in the boxes', () => {
    expect(draftOf({})).toEqual(EMPTY_DRAFT)
    expect(draftOf({ radius_m: 300, freq_mhz: 8400 })).toEqual({ radius_m: '300', lander_antenna_m: '', rover_antenna_m: '', freq_mhz: '8400' })
    expect(anyGiven({})).toBe(false)
    expect(anyGiven({ rover_antenna_m: 0 })).toBe(true)
  })

  it('drops the service’s closing hint that names a field of the request, since the box is on screen', () => {
    expect(plainReason("The lander's antenna height is not published; assumed. Give lander_antenna_m.")).toBe("The lander's antenna height is not published; assumed.")
    expect(plainReason("2.4 GHz is assumed (only the radio path depends on it). Give freq_mhz.")).toBe('2.4 GHz is assumed (only the radio path depends on it).')
    expect(plainReason('As given in the request.')).toBe('As given in the request.')
    expect(plainReason('Give a number.')).toBe('Give a number.')
  })
})
