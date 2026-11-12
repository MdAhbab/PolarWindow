// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, screen } from '@testing-library/react'
import type { Mission, StepMark } from '../lib/api/adapters'
import { StepStrip, hasWhat } from './StepStrip'
import { renderApp } from '../test/render'

afterEach(cleanup)

const SECTIONS = ['ready', 'launch', 'trip', 'landing', 'contact', 'return'] as const

function withMarks(marks: StepMark['mark'][], scenario: string | null = null): Mission {
  const steps = SECTIONS.map((section, i) => ({
    section,
    mark: marks[i],
    scenarioId: marks[i] === 'example' ? scenario : null,
  }))
  return { id: 'cs-8', name: 'CS-8', steps } as unknown as Mission
}

describe('StepStrip', () => {
  it('draws one link per step, in the worked example when that answers it', () => {
    renderApp(<StepStrip mission={withMarks(['input', 'input', 'input', 'example', 'record', 'example'], 'sc-1')} />)
    expect(screen.getAllByRole('link')).toHaveLength(6)
    expect(screen.getByRole('link', { name: 'Surface: worked example' }).getAttribute('href')).toBe(
      '/missions/cs-8/surface?scenario=sc-1',
    )
    expect(screen.getByRole('link', { name: 'Contact: from the record' }).getAttribute('href')).toBe('/missions/cs-8/contact')
    expect(screen.getByRole('link', { name: 'Ready: needs your input' }).getAttribute('href')).toBe('/missions/cs-8/ready')
  })

  it('draws nothing when no step applies', () => {
    const { container } = renderApp(<StepStrip mission={withMarks(Array(6).fill('none'))} />)
    expect(container.querySelector('ul')).toBeNull()
  })
})

describe('hasWhat', () => {
  const flown = withMarks(['record', 'record', 'record', 'none', 'record', 'record'])
  const planned = withMarks(['input', 'record', 'input', 'example', 'record', 'example'])
  const onlyReady = withMarks(['input', 'record', 'record', 'record', 'record', 'record'])

  it('full record: every step that applies is from the record', () => {
    expect(hasWhat(flown, 'record')).toBe(true)
    expect(hasWhat(planned, 'record')).toBe(false)
  })

  it('worked example and needs input; a hollow Ready alone does not count', () => {
    expect(hasWhat(planned, 'example')).toBe(true)
    expect(hasWhat(flown, 'example')).toBe(false)
    expect(hasWhat(planned, 'input')).toBe(true)
    expect(hasWhat(onlyReady, 'input')).toBe(false)
  })
})
