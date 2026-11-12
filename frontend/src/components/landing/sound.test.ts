import { beforeEach, describe, expect, it } from 'vitest'
import { audibleFilm, soundControlShown, useSound } from './sound'

describe('which film is heard', () => {
  it('is none with sound off, however many are on screen', () => {
    expect(audibleFilm(false, {})).toBeNull()
    expect(audibleFilm(false, { light: true })).toBeNull()
    expect(audibleFilm(false, { light: true, rim: true })).toBeNull()
  })

  it('is none with sound on and no film in view', () => {
    expect(audibleFilm(true, {})).toBeNull()
    expect(audibleFilm(true, { light: false, rim: false })).toBeNull()
  })

  it('is the film in view, and only that one', () => {
    expect(audibleFilm(true, { light: true })).toBe('light')
    expect(audibleFilm(true, { rim: true })).toBe('rim')
  })

  it('is never two: with both in view the earlier one in the page is heard', () => {
    expect(audibleFilm(true, { light: true, rim: true })).toBe('light')
  })
})

describe('the control', () => {
  it('shows while a film that carries sound is on screen', () => {
    expect(soundControlShown({})).toBe(false)
    expect(soundControlShown({ light: true })).toBe(true)
    expect(soundControlShown({ light: false, rim: true })).toBe(true)
    expect(soundControlShown({ light: false, rim: false })).toBe(false)
  })
})

describe('the sound state', () => {
  beforeEach(() => useSound.setState({ soundOn: false, inView: {} }))

  it('starts muted and is turned on and off by the one control', () => {
    expect(useSound.getState().soundOn).toBe(false)
    useSound.getState().toggle()
    expect(useSound.getState().soundOn).toBe(true)
    useSound.getState().toggle()
    expect(useSound.getState().soundOn).toBe(false)
  })

  it('keeps the choice while the films come and go', () => {
    useSound.getState().toggle()
    useSound.getState().setInView('light', true)
    useSound.getState().setInView('light', false)
    useSound.getState().setInView('rim', true)
    expect(useSound.getState().soundOn).toBe(true)
    const { soundOn, inView } = useSound.getState()
    expect(audibleFilm(soundOn, inView)).toBe('rim')
  })

  it('does not notify for a film that is already as it was said to be', () => {
    useSound.getState().setInView('light', true)
    const before = useSound.getState().inView
    useSound.getState().setInView('light', true)
    expect(useSound.getState().inView).toBe(before)
  })
})
