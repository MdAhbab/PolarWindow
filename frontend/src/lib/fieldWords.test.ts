import { describe, expect, it } from 'vitest'
import { fieldWords, toolWords } from './fieldWords'
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
