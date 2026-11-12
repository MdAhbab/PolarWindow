import { useEffect, useRef, useState } from 'react'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { filmNative, SCRUB_FRAMES, SCRUB_FPS, approach, beatFor, frameAt, frameTime, progressToTime, seeksTooSlow, type Beats } from './film'
import { FilmFrame } from './FilmFrame'
import { IdeaCard } from './IdeaCard'
import type { Idea } from './ideas'
import { useFilmFiles } from './useFilmFiles'
import './landing.css'

gsap.registerPlugin(ScrollTrigger)

/**
 * A film that scroll drives: a full-screen stage pinned (position: sticky) for
 * two and a half screens, whose film moves forward as the page scrolls down and
 * back as it scrolls up, with its idea card in beats on top. Nothing plays by
 * itself.
 *
 * The film is an MP4 in which every frame is a keyframe (120 frames, 12 per
 * second, no sound), so a seek costs about the same anywhere. Scroll only
 * stores a number (GSAP ScrollTrigger's progress, in a variable, not in React
 * state); one animation frame at a time then moves the film's time toward it,
 * seeks when the frame changes, and sets which beat shows on the stage
 * element's data attribute. If the first three seeks each take longer than
 * SEEK_LIMIT_MS the stage gives up on scrubbing and shows the card over the
 * poster; if the file does not load it shows the card over the Moon.
 *
 * Phones, reduced motion and data saver get the other shape (`pinned` false):
 * the poster as a still behind the whole card, no pinning.
 */
export function ScrubStage({
  idea,
  index,
  total,
  film,
  beats,
  pinned,
  small,
  animate,
}: {
  idea: Idea
  index: number
  total: number
  film: 'shadow' | 'earth'
  beats: Beats
  /** Scrubbing is allowed on this device and setting. */
  pinned: boolean
  /** The small file rather than the large one. */
  small: boolean
  animate: boolean
}) {
  const [seen, setStatus] = useState<'ok' | 'slow' | 'failed'>('ok')
  const files = useFilmFiles()
  const status = files === 'no' ? 'failed' : seen
  const poster = `/landing/${film}-poster${small ? '-small' : ''}.jpg`

  if (!pinned || status !== 'ok') {
    return (
      <section
        data-theme="dark"
        data-film={status === 'failed' ? 'off' : 'on'}
        className="pw-film flex min-h-[100dvh] items-center px-4 py-24 lg:px-8"
      >
        {status !== 'failed' && (
          <FilmFrame native={filmNative(film, small ? 'small' : 'large')} grain={files === 'yes'}>
            {(report) => (
              <img
                src={files === 'yes' ? poster : undefined}
                alt=""
                aria-hidden="true"
                className="pw-film-media"
                loading="lazy"
                decoding="async"
                onLoad={(e) => report(e.currentTarget.naturalWidth, e.currentTarget.naturalHeight)}
                onError={() => setStatus('failed')}
              />
            )}
          </FilmFrame>
        )}
        <div aria-hidden="true" className="pw-film-shade" />
        <div className="relative z-10 w-full">
          <IdeaCard idea={idea} index={index} total={total} variant="stacked" animate={animate} />
        </div>
      </section>
    )
  }
  return (
    <Pinned
      idea={idea}
      index={index}
      total={total}
      film={film}
      beats={beats}
      animate={animate}
      poster={poster}
      small={small}
      ready={files === 'yes'}
      onStatus={setStatus}
    />
  )
}

