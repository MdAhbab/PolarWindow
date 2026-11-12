import { create } from 'zustand'

/**
 * The one sound control. The music is inside the two films that play by
 * themselves; everything starts muted, and the choice lasts for the visit (the
 * store lives as long as the page does, and is gone on a reload).
 */
export type FilmId = 'light' | 'rim'

/** Page order: if two were ever on screen at once, the earlier one is heard. */
export const FILM_ORDER: readonly FilmId[] = ['light', 'rim']

/** Which film is heard, if any: only with sound on, only one, only one in view. */
export function audibleFilm(soundOn: boolean, inView: Partial<Record<FilmId, boolean>>): FilmId | null {
  if (!soundOn) return null
  return FILM_ORDER.find((id) => inView[id]) ?? null
}

/** The control shows while one of the films that carries sound is on screen. */
export function soundControlShown(inView: Partial<Record<FilmId, boolean>>): boolean {
  return FILM_ORDER.some((id) => inView[id])
}

interface SoundState {
  soundOn: boolean
  inView: Partial<Record<FilmId, boolean>>
  toggle: () => void
  setInView: (id: FilmId, on: boolean) => void
}

export const useSound = create<SoundState>((set) => ({
  soundOn: false,
  inView: {},
  toggle: () => set((s) => ({ soundOn: !s.soundOn })),
  setInView: (id, on) => set((s) => (Boolean(s.inView[id]) === on ? s : { inView: { ...s.inView, [id]: on } })),
}))
