// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, screen } from '@testing-library/react'
import { renderApp } from '../../test/render'
import { WhatIfLink } from './ScenarioEntry'

afterEach(cleanup)

describe('WhatIfLink', () => {
  it('offers a scenario only on a mission still to fly', () => {
    renderApp(<WhatIfLink status="planned" />)
    expect(screen.getByRole('link', { name: /What if/ })).toBeTruthy()
  })

  it('stays away from a flown or cancelled mission: its record is what happened', () => {
    for (const status of ['completed', 'partial_success', 'lost_before_landing', 'cancelled']) {
      const { container } = renderApp(<WhatIfLink status={status} />)
      expect(container.textContent).not.toMatch(/What if/)
      cleanup()
    }
  })
})