function Pinned({
  idea,
  index,
  total,
  film,
  beats,
  animate,
  poster,
  small,
  ready,
  onStatus,
}: {
  idea: Idea
  index: number
  total: number
  film: 'shadow' | 'earth'
  beats: Beats
  animate: boolean
  poster: string
  small: boolean
  /** The film files are known to be there (useFilmFiles). */
  ready: boolean
  onStatus: (s: 'slow' | 'failed') => void
}) {
  const outer = useRef<HTMLElement>(null)
  const pin = useRef<HTMLDivElement>(null)
  const vid = useRef<HTMLVideoElement>(null)
  const [near, setNear] = useState(false)

  // A screen away: start to load the file.
  useEffect(() => {
    const el = outer.current
    if (!el) return
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setNear(true)
          io.disconnect()
        }
      },
      { rootMargin: '100% 0px 100% 0px' },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [])

  useEffect(() => {
    const stage = outer.current
    const frame = pin.current
    const v = vid.current
    if (!stage || !frame || !v) return

    let progress = 0
    let current = 0 // the film's time as drawn, in seconds
    let lastFrame = -1
    let lastBeat = -1
    let held: number | null = null // a beat kept on screen while its link has keyboard focus
    let raf = 0
    let seekStart = 0
    let seeking = false
    let measuring = false
    const seekMs: number[] = []

    const setBeat = (b: number) => {
      if (b === lastBeat) return
      lastBeat = b
      frame.dataset.beat = String(b)
    }

    const tick = () => {
      raf = 0
      setBeat(held ?? beatFor(progress, beats))
      // No file yet (it loads when the stage is a screen away): the loadedmetadata event starts this again.
      if (v.readyState < 1) return
      const duration = Number.isFinite(v.duration) && v.duration > 0 ? v.duration : SCRUB_FRAMES / SCRUB_FPS
      const target = progressToTime(progress, duration)
      current = approach(current, target)
      const f = frameAt(current)
      let settled = f === lastFrame && current === target
      if (f !== lastFrame) {
        if (!v.seeking) {
          const t = frameTime(f)
          seekStart = performance.now()
          seeking = true
          const fast = (v as HTMLVideoElement & { fastSeek?: (t: number) => void }).fastSeek
          if (typeof fast === 'function') fast.call(v, t)
          else v.currentTime = t
          lastFrame = f
          settled = current === target
        } else {
          settled = false // not ready or still seeking: try again next frame
        }
      }
      if (!settled) raf = requestAnimationFrame(tick)
    }
    const kick = () => {
      if (!raf) raf = requestAnimationFrame(tick)
    }

    const onSeeked = () => {
      if (!seeking) return
      seeking = false
      if (measuring && seekMs.length < 3) {
        seekMs.push(performance.now() - seekStart)
        if (seeksTooSlow(seekMs)) onStatus('slow')
      }
    }
    // Seeks made while the file is still arriving say nothing about the browser's seeking.
    const onReady = () => {
      measuring = true
      kick()
    }
    const onLoaded = () => kick()
    v.addEventListener('seeked', onSeeked)
    v.addEventListener('canplaythrough', onReady)
    v.addEventListener('loadedmetadata', onLoaded)

    const trigger = ScrollTrigger.create({
      trigger: stage,
      start: 'top top',
      end: 'bottom bottom',
      onUpdate: (self) => {
        progress = self.progress
        kick()
      },
      onRefresh: (self) => {
        progress = self.progress
        kick()
      },
    })

    // Keyboard: a link in a beat that is not showing is brought on stage while it has focus.
    const onFocusIn = (e: FocusEvent) => {
      const beat = (e.target as HTMLElement).closest<HTMLElement>('.pw-beat')
      if (beat?.dataset.i) {
        held = Number(beat.dataset.i)
        kick()
      }
    }
    const onFocusOut = () => {
      held = null
      kick()
    }
    frame.addEventListener('focusin', onFocusIn)
    frame.addEventListener('focusout', onFocusOut)
    kick()

    return () => {
      trigger.kill()
      if (raf) cancelAnimationFrame(raf)
      v.removeEventListener('seeked', onSeeked)
      v.removeEventListener('canplaythrough', onReady)
      v.removeEventListener('loadedmetadata', onLoaded)
      frame.removeEventListener('focusin', onFocusIn)
      frame.removeEventListener('focusout', onFocusOut)
    }
  }, [beats, onStatus])

  return (
    <section ref={outer} data-theme="dark" className="pw-scrub" data-stage={film}>
      <div ref={pin} className="pw-scrub-pin" data-beat="0">
        <FilmFrame native={filmNative(film, small ? 'small' : 'large')} grain={ready}>
          {(report) => (
            <video
              ref={vid}
              className="pw-film-media"
              src={near && ready ? `/landing/${film}-scrub${small ? '-small' : ''}.mp4` : undefined}
              poster={near && ready ? poster : undefined}
              preload={near && ready ? 'auto' : 'none'}
              muted
              playsInline
              aria-hidden="true"
              tabIndex={-1}
              disablePictureInPicture
              disableRemotePlayback
              onError={() => onStatus('failed')}
              onLoadedMetadata={(e) => report(e.currentTarget.videoWidth, e.currentTarget.videoHeight)}
            />
          )}
        </FilmFrame>
        <div aria-hidden="true" className="pw-film-shade" />
        <div className="relative z-10 flex h-full items-center px-4 lg:px-8">
          <IdeaCard idea={idea} index={index} total={total} variant="beats" animate={animate} playOn={outer} />
        </div>
      </div>
    </section>
  )
}
