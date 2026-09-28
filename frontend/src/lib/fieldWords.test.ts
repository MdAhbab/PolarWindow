import { describe, expect, it } from 'vitest'
import { fieldWords, toolWords, verdictWord } from './fieldWords'
import { compassWords } from './format'

describe('API names in words', () => {
  it('names a known field and its unit, and never converts the value', () => {
    expect(fieldWords('longest_dark_s')).toBe('longest night (seconds)')
    expect(fieldWords('sunlit_s')).toBe('time in sunlight (seconds)')
    expect(fieldWords('max_el_deg')).toBe('highest skyline (degrees)')
  })

  it('falls back to the name without underscores', () => {
    expect(fieldWords('some_new_field_s')).toBe('some new field (seconds)')
    expect(fieldWords('rank')).toBe('rank')
    expect(toolWords('get_metrics')).toBe('Site numbers')
    expect(toolWords('a_new_tool')).toBe('a new tool')
  })

  it('names the mission and space weather tools', () => {
    expect(toolWords('list_missions')).toBe('Mission list')
    expect(toolWords('get_mission_sections')).toBe('A mission’s sections')
    expect(toolWords('get_mission_section')).toBe('One section of a mission')
    expect(toolWords('get_space_weather')).toBe('Space weather now')
  })

  it('reads a path into a section as the field with where it sits', () => {
    expect(fieldWords('data.booster.wave_height_m.value')).toBe('booster: wave height (metres)')
    expect(fieldWords('data.opportunities[2].rules[0].chance.pm')).toBe('opportunities 3, rules 1: margin on chance')
    expect(fieldWords('now.solar_wind_km_s.value')).toBe('now: solar wind (kilometres a second)')
    expect(fieldWords('data.radiation.belts_mgy.hi')).toBe('radiation: high end of belts (milligray)')
  })

  it('finds the word a verdict guard caught', () => {
    expect(verdictWord("'safe' in summary is a verdict. Do not judge the whole.")).toBe('safe')
    expect(verdictWord('something else')).toBeNull()
    expect(verdictWord(undefined)).toBeNull()
  })
})

describe('compass points in words', () => {
  it('spells out every point', () => {
    expect(compassWords(0)).toBe('north')
    expect(compassWords(45)).toBe('north-east')
    expect(compassWords(67.5)).toBe('east-north-east')
    expect(compassWords(157.5)).toBe('south-south-east')
    expect(compassWords(-90)).toBe('west')
  })
})
