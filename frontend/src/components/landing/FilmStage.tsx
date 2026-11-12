import { useCallback, useState } from 'react'
import { AutoplayFilm } from './AutoplayFilm'
import { Captions } from './Captions'
import { EnterButton, ENTER_WORDS } from './Enter'
import { captionAt } from './film'
import { IdeaCard } from './IdeaCard'
import type { Idea } from './ideas'
import { useFilmFiles } from './useFilmFiles'
import './landing.css'

/**
 * The first film, straight after the hero: `light` plays by itself, full
 * screen, with the section's heading and the first idea card over a shade on
 * the left. If the film does not load, the section keeps its words and the
 * Moon shows behind them, as the page did before there were films.
 */
export function LightStage({
  idea,
  total,
  autoplay,
  small,
  animate,
}: {
  idea: Idea
  total: number
  autoplay: boolean
  small: boolean
  animate: boolean
}) {
  const [broken, setFailed] = useState(false)
  const files = useFilmFiles()
  const failed = broken || files === 'no'
  return (
    <section
      data-theme="dark"
      data-film={failed ? 'off' : 'on'}
      className="pw-film flex min-h-[100dvh] flex-col justify-center gap-10 px-4 py-24 lg:px-8 lg:py-36"
    >
      {!failed && <AutoplayFilm id="light" still={!autoplay} small={small} ready={files === 'yes'} onFail={() => setFailed(true)} />}
      <div aria-hidden="true" className="pw-film-shade" />
      <h2 data-reveal className="pw-display relative z-10 max-w-xl text-[32px] leading-[1.06] sm:text-[44px]">
        Why the south pole is hard
      </h2>
      <div className="relative z-10">
        <IdeaCard idea={idea} index={0} total={total} variant="stacked" animate={animate} />
      </div>
    </section>
  )
}

/**
 * The last film: the rim and the descent, playing by itself, with the fourth
 * idea's words as captions and the way in below them. The button is always
 * there (not only while the last caption shows), so it can always be reached.
 */
export function CloseStage({ autoplay, phone, small }: { autoplay: boolean; phone: boolean; small: boolean }) {
  const [broken, setFailed] = useState(false)
  const files = useFilmFiles()
  const failed = broken || files === 'no'
  const [caption, setCaption] = useState<number | null>(0)
  const timed = autoplay && !phone && !failed
  const onTime = useCallback((t: number) => {
    const c = captionAt(t)
    setCaption((prev) => (prev === c ? prev : c))
  }, [])
  return (
    <section
      data-theme="dark"
      data-film={failed ? 'off' : 'on'}
      aria-labelledby="close-h"
      className="pw-film flex min-h-[100dvh] items-end justify-center px-4 pt-32 pb-16 lg:px-8"
    >
      {!failed && (
        <AutoplayFilm id="rim" still={!autoplay} small={small} ready={files === 'yes'} onFail={() => setFailed(true)} onTime={timed ? onTime : undefined} />
      )}
      <div aria-hidden="true" className="pw-film-shade pw-film-shade-low" />
      <div data-reveal className="relative z-10 flex w-full max-w-3xl flex-col items-center gap-8 text-center">
        <h2 id="close-h" className="sr-only">
          {ENTER_WORDS}
        </h2>
        <Captions timed={timed} index={caption} />
        <EnterButton />
      </div>
    </section>
  )
}
