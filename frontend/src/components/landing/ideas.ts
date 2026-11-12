import type { ComponentType } from 'react'
import { SunPathArt, RidgeArt, EarthArt, IceArt } from '../../landing/Illustrations'
import type { ExampleKind } from './example'

/**
 * The four ideas the front page teaches. The first three sit over a film each;
 * the fourth is the closing film's captions (RIM_CAPTIONS in film.ts), and its
 * card sits on the Moon just before the product is shown.
 *
 * `body` is the card as it reads on its own. Where the card is shown in beats
 * over a scroll-driven film (the second and third), `beats.first` opens it
 * (title and the first sentences), `beats.second` is the beat with the real
 * example, and `lives` is the last beat: where the idea lives in the product.
 */
export interface Idea {
  id: 'sun' | 'ridge' | 'earth' | 'ice'
  title: string
  body: string
  Art: ComponentType
  /** The real figure shown under the drawing, when the service gives it. */
  example?: ExampleKind
  beats?: { first: string; second: string }
  /** Where this idea lives in the dashboard: a line, and one link to the page that shows it. */
  lives: { line: string; link: string; to: string }
}

export const IDEAS: readonly Idea[] = [
  {
    id: 'sun',
    title: 'The Sun never climbs',
    body: 'Near the Moon’s south pole the Sun doesn’t rise overhead. It circles along the horizon all month, so its light always arrives sideways.',
    Art: SunPathArt,
    example: 'sunlight',
    lives: { line: 'PolarWindow counts the hours of sunlight at each site.', link: 'See a site’s sunlight', to: '/site' },
  },
  {
    id: 'ridge',
    title: 'So a hill can switch off the Sun',
    body: 'Light that low is easy to block. A ridge kilometres away can put a lander in shadow for days. It has to survive on its batteries until the Sun returns.',
    Art: RidgeArt,
    example: 'night',
    beats: {
      first: 'Light that low is easy to block. A ridge kilometres away can put a lander in shadow for days.',
      second: 'In shadow it runs on its batteries until the Sun returns.',
    },
    lives: { line: 'PolarWindow times this for every site.', link: 'See a site’s longest night', to: '/site' },
  },
  {
    id: 'earth',
    title: 'Earth is low in the sky too',
    body: 'Radio needs a clear line to Earth. From the pole, Earth hangs near the horizon and bobs up and down. Hills cut off contact for stretches of time.',
    Art: EarthArt,
    example: 'contact',
    beats: {
      first: 'Radio needs a clear line to Earth. From the pole, Earth hangs near the horizon and bobs up and down.',
      second: 'When a hill covers it, the lander is out of contact.',
    },
    lives: { line: 'PolarWindow shows every stretch without contact at each site.', link: 'See a site’s time in contact', to: '/site' },
  },
  {
    id: 'ice',
    title: 'The ice is in the dark. The power is in the light.',
    body: 'Water ice survives only in crater floors the Sun never reaches. Solar power works only where it does. Missions land on the edge between them, so the exact spot matters.',
    Art: IceArt,
    lives: { line: 'The map shows every candidate site at the pole.', link: 'Open the map', to: '/map' },
  },
]

/** The closing film's three lines, in order: card 4's words, said as captions. */
export const RIM_LINES = ['The power is in the light.', 'The ice is in the dark.', 'So the exact spot matters.'] as const
