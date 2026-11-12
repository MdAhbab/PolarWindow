import { describe, expect, it } from 'vitest'
import {
  BEATS,
  RIM_CAPTIONS,
  SCRUB_FPS,
  SCRUB_FRAMES,
  approach,
  beatFor,
  captionAt,
  filmFilesReachable,
  filmFrame,
  filmNative,
  filmSize,
  filmMode,
  frameAt,
  frameTime,
  progressToTime,
  seeksTooSlow,
  stageProgress,
} from './film'

describe('scroll progress to the film', () => {
  it('measures how far through a pinned stage the page is', () => {
    // A stage 2250 tall in a window 900 tall travels 1350: at its top edge, half way, at its end.
    expect(stageProgress(0, 2250, 900)).toBe(0)
    expect(stageProgress(-675, 2250, 900)).toBe(0.5)
    expect(stageProgress(-1350, 2250, 900)).toBe(1)
    // Before it arrives and after it has gone, the ends hold.
    expect(stageProgress(400, 2250, 900)).toBe(0)
    expect(stageProgress(-3000, 2250, 900)).toBe(1)
    // A stage no taller than the window never moves.
    expect(stageProgress(-10, 900, 900)).toBe(0)
  })

  it('turns progress into a time in the film, clamped to its length', () => {
    expect(progressToTime(0, 10)).toBe(0)
    expect(progressToTime(0.25, 10)).toBe(2.5)
    expect(progressToTime(1, 10)).toBe(10)
    expect(progressToTime(-1, 10)).toBe(0)
    expect(progressToTime(2, 10)).toBe(10)
    expect(progressToTime(0.5, NaN)).toBe(0)
    expect(progressToTime(NaN, 10)).toBe(0)
  })

  it('finds the frame a time falls on, and holds the last frame at the end', () => {
    expect(SCRUB_FRAMES).toBe(120)
    expect(frameAt(0)).toBe(0)
    expect(frameAt(1 / SCRUB_FPS)).toBe(1)
    expect(frameAt(5)).toBe(60)
    expect(frameAt(10)).toBe(119)
    expect(frameAt(99)).toBe(119)
    expect(frameAt(-3)).toBe(0)
  })

  it('seeks a quarter of the way into the frame so rounding cannot land on the one before', () => {
    for (const f of [0, 1, 59, 119]) expect(frameAt(frameTime(f))).toBe(f)
    expect(frameTime(0)).toBeCloseTo(0.25 / 12)
  })

  it('chases the scroll: a share of the gap each frame, snapping when within half a frame', () => {
    expect(approach(0, 10)).toBeCloseTo(3.5)
    expect(approach(9.99, 10)).toBe(10)
    // Never past the target, in either direction.
    expect(approach(10, 4, 0.5)).toBeGreaterThan(4)
    let t = 0
    for (let i = 0; i < 60; i++) t = approach(t, 7)
    expect(t).toBe(7)
  })
})

describe('the beats of a pinned stage', () => {
  it('shows the first beat to start with and the last at the end', () => {
    expect(beatFor(0, BEATS.shadow)).toBe(0)
    expect(beatFor(1, BEATS.shadow)).toBe(2)
    expect(beatFor(0, BEATS.earth)).toBe(0)
    expect(beatFor(1, BEATS.earth)).toBe(2)
  })

  it('changes at the progress each beat starts, and never has none showing', () => {
    const [, b, c] = BEATS.shadow
    expect(beatFor(b - 0.001, BEATS.shadow)).toBe(0)
    expect(beatFor(b, BEATS.shadow)).toBe(1)
    expect(beatFor(c - 0.001, BEATS.shadow)).toBe(1)
    expect(beatFor(c, BEATS.shadow)).toBe(2)
    for (let p = 0; p <= 1; p += 0.01) expect([0, 1, 2]).toContain(beatFor(p, BEATS.earth))
  })

  it('is monotone: going back goes back', () => {
    let last = 0
    for (let p = 0; p <= 1.0001; p += 0.005) {
      const beat = beatFor(p, BEATS.shadow)
      expect(beat).toBeGreaterThanOrEqual(last)
      last = beat
    }
    expect(beatFor(0.9, BEATS.shadow)).toBe(2)
    expect(beatFor(0.5, BEATS.shadow)).toBe(1)
    expect(beatFor(0.1, BEATS.shadow)).toBe(0)
  })

  it('clamps progress outside the stage', () => {
    expect(beatFor(-4, BEATS.shadow)).toBe(0)
    expect(beatFor(7, BEATS.shadow)).toBe(2)
    expect(beatFor(NaN, BEATS.shadow)).toBe(0)
  })
})

describe('the closing film’s captions', () => {
  it('shows each line in its window by the film’s own clock', () => {
    expect(captionAt(0)).toBe(0)
    expect(captionAt(3.9)).toBe(0)
    expect(captionAt(5)).toBe(1)
    expect(captionAt(11.9)).toBe(1)
    expect(captionAt(13)).toBe(2)
    expect(captionAt(19.2)).toBe(2)
  })

  it('leaves a second of quiet between the lines', () => {
    expect(captionAt(4)).toBeNull()
    expect(captionAt(4.9)).toBeNull()
    expect(captionAt(12)).toBeNull()
    expect(captionAt(12.9)).toBeNull()
  })

  it('shows nothing for a time that is not one', () => {
    expect(captionAt(-1)).toBeNull()
    expect(captionAt(NaN)).toBeNull()
    expect(RIM_CAPTIONS).toHaveLength(3)
  })

  it('reads whatever windows it is given', () => {
    expect(captionAt(2, [{ start: 1, end: 3 }])).toBe(0)
    expect(captionAt(3, [{ start: 1, end: 3 }])).toBeNull()
  })
})

