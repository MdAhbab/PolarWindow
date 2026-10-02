// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { Select } from './Select'

afterEach(cleanup)

const SITES = [
  { value: 'a', label: 'Amundsen rim', group: 'Candidate sites' },
  { value: 'b', label: 'Connecting Ridge', group: 'Candidate sites' },
  { value: 'c', label: 'Mons Mouton', group: 'Mission landing spots' },
]

function setup(value = 'a', onChange = vi.fn()) {
  render(
    <>
      <label htmlFor="site">Site</label>
      <Select id="site" value={value} onChange={onChange} options={SITES} />
    </>,
  )
  return { box: screen.getByRole('combobox', { name: 'Site' }), onChange }
}

describe('Select', () => {
  it('is named by its label, says what is chosen, and keeps its list shut', () => {
    const { box } = setup('b')
    expect(box.textContent).toBe('Connecting Ridge')
    expect(box.getAttribute('aria-expanded')).toBe('false')
    expect(screen.queryByRole('listbox')).toBeNull()
  })

  it('opens on a press with the chosen option marked, under its groups', () => {
    const { box } = setup('b')
    fireEvent.click(box)
    expect(box.getAttribute('aria-expanded')).toBe('true')
    expect(screen.getByRole('listbox', { name: 'Site' })).toBeTruthy()
    expect(screen.getAllByRole('option').map((o) => o.textContent)).toEqual(['Amundsen rim', 'Connecting Ridge', 'Mons Mouton'])
    expect(screen.getByRole('option', { name: 'Connecting Ridge' }).getAttribute('aria-selected')).toBe('true')
    expect(screen.getByRole('group', { name: 'Mission landing spots' })).toBeTruthy()
    expect(box.getAttribute('aria-activedescendant')).toBe(screen.getByRole('option', { name: 'Connecting Ridge' }).id)
  })

  it('moves with the arrow keys and chooses with Enter', () => {
    const { box, onChange } = setup('a')
    fireEvent.keyDown(box, { key: 'ArrowDown' })
    fireEvent.keyDown(box, { key: 'ArrowDown' })
    fireEvent.keyDown(box, { key: 'ArrowDown' })
    expect(box.getAttribute('aria-activedescendant')).toBe(screen.getByRole('option', { name: 'Mons Mouton' }).id)
    fireEvent.keyDown(box, { key: 'Enter' })
    expect(onChange).toHaveBeenCalledWith('c')
    expect(screen.queryByRole('listbox')).toBeNull()
  })

  it('finds an option by the letters typed', () => {
    const { box, onChange } = setup('a')
    fireEvent.keyDown(box, { key: 'm' })
    expect(box.getAttribute('aria-activedescendant')).toBe(screen.getByRole('option', { name: 'Mons Mouton' }).id)
    fireEvent.keyDown(box, { key: ' ' })
    expect(onChange).toHaveBeenCalledWith('c')
  })

  it('closes on Esc without choosing, and keeps the key from whatever holds it', () => {
    const outer = vi.fn()
    const onChange = vi.fn()
    render(
      <div onKeyDown={outer}>
        <Select aria-label="Site" value="a" onChange={onChange} options={SITES} />
      </div>,
    )
    const box = screen.getByRole('combobox', { name: 'Site' })
    fireEvent.click(box)
    fireEvent.keyDown(box, { key: 'ArrowDown' })
    outer.mockClear()
    fireEvent.keyDown(box, { key: 'Escape' })
    expect(screen.queryByRole('listbox')).toBeNull()
    expect(onChange).not.toHaveBeenCalled()
    expect(outer).not.toHaveBeenCalled()
  })

  it('chooses the option pressed, and says nothing when it is the one already chosen', () => {
    const { box, onChange } = setup('a')
    fireEvent.click(box)
    fireEvent.click(screen.getByRole('option', { name: 'Amundsen rim' }))
    expect(onChange).not.toHaveBeenCalled()
    fireEvent.click(box)
    fireEvent.click(screen.getByRole('option', { name: 'Connecting Ridge' }))
    expect(onChange).toHaveBeenCalledWith('b')
  })

  it('shows its placeholder while nothing is chosen, and does not open when disabled', () => {
    render(<Select aria-label="Add a site" value="" onChange={() => {}} options={SITES} placeholder="Choose a site…" disabled />)
    const box = screen.getByRole('combobox', { name: 'Add a site' })
    expect(box.textContent).toBe('Choose a site…')
    fireEvent.click(box)
    expect(screen.queryByRole('listbox')).toBeNull()
  })
})
