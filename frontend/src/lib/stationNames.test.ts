import { describe, expect, it } from 'vitest'
import { stationName } from './stationNames'

describe('stationName', () => {
  it('puts the place and the dish first and the station code second', () => {
    expect(stationName('DSS-14 (70-meter)')).toBe('Goldstone, 70 m dish (DSS-14)')
    expect(stationName('DSS-43 (70-meter)')).toBe('Canberra, 70 m dish (DSS-43)')
    expect(stationName('DSS-63 (70-meter)')).toBe('Madrid, 70 m dish (DSS-63)')
    expect(stationName('DSS-24 (34-m BWG)')).toBe('Goldstone, 34 m dish (DSS-24, BWG)')
    expect(stationName('DSS-65 (34-m HEF)')).toBe('Madrid, 34 m dish (DSS-65, HEF)')
  })

  it('keeps any other name as it is', () => {
    expect(stationName('DSS-24')).toBe('DSS-24')
    expect(stationName('ESTRACK Kourou')).toBe('ESTRACK Kourou')
    expect(stationName('DSS-84 (34-m BWG)')).toBe('DSS-84 (34-m BWG)')
  })
})
