import { describe, expect, it } from 'vitest'
import { subSolarAt, subSolarFromLook } from './subSolar'

describe('subSolarFromLook', () => {
  it('puts the Sun overhead at the site when it is at the zenith', () => {
    const p = subSolarFromLook(-30, 45, 123, 90)
    expect(p.latDeg).toBeCloseTo(-30, 9)
    expect(p.lonDeg).toBeCloseTo(45, 9)
  })

  it('puts a Sun rising due east at the equator a quarter-turn east', () => {
    const p = subSolarFromLook(0, 10, 90, 0)
    expect(p.latDeg).toBeCloseTo(0, 9)
    expect(p.lonDeg).toBeCloseTo(100, 9)
  })

  it('puts a Sun on the horizon due north of the south pole on the equator', () => {
    // At the pole every direction is north; azimuth is measured from the
    // meridian of the site's longitude.
    const p = subSolarFromLook(-89.999999, 0, 0, 0)
    expect(p.latDeg).toBeCloseTo(0, 4)
  })

  it('reads a Sun below the flat horizon at the pole as a northern sub-solar latitude', () => {
    expect(subSolarFromLook(-90 + 1e-9, 0, 0, -1.2).latDeg).toBeCloseTo(1.2, 5)
  })
})

describe('subSolarAt', () => {
  const tl = {
    start: '2027-03-14T00:00:00Z',
    t_s: [0, 900, 1800],
    sun: { az_deg: [90, 90, 90], el_deg: [0, 10, 20], mask_el_deg: [], margin_deg: [], state: [] },
  }
  it('takes the nearest sample', () => {
    const at = Date.parse('2027-03-14T00:14:00Z')
    expect(subSolarAt(tl, 0, 0, at)).toEqual(subSolarFromLook(0, 0, 90, 10))
  })
  it('is null outside the span', () => {
    expect(subSolarAt(tl, 0, 0, Date.parse('2027-03-15T00:00:00Z'))).toBeNull()
  })
})
