// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import type { RoverSightDTO, SectionDTO } from '../../lib/api/lifecycle'
import roverFixture from '../../lib/api/__fixtures__/lifecycle/rover.json'
import { RoverInputs } from './RoverInputs'

const answer = (roverFixture as unknown as SectionDTO<RoverSightDTO>).data

afterEach(cleanup)

const box = (label: RegExp) => screen.getByLabelText(label) as HTMLInputElement

describe('Try other values', () => {
  it('shows what is in use for each box, assumed unless given, and asks for nothing until the button is pressed', () => {
    const onApply = vi.fn()
    render(<RoverInputs answer={answer} given={{}} onApply={onApply} />)
    expect(screen.getByText('Between 50 and 5,000 m. In use: 500 m, assumed.')).toBeTruthy()
    expect(screen.getByText('Between 0 and 50 m. In use: 3 m, assumed.')).toBeTruthy()
    expect(screen.getByText('Between 0 and 50 m. In use: 0.3 m, assumed.')).toBeTruthy()
    expect(screen.getByText('Between 30 and 100,000 MHz. In use: 2,400 MHz, assumed.')).toBeTruthy()
    // An empty box says what it will keep.
    expect(box(/^How far from the lander, metres$/).placeholder).toBe('500')
    expect(box(/^Radio frequency, MHz$/).placeholder).toBe('2,400')
    const go = screen.getByRole('button', { name: 'Work it out with these' }) as HTMLButtonElement
    expect(go.disabled).toBe(true)
    fireEvent.change(box(/^How far from the lander/), { target: { value: '300' } })
    expect(go.disabled).toBe(false)
    expect(onApply).not.toHaveBeenCalled()
    // Only what was typed is asked for.
    fireEvent.change(box(/^Lander’s antenna above the ground/), { target: { value: '3' } })
    fireEvent.click(go)
    expect(onApply).toHaveBeenCalledWith({ radius_m: 300, lander_antenna_m: 3 })
    expect(screen.queryByRole('button', { name: 'Back to the assumed values' })).toBeNull()
  })

  it('tells a slip at its box and asks for nothing', () => {
    const onApply = vi.fn()
    render(<RoverInputs answer={answer} given={{}} onApply={onApply} />)
    fireEvent.change(box(/^Rover’s antenna above the ground/), { target: { value: '90' } })
    fireEvent.change(box(/^Radio frequency/), { target: { value: 'fast' } })
    fireEvent.click(screen.getByRole('button', { name: 'Work it out with these' }))
    expect(screen.getByText('Between 0 and 50 m.', { selector: 'p.font-semibold' })).toBeTruthy()
    expect(screen.getByText('Give a number. Between 30 and 100,000 MHz.')).toBeTruthy()
    expect(box(/^Rover’s antenna above the ground/).getAttribute('aria-invalid')).toBe('true')
    expect(onApply).not.toHaveBeenCalled()
    // Fixing the box takes its message away.
    fireEvent.change(box(/^Rover’s antenna above the ground/), { target: { value: '1' } })
    expect(screen.queryByText('Between 0 and 50 m.', { selector: 'p.font-semibold' })).toBeNull()
  })

  it('starts from the values in force, says they are the team’s, and goes back to the assumed ones on request', () => {
    const onApply = vi.fn()
    render(<RoverInputs answer={{ ...answer, radius_m: 300 }} given={{ radius_m: 300 }} onApply={onApply} />)
    expect(box(/^How far from the lander/).value).toBe('300')
    expect(screen.getByText('Between 50 and 5,000 m. In use: 300 m, as you gave it.')).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Work it out with these' }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Back to the assumed values' }))
    expect(onApply).toHaveBeenCalledWith({})
    expect(box(/^How far from the lander/).value).toBe('')
  })
})
