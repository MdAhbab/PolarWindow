/**
 * The front page's films, as arithmetic: no DOM in here, so each rule can be
 * tested on its own. The components only read numbers off the page and call
 * these.
 */

/** The scroll-driven files are 120 frames at 12 per second (scripts/landing-video.mjs). */
export const SCRUB_FPS = 12
export const SCRUB_FRAMES = 120

export const clamp01 = (n: number): number => (Number.isFinite(n) ? Math.min(1, Math.max(0, n)) : 0)

/** How far through a pinned stage the page is (0 to 1), from where its top and bottom are in the window. */
export function stageProgress(top: number, height: number, viewport: number): number {
  const travel = height - viewport
  return travel <= 0 ? 0 : clamp01(-top / travel)
}

/** Scroll progress to a time in the film, in seconds. */
export function progressToTime(progress: number, duration: number): number {
  return clamp01(progress) * (Number.isFinite(duration) && duration > 0 ? duration : 0)
}

/** The frame a time falls on; the last frame holds at the end. */
export function frameAt(time: number, frames = SCRUB_FRAMES, fps = SCRUB_FPS): number {
  return Math.min(frames - 1, Math.max(0, Math.floor(time * fps + 1e-6)))
}

/**
 * Where to seek to show a frame: a quarter of the way into it, so a time that
 * rounds a hair low still lands on this frame and not the one before.
 */
export function frameTime(frame: number, fps = SCRUB_FPS): number {
  return (frame + 0.25) / fps
}

/**
 * Chasing the scroll: each animation frame the film's time moves a share of
 * the way to where the scroll says it should be, and snaps once it is within
 * half a frame. Never overshoots, so a fast flick and a slow drag both settle.
 */
export function approach(current: number, target: number, share = 0.35, fps = SCRUB_FPS): number {
  const d = target - current
  return Math.abs(d) <= 0.5 / fps ? target : current + d * share
}

/**
 * The beats of a pinned stage: the progress each one starts at, ascending. A
 * beat holds until the next starts, so there is no moment with none showing.
 * Set against the real frames (see landing-video notes in L1.md):
 *  - shadow: the lander is lit until 0.30, the shadow is across it from 0.37
 *    to 0.57, and the light is back by 0.63;
 *  - earth: Earth stands clear of the hill until about 0.45, then the hill
 *    covers more of it each moment (a quarter of it gone by 0.7, most by 0.9).
 */
export const BEATS = {
  shadow: [0, 0.35, 0.65],
  earth: [0, 0.42, 0.85],
} as const

export type Beats = readonly number[]

/** Which beat a progress falls in. */
export function beatFor(progress: number, starts: Beats): number {
  const p = clamp01(progress)
  for (let i = starts.length - 1; i > 0; i--) if (p >= starts[i]) return i
  return 0
}

/**
 * The captions of the closing film, by the film's own clock. A second of
 * quiet between lines, so each one is read as a line and not as a blur.
 * `end` is exclusive; the last one holds to the end of the loop.
 */
export interface CaptionWindow {
  start: number
  end: number
}
export const RIM_CAPTIONS: readonly CaptionWindow[] = [
  { start: 0, end: 4 },
  { start: 5, end: 12 },
  { start: 13, end: Infinity },
]

/** The caption showing at a time in the film, or null in the gaps. */
export function captionAt(time: number, windows: readonly CaptionWindow[] = RIM_CAPTIONS): number | null {
  if (!Number.isFinite(time) || time < 0) return null
  const i = windows.findIndex((w) => time >= w.start && time < w.end)
  return i < 0 ? null : i
}

/**
 * How the films are shown, from what the visitor's device and settings say.
 * Reduced motion (the system's or the app's own) and data saver turn every
 * film into a still behind its text; a phone gets no pinning and no scrubbing
 * but may play the two films that play by themselves.
 */
export interface FilmEnv {
  reduced: boolean
  phone: boolean
  saveData: boolean
}
export interface FilmMode {
  /** The pinned, scroll-driven stages. */
  scrub: boolean
  /** The two films that play by themselves. */
  autoplay: boolean
}
export function filmMode({ reduced, phone, saveData }: FilmEnv): FilmMode {
  return { scrub: !reduced && !saveData && !phone, autoplay: !reduced && !saveData }
}

/** A film file answered as a file: a 2xx that is an image, not the app's own page standing in for a missing one. */
export function filmFilesReachable(ok: boolean, contentType: string | null): boolean {
  return ok && /^image\//i.test(contentType ?? '')
}

/**
 * The films are 1280 wide (960 for a phone) and never shown more than 1.25 times as wide: stretched
 * further they are soft, and on a big screen a clean file looks better small and centred than large
 * and blurred. Beyond that size the picture sits in the middle of its stage, which is the page's canvas
 * colour, and its edges fade into it (landing.css, .pw-film-frame).
 */
export const FILM_MAX_SCALE = 1.25
/** How much of the picture's own width and height each feathered edge takes. */
export const FILM_FEATHER = 0.08

/**
 * Each film ships in two sizes (scripts/landing-video.mjs): large is the default, small is for phones, small
 * windows and slow connections. These are the widths they are made at, used until the file has loaded and
 * said what it really is (`videoWidth`): the 1.25 times cap follows the real size, so a larger file
 * fills a larger screen with no change here.
 */
export type FilmSize = 'large' | 'small'
export const FILM_WIDTH: Record<FilmSize, number> = { large: 1920, small: 1280 }

/** Height over width of each film as shipped: light and earth are cropped of their black bars to 20:9. */
const FILM_ASPECT = { light: 576 / 1280, shadow: 720 / 1280, earth: 576 / 1280, rim: 720 / 1280 } as const
export type FilmName = keyof typeof FILM_ASPECT

export function filmNative(name: FilmName, size: FilmSize): { w: number; h: number } {
  const w = FILM_WIDTH[size]
  return { w, h: Math.round(w * FILM_ASPECT[name]) }
}

/**
 * Which size to fetch: the small one on a phone, on a slow connection, or where the window times the pixel
 * ratio is no more than a little over the small file's own width; otherwise the large one.
 */
export function filmSize(viewportW: number, pixelRatio: number, slow: boolean): FilmSize {
  if (slow || viewportW < 768) return 'small'
  return viewportW * (pixelRatio || 1) > 1.1 * FILM_WIDTH.small ? 'large' : 'small'
}

export interface FilmFrame {
  w: number
  h: number
  /** The picture does not reach the stage's left and right edges, so those two fade. */
  featherX: boolean
  /** The same for its top and bottom. */
  featherY: boolean
}

/**
 * The picture's box in its stage: as much of the stage as it can have without being shown larger than
 * FILM_MAX_SCALE times its own size, and no taller than the window. Where it fills the stage it has no
 * edge to fade there.
 */
export function filmFrame(
  stageW: number,
  stageH: number,
  viewportH: number,
  nativeW: number,
  nativeH: number,
  maxScale = FILM_MAX_SCALE,
): FilmFrame {
  const w = Math.min(stageW, maxScale * nativeW)
  const h = Math.min(stageH, viewportH, maxScale * nativeH)
  return { w, h, featherX: stageW - w > 0.5, featherY: stageH - h > 0.5 }
}

/**
 * A seek is too slow to scrub with when the first three each take longer than
 * the limit; then the stage stops scrubbing and the card sits over the poster.
 */
export const SEEK_LIMIT_MS = 120
export function seeksTooSlow(durations: readonly number[], limit = SEEK_LIMIT_MS): boolean {
  return durations.length >= 3 && durations.slice(0, 3).every((d) => d > limit)
}