describe('how big a film is shown', () => {
  it('fills the stage up to 1.25 times the film’s own width, with nothing to fade', () => {
    expect(filmFrame(1440, 900, 900, 1280, 720)).toEqual({ w: 1440, h: 900, featherX: false, featherY: false })
    expect(filmFrame(1280, 720, 720, 1280, 720)).toMatchObject({ w: 1280, h: 720, featherX: false, featherY: false })
  })

  it('stops at 1.25 times and centres, fading its edges into the stage', () => {
    expect(filmFrame(1920, 1080, 1080, 1280, 720)).toEqual({ w: 1600, h: 900, featherX: true, featherY: true })
    expect(filmFrame(2560, 1440, 1440, 1280, 720)).toEqual({ w: 1600, h: 900, featherX: true, featherY: true })
  })

  it('fades only the edges that are not the stage’s', () => {
    // Wide and short: the width is capped, the height is the stage's.
    expect(filmFrame(1920, 900, 900, 1280, 720)).toEqual({ w: 1600, h: 900, featherX: true, featherY: false })
    // Narrow and tall: the whole width, but no taller than 1.25 times.
    expect(filmFrame(1440, 1000, 1000, 1280, 720)).toMatchObject({ w: 1440, h: 900, featherX: false, featherY: true })
  })

  it('is never taller than the window, even where the stage is', () => {
    expect(filmFrame(1200, 1500, 800, 1280, 720)).toMatchObject({ w: 1200, h: 800, featherY: true })
  })

  it('follows the film’s own size, so a larger file fills a larger screen with no change', () => {
    expect(filmFrame(2560, 1440, 1440, 1920, 1080)).toEqual({ w: 2400, h: 1350, featherX: true, featherY: true })
    expect(filmFrame(2560, 1440, 1440, 3840, 2160)).toEqual({ w: 2560, h: 1440, featherX: false, featherY: false })
  })

  it('knows the cropped films are 20:9', () => {
    const light = filmNative('light', 'large')
    expect(light.h / light.w).toBeCloseTo(9 / 20)
    expect(filmNative('earth', 'large').h / filmNative('earth', 'large').w).toBeCloseTo(9 / 20)
    expect(filmNative('shadow', 'large').h / filmNative('shadow', 'large').w).toBeCloseTo(9 / 16)
    expect(filmNative('light', 'small').w).toBeLessThan(light.w)
  })

  it('fetches the small file on a phone, on a slow connection and where it would be enough', () => {
    expect(filmSize(390, 3, false)).toBe('small')
    expect(filmSize(1440, 2, true)).toBe('small')
    expect(filmSize(1024, 1, false)).toBe('small')
    expect(filmSize(1280, 1, false)).toBe('small')
    expect(filmSize(1440, 1, false)).toBe('large')
    expect(filmSize(1920, 1, false)).toBe('large')
    expect(filmSize(1440, 2, false)).toBe('large')
    // Never below a tablet's width, however sharp the screen.
    expect(filmSize(767, 4, false)).toBe('small')
    expect(filmSize(1440, 0, false)).toBe('large')
  })
})

describe('how the films are shown', () => {
  it('scrubs and plays on a wide screen with nothing asked against it', () => {
    expect(filmMode({ reduced: false, phone: false, saveData: false })).toEqual({ scrub: true, autoplay: true })
  })

  it('turns every film into a still for reduced motion and for data saver', () => {
    expect(filmMode({ reduced: true, phone: false, saveData: false })).toEqual({ scrub: false, autoplay: false })
    expect(filmMode({ reduced: false, phone: false, saveData: true })).toEqual({ scrub: false, autoplay: false })
    expect(filmMode({ reduced: true, phone: true, saveData: true })).toEqual({ scrub: false, autoplay: false })
  })

  it('does not pin or scrub on a phone, which may still play the two films', () => {
    expect(filmMode({ reduced: false, phone: true, saveData: false })).toEqual({ scrub: false, autoplay: true })
    expect(filmMode({ reduced: false, phone: true, saveData: true })).toEqual({ scrub: false, autoplay: false })
  })

  it('treats the film folder as there only when a file answers as a file', () => {
    expect(filmFilesReachable(true, 'image/jpeg')).toBe(true)
    expect(filmFilesReachable(true, 'IMAGE/JPEG')).toBe(true)
    // A missing file answered by the app's own page (a single-page app's fallback), or by an error, or by nothing.
    expect(filmFilesReachable(true, 'text/html; charset=utf-8')).toBe(false)
    expect(filmFilesReachable(true, null)).toBe(false)
    expect(filmFilesReachable(false, 'image/jpeg')).toBe(false)
  })

  it('gives up scrubbing only when the first three seeks are all slow', () => {
    expect(seeksTooSlow([130, 140, 150])).toBe(true)
    expect(seeksTooSlow([130, 140, 100])).toBe(false)
    expect(seeksTooSlow([200, 300])).toBe(false)
    expect(seeksTooSlow([])).toBe(false)
    expect(seeksTooSlow([10, 10, 10, 500, 500, 500])).toBe(false)
    expect(seeksTooSlow([121, 121, 121])).toBe(true)
    expect(seeksTooSlow([120, 121, 121])).toBe(false)
  })
})
