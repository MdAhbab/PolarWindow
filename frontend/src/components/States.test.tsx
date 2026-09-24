// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { ProblemPanel, UncertaintyNote } from './States'
import { ApiError } from '../lib/api/client'

afterEach(cleanup)

describe('ProblemPanel', () => {
  it('renders the server problem as given: title, detail and what still works', () => {
    const e = new ApiError(409, {
      detail: {
        title: 'This site has not been surveyed yet',
        detail: "No horizon mask for 'nobile-rim-2'.",
        ui: { still_works: 'Sites that have been surveyed are unaffected.', retryable: true },
      },
    })
    const retry = vi.fn()
    render(<ProblemPanel error={e} onRetry={retry} />)
    expect(screen.getByText('This site has not been surveyed yet')).toBeTruthy()
    expect(screen.getByText("No horizon mask for 'nobile-rim-2'.")).toBeTruthy()
    expect(screen.getByText('Sites that have been surveyed are unaffected.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(retry).toHaveBeenCalled()
  })

  it('offers no retry when the server says retrying will not help, and keeps the next action', () => {
    const e = new ApiError(404, { detail: { title: "That mission isn't in the list", ui: { still_works: 'All other missions are available.', retryable: false } } })
    const back = vi.fn()
    render(<ProblemPanel error={e} onRetry={() => {}} action={{ label: 'Back to missions', onClick: back }} />)
    expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Back to missions' }))
    expect(back).toHaveBeenCalled()
  })

  it('is headed as an error, never a loader', () => {
    render(<ProblemPanel error={new ApiError(500, null)} />)
    expect(screen.queryByRole('progressbar')).toBeNull()
    expect(screen.getByText('Something went wrong')).toBeTruthy()
  })
})

describe('UncertaintyNote', () => {
  it('can speak about something other than chart margins', () => {
    render(
      <UncertaintyNote title="Built from the measurements" hatchKey={false}>
        body
      </UncertaintyNote>,
    )
    expect(screen.getByText('Built from the measurements')).toBeTruthy()
    expect(screen.queryByText(/drawn at every arc edge/)).toBeNull()
  })
})
