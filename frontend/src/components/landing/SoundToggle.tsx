import { soundControlShown, useSound } from './sound'
import './landing.css'

/**
 * The one control for sound: the music is inside the two films that play by
 * themselves, everything starts silent, and this turns it on. It is fixed at
 * the bottom right and shown only while one of those two films is on screen
 * (the scroll-driven ones never have sound, so it would promise nothing there).
 * The label says how things stand now, and `aria-pressed` says the same to a
 * screen reader. 44 px tall, and out of the tab order while it is hidden.
 */
export function SoundToggle() {
  const soundOn = useSound((s) => s.soundOn)
  const toggle = useSound((s) => s.toggle)
  const shown = useSound((s) => soundControlShown(s.inView))
  return (
    <div className="pw-sound" data-shown={shown} data-theme="dark">
      <button
        type="button"
        aria-pressed={soundOn}
        onClick={toggle}
        tabIndex={shown ? 0 : -1}
        className="pw-press inline-flex h-11 min-w-28 items-center justify-center rounded-pill border border-line-strong bg-raised px-5 text-control font-semibold text-ink hover:border-ink-3 hover:bg-inset"
      >
        {soundOn ? 'Sound on' : 'Sound off'}
      </button>
    </div>
  )
}
