import { RIM_LINES } from './ideas'
import './landing.css'

/**
 * The closing film's three lines. Timed, they are captions: one line at a time
 * on their own plate, cross-fading as the film's clock passes each line's
 * window (captionAt in film.ts); the plate is hidden from assistive
 * technology and the same three lines are read from a list beside it. Not
 * timed (a phone, reduced motion, data saver, a film that did not load), they
 * are that list itself, one under another, on the plate.
 */
export function Captions({ timed, index }: { timed: boolean; index: number | null }) {
  if (!timed) {
    return (
      <ul className="pw-caption-plate flex w-full max-w-xl flex-col gap-3 px-6 py-5 text-left sm:px-8 sm:py-6">
        {RIM_LINES.map((line) => (
          <li key={line} className="pw-display text-[22px] leading-[1.2] sm:text-[28px]">
            {line}
          </li>
        ))}
      </ul>
    )
  }
  return (
    <>
      <div
        aria-hidden="true"
        data-caption={index === null ? 'none' : index}
        className="pw-caption-plate max-w-full px-6 py-4 sm:px-10 sm:py-5"
      >
        <div className="pw-captions">
          {RIM_LINES.map((line, i) => (
            <p key={line} data-i={i} className="pw-caption pw-display text-[24px] leading-[1.2] sm:text-[34px]">
              {line}
            </p>
          ))}
        </div>
      </div>
      <ul className="sr-only">
        {RIM_LINES.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </>
  )
}
