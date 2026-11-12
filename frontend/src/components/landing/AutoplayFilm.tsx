import { useEffect, useRef, useState } from 'react'
import { gsap } from 'gsap'
import { filmNative } from './film'
import { FilmFrame } from './FilmFrame'
import { audibleFilm, useSound, type FilmId } from './sound'
import './landing.css'

/** Where the film files are (public/landing, made by scripts/landing-video.mjs). */
export const FILM_FILES: Record<FilmId, { stem: string }> = {
  light: { stem: 'light' },
  rim: { stem: 'rim-descent' },
}

/**
 * One of the two films that play by themselves (`light` after the hero, the
 * rim and descent at the end). It is decoration: hidden from assistive
 * technology, and everything it shows is also said in the page's text.
 *
 * Nothing is fetched until the film is a screen away; it plays only while on
 * screen and while the tab is showing; it is muted until the visitor turns
 * sound on, and then it is heard only while it is the one in view, fading in
 * and out over half a second. A film that cannot load says so (`onFail`) and
 * the section falls back to the Moon behind the page.
 *
 * With `still`, nothing plays: the poster is the picture.
 */
export function AutoplayFilm({
  id,
  still,
  small,
  ready,
  onFail,
  onTime,
}: {
  id: FilmId
  still: boolean
  /** The small file (a phone, a small window, a slow connection) rather than the large one. */
  small: boolean
  /** The film files are known to be there (useFilmFiles); until then nothing is asked for. */
  ready: boolean
  onFail: () => void
  /** The film's own clock, a few times a second, for the captions. */
  onTime?: (seconds: number) => void
}) {
  const video = useRef<HTMLVideoElement>(null)
  const [near, setNear] = useState(false)
  const visible = useRef(false)
  const stem = FILM_FILES[id].stem
  const src = `/landing/${stem}${small ? '-small' : ''}.mp4`
  const poster = `/landing/${stem}-poster${small ? '-small' : ''}.jpg`

  const audible = useSound((s) => audibleFilm(s.soundOn, s.inView) === id)

  // A screen away: start to load. On screen: play. Off screen, or the tab hidden: stop.
  useEffect(() => {
    const v = video.current
    if (still || !v) return
    v.muted = true
    const sync = () => {
      const on = visible.current && !document.hidden
      if (on) void v.play().catch(() => {})
      else v.pause()
    }
    const nearIo = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setNear(true)
          nearIo.disconnect()
        }
      },
      { rootMargin: '100% 0px 100% 0px' },
    )
    const viewIo = new IntersectionObserver(
      (entries) => {
        const e = entries[entries.length - 1]
        visible.current = e.intersectionRatio >= 0.15
        useSound.getState().setInView(id, visible.current)
        sync()
      },
      { threshold: [0, 0.15, 0.3] },
    )
    nearIo.observe(v)
    viewIo.observe(v)
    document.addEventListener('visibilitychange', sync)
    return () => {
      nearIo.disconnect()
      viewIo.disconnect()
      document.removeEventListener('visibilitychange', sync)
      useSound.getState().setInView(id, false)
      v.pause()
    }
  }, [id, still])

  // Sound: unmuted only while this is the audible film, over half a second each way.
  useEffect(() => {
    const v = video.current
    if (still || !v) return
    if (audible) {
      v.volume = 0
      v.muted = false
      const t = gsap.to(v, { volume: 1, duration: 0.5, ease: 'none' })
      return () => {
        t.kill()
      }
    }
    if (v.muted) return
    const t = gsap.to(v, {
      volume: 0,
      duration: 0.5,
      ease: 'none',
      onComplete: () => {
        v.muted = true
      },
    })
    return () => {
      t.kill()
      v.muted = true
    }
  }, [audible, still])

  const native = filmNative(id, small ? 'small' : 'large')

  return (
    <FilmFrame native={native} grain={ready}>
      {(report) =>
        still ? (
          <img
            src={ready ? poster : undefined}
            alt=""
            aria-hidden="true"
            className="pw-film-media"
            loading="lazy"
            decoding="async"
            onLoad={(e) => report(e.currentTarget.naturalWidth, e.currentTarget.naturalHeight)}
            onError={onFail}
          />
        ) : (
          <video
            ref={video}
            className="pw-film-media"
            src={near && ready ? src : undefined}
            poster={near && ready ? poster : undefined}
            preload={near && ready ? 'auto' : 'none'}
            muted
            loop
            playsInline
            aria-hidden="true"
            tabIndex={-1}
            disablePictureInPicture
            disableRemotePlayback
            onError={onFail}
            onLoadedMetadata={(e) => report(e.currentTarget.videoWidth, e.currentTarget.videoHeight)}
            // The file arrives after the section may already be on screen: play then.
            onCanPlay={(e) => {
              if (visible.current && !document.hidden) void e.currentTarget.play().catch(() => {})
            }}
            onTimeUpdate={onTime ? (e) => onTime(e.currentTarget.currentTime) : undefined}
          />
        )
      }
    </FilmFrame>
  )
}
