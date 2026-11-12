import { RIM_LINES, RIM_MORE } from './ideas'
import './landing.css'

/**
 * The closing film's three lines, each with one more line under it. Timed, they are captions in the
 * middle of the picture, set like a story caption: heavy, narrow capitals with the smaller line under
 * them, one at a time, cross-fading as the film's clock passes each window (captionAt in film.ts). The
 * captions are hidden from assistive technology and the same lines are read from a list beside them.
 * Not timed (a phone, reduced motion, data saver, a film that did not load), they are that list
 * itself, one under another, on a plate.
 */
export function Captions({ timed, index }: { timed: boolean; index: number | null }) {
  if (!timed) {
    return (
      <ul className="pw-caption-plate flex w-full max-w-xl flex-col gap-5 px-6 py-5 text-left sm:px-8 sm:py-6">
        {RIM_LINES.map((line, i) => (
          <li key={line} className="flex flex-col gap-1.5">
            <span className="pw-caption-strong text-[26px] leading-[1.05] sm:text-[34px]">{line}</span>
            <span className="text-body leading-body text-ink-2">{RIM_MORE[i]}</span>
          </li>
        ))}
      </ul>
    )
  }
  return (
    <>
      <div aria-hidden="true" data-caption={index === null ? 'none' : index} className="pw-caption-stage">
        <div className="pw-captions">
          {RIM_LINES.map((line, i) => (
            <div key={line} data-i={i} className="pw-caption flex flex-col items-center gap-3 sm:gap-4">
              <p className="pw-caption-strong text-[40px] leading-[0.98] sm:text-[64px] lg:text-[84px]">{line}</p>
              <p className="pw-caption-more max-w-[34ch] text-[17px] leading-[1.35] sm:text-[22px]">{RIM_MORE[i]}</p>
            </div>
          ))}
        </div>
      </div>
      <ul className="sr-only">
        {RIM_LINES.map((line, i) => (
          <li key={line}>
            {line} {RIM_MORE[i]}
          </li>
        ))}
      </ul>
    </>
  )
}
