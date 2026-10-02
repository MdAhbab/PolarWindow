import markOnDark from '../assets/brand/mark-on-dark.png'
import markOnLight from '../assets/brand/mark-on-light.png'
import wordsOnDark from '../assets/brand/wordmark-on-dark.png'
import wordsOnLight from '../assets/brand/wordmark-on-light.png'
import logoOnDark from '../assets/brand/logo-on-dark.png'
import logoOnLight from '../assets/brand/logo-on-light.png'

/**
 * The POLAR WINDOW logo, in the version for the ground under it: light lines
 * on a dark page, ink on a light one. The version follows `data-theme`, not
 * the system setting, so the report's paper (a light page inside a dark one)
 * gets the ink logo (`.pw-logo-on-dark` and `.pw-logo-on-light` in globals.css).
 *
 * The full logo's words are too small to read at the size of a header, so
 * there the mark and the words are set side by side at their own sizes
 * (`BrandName`); the full logo is for places it can be large (`BrandLogo`).
 */
function Pair({ dark, light, alt, className }: { dark: string; light: string; alt: string; className: string }) {
  return (
    <>
      <img src={dark} alt={alt} className={`pw-logo-on-dark w-auto shrink-0 ${className}`} draggable={false} />
      <img src={light} alt={alt} className={`pw-logo-on-light w-auto shrink-0 ${className}`} draggable={false} />
    </>
  )
}

/** The mark alone: the P over the horizon line, with the crescent. */
export function BrandMark({ className = 'h-8', alt = 'POLAR WINDOW' }: { className?: string; alt?: string }) {
  return <Pair dark={markOnDark} light={markOnLight} alt={alt} className={className} />
}

/** The mark and the words, for a header. The words are named once, by the mark's text alternative. */
export function BrandName({ mark = 'h-7', words = 'h-[8px] sm:h-[9px]' }: { mark?: string; words?: string }) {
  return (
    <span className="flex items-center gap-2.5 sm:gap-3">
      <BrandMark className={mark} />
      <Pair dark={wordsOnDark} light={wordsOnLight} alt="" className={words} />
    </span>
  )
}

/** The full logo, where it can be large enough for its words to be read. */
export function BrandLogo({ className = 'h-14' }: { className?: string }) {
  // Its own box, so a column it sits in cannot stretch it to its width.
  return (
    <span className="inline-flex max-w-full shrink-0">
      <Pair dark={logoOnDark} light={logoOnLight} alt="POLAR WINDOW" className={`max-w-full object-contain ${className}`} />
    </span>
  )
}
