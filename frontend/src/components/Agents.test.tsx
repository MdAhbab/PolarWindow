// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, screen } from '@testing-library/react'
import { AgentCard } from './Agents'
import { guardLine } from './RunLog'
import { ApiUnreachable, type AgentDTO } from '../lib/api/client'
import { useMission } from '../lib/store'
import { renderApp } from '../test/render'

afterEach(cleanup)

const meta = (configured: boolean) => ({
  computed_at: '2026-09-24T07:34:50Z',
  resolution: {},
  uncertainty: { grounded: true, notes: [] },
  model: 'gemini-3.8-flash',
  agents_configured: configured,
  offline: false,
})

const answer = (over: Partial<AgentDTO>): AgentDTO =>
  ({
    status: 'ok',
    run_status: 'ok',
    reason: null,
    result: { paragraph: 'Connecting Ridge is sunlit for 574.4 hours.' },
    provenance: [{ claim: 'sunlit for 574.4 hours', value: 574.4, tool: 'get_metrics', call_seq: 2, field: 'sunlit_s' }],
    tool_calls: [],
    run_id: 'run-1',
    attempts: 1,
    latency_ms: 3200,
    guard_failures: [],
    meta: meta(true),
    ...over,
  }) as unknown as AgentDTO

const idle = { isIdle: false, isPending: false, isError: false, error: null, cancel: () => {} }

describe('AgentCard', () => {
  it('ok: the answer as text, the numbers used, and the way to the run log', () => {
    renderApp(<AgentCard kind="explain" agent={{ ...idle, data: answer({}) }} />)
    expect(screen.getByText(/^AI answer · gemini-3\.8-flash · 3\.2 s · \d+ numbers, each checked/)).toBeTruthy()
    expect(screen.getByText('Connecting Ridge is sunlit for 574.4 hours.')).toBeTruthy()
    const cell = screen.getByText('Site numbers · time in sunlight (seconds)')
    expect(cell.closest('tr')?.textContent).toContain('574.4')
    fireEvent.click(screen.getByRole('button', { name: 'How the AI got this' }))
    expect(useMission.getState().runLog).toEqual({ open: true, runId: 'run-1' })
  })

  it('never renders model text as HTML', () => {
    const data = answer({ result: { paragraph: '<img src=x onerror=alert(1)><b>bold</b>' } })
    const { container } = renderApp(<AgentCard kind="explain" agent={{ ...idle, data }} />)
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('b')).toBeNull()
    expect(screen.getByText('<img src=x onerror=alert(1)><b>bold</b>')).toBeTruthy()
  })

  it('insufficient data: the reason verbatim, a way to rephrase, and no partial answer', () => {
    const rephrase = vi.fn()
    const data = answer({ status: 'insufficient_data', reason: 'No site in the dataset is named Atlantis.', provenance: [] })
    renderApp(<AgentCard kind="ask" agent={{ ...idle, data }} onRephrase={rephrase} />)
    expect(screen.getByText('Not enough data to answer')).toBeTruthy()
    expect(screen.getByText('No site in the dataset is named Atlantis.')).toBeTruthy()
    expect(screen.queryByText('Numbers used')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Rephrase' }))
    expect(rephrase).toHaveBeenCalled()
  })

  it('degraded with no model configured: a first-class summary, not an error', () => {
    const data = answer({ status: 'degraded', run_status: 'degraded', reason: 'not configured', meta: meta(false) } as unknown as Partial<AgentDTO>)
    renderApp(<AgentCard kind="explain" agent={{ ...idle, data }} />)
    expect(screen.getByText(/^Summary from measurements \(no AI\)/)).toBeTruthy()
    expect(screen.getByText(/No AI model is set up on this server/)).toBeTruthy()
    expect(screen.getByText('Connecting Ridge is sunlit for 574.4 hours.')).toBeTruthy()
    expect(screen.queryByText('What still works')).toBeNull()
  })

  it('degraded after a timeout keeps the server reason', () => {
    const data = answer({ status: 'degraded', run_status: 'timeout', reason: 'The model took longer than 20 s.' } as Partial<AgentDTO>)
    renderApp(<AgentCard kind="explain" agent={{ ...idle, data }} />)
    expect(screen.getByText(/The AI didn't respond/)).toBeTruthy()
    expect(screen.getByText('The model took longer than 20 s.')).toBeTruthy()
  })

  it('guard rejected: says a number could not be traced, then the measurements', () => {
    const data = answer({ status: 'degraded', run_status: 'guard_rejected' } as Partial<AgentDTO>)
    renderApp(<AgentCard kind="explain" agent={{ ...idle, data }} />)
    expect(screen.getByText(/^Summary from measurements \(AI answer replaced\)/)).toBeTruthy()
    expect(screen.getByText(/included a number we couldn't trace to a measurement/)).toBeTruthy()
  })

  it('guard rejected for a verdict word: names the word and leaves the decision to people', () => {
    const detail = "'no-go' in summary is a verdict. Do not judge the whole, not even to deny it."
    const data = answer({ status: 'degraded', run_status: 'guard_rejected', guard_failures: [{ kind: 'verdict_word', detail, value: null }] } as Partial<AgentDTO>)
    renderApp(<AgentCard kind="explain" agent={{ ...idle, data }} />)
    expect(screen.getByText(/judged the whole \(“no-go”\) instead of saying what each number shows/)).toBeTruthy()
    expect(screen.queryByText(/couldn't trace/)).toBeNull()
    expect(screen.queryByText(/Do not judge/)).toBeNull()
  })

  it('guard rejected for both: says both reasons', () => {
    const data = answer({
      status: 'degraded',
      run_status: 'guard_rejected',
      guard_failures: [
        { kind: 'ungrounded_number', detail: '42 not found', value: 42 },
        { kind: 'verdict_word', detail: "'safe' in summary is a verdict.", value: null },
      ],
    } as Partial<AgentDTO>)
    renderApp(<AgentCard kind="explain" agent={{ ...idle, data }} />)
    expect(screen.getByText(/couldn't trace to a measurement and judged the whole \(“safe”\)/)).toBeTruthy()
  })

  it('loading: says what is being checked, and Cancel aborts', () => {
    const cancel = vi.fn()
    renderApp(<AgentCard kind="ask" agent={{ ...idle, isPending: true, cancel }} />)
    expect(screen.getByRole('status').textContent).toBe('Writing… every number is checked against the measurements')
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(cancel).toHaveBeenCalled()
  })

  it('HTTP failure: the error panel, fed from the problem detail', () => {
    renderApp(<AgentCard kind="ask" agent={{ ...idle, isError: true, error: new ApiUnreachable(new TypeError('Failed to fetch')) }} />)
    expect(screen.getByText('Cannot reach the service that does the calculations')).toBeTruthy()
    expect(screen.getByText('What still works')).toBeTruthy()
    expect(screen.queryByText(/Failed to fetch/)).toBeNull()
  })
})

describe('How the AI got this: a guard in words', () => {
  it('a verdict word is named, not the instruction written to the model', () => {
    expect(guardLine({ kind: 'verdict_word', detail: "'go for launch' in summary is a verdict. Do not judge the whole." })).toBe(
      'Rejected: “go for launch” judges the whole instead of saying what each number shows',
    )
    expect(guardLine({ kind: 'ungrounded_number', value: 42 })).toBe('Rejected: 42 is not in the data it looked up')
  })
})
