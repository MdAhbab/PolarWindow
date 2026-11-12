#!/usr/bin/env node
/**
 * Builds the front page's film files into public/landing/.
 *
 *   FFMPEG=/path/to/ffmpeg node scripts/landing-video.mjs [folder holding the five clips]
 *   ONLY=shadow OUT=/some/folder node scripts/landing-video.mjs      (one film, elsewhere: for trying)
 *
 * Sources: the owner's five clips of 13 November, read straight from the workspace root (beside polarwindow/,
 * or the folder given as the argument) and never changed: light.mp4, shadow.mp4, earth.mp4, rim.mp4 and
 * descent.mp4. All are 1920x1080, 24 fps, H.264 with stereo AAC (the music is part of the clip), with no
 * black bars. There are no masters and no cropping: 1920 is the page's large size, so nothing is upscaled
 * (the script refuses a source narrower than the size asked for), and the small size is scaled down.
 *
 * Each film ships in two sizes, chosen on the page by what the screen can show (components/landing/film.ts,
 * filmSize): LARGE is 1920 wide (the default) and SMALL is 1280 wide (phones, small windows, slow
 * connections). Names: <film>.mp4 and <film>-small.mp4, <film>-poster.jpg and <film>-poster-small.jpg.
 *
 *   light.mp4                  plays by itself: the whole 12 s clip, its last 0.75 s cross-faded into its first,
 *                              so the loop has no seam; the audio is levelled to -24 LUFS
 *   rim-descent.mp4            plays by itself: rim then descent joined as one loop (about 25 s). The two are
 *                              cross-faded where they meet and again where the loop turns over (descent's end
 *                              into rim's start), 1 s each, in picture and in sound. Each clip's sound is
 *                              levelled to -24 LUFS before joining, so the join does not jump, and the file is
 *                              checked afterwards. The film starts on a clean frame of rim, 1 s in.
 *   shadow-scrub.mp4,          scroll drives them: every frame a keyframe (a seek costs about the same anywhere),
 *   earth-scrub.mp4            120 frames at 12 per second (every second source frame of 10 s), no audio.
 *                              earth is its whole 10 s. shadow is 12 s: its first 10 s are used, so the hill's shadow
 *                              (4.8 to 6 s) falls in the middle; the last 2 s, the Sun high and still, are left out.
 *   <film>-poster.jpg          a still, cut from the original clip (not from an encode) at the frame the film
 *                              starts on, JPEG at -q:v 2 (about quality 95), converted to RGB and back with the
 *                              BT.601 matrix a JPEG is read with, so its colours match the film's
 *
 * Quality: H.264 high profile, -preset slow, -tune film, constant quality. The wanted CRF per film is
 * below; where the file comes out over its size cap the CRF is raised one or two steps at a time until it
 * fits (budget: no file over 10 MB, the folder under 45 MB; the caps below plus the posters stay inside it,
 * and the script checks the folder when it has built everything).
 * Colour: the clips are tagged BT.601 for the matrix (smpte170m) with the sRGB transfer and BT.709 primaries,
 * which is what a browser follows. Their matrix is converted to BT.709 (transfer and primaries kept), dithered
 * so the dark sky does not band, and the films are tagged BT.709/sRGB, so the picture on the page is the clip's.
 */
import { spawnSync } from 'node:child_process'
import { mkdirSync, statSync, existsSync, readdirSync, rmSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const REPO = resolve(here, '..', '..')
const FFMPEG = process.env.FFMPEG || 'ffmpeg'
const FFPROBE = process.env.FFPROBE || FFMPEG.replace(/ffmpeg(\.exe)?$/i, 'ffprobe$1')
const CLIPS = resolve(process.argv[2] || join(REPO, '..'))
const OUT = resolve(process.env.OUT || join(here, '..', 'public', 'landing'))
const ONLY = process.env.ONLY
const TARGET_LUFS = -24
const FPS = 24
/** The scroll-driven films: 120 frames at 12 per second (SCRUB_FRAMES and SCRUB_FPS in components/landing/film.ts). */
const SCRUB_FRAMES = 120
const SCRUB_FPS = 12
const BUDGET = { file: 10, folder: 45 } // MB

/**
 * Where each film's clips, size, cap and wanted quality are. `parts` are the clips in the order they play (`secs`
 * is what the clip is meant to be, checked against the file). `fade` is the cross-fade, in seconds, of a loop.
 * `from` is where a scroll-driven film starts in its clip, in seconds. Caps in MB: the four large and four small
 * files, the eight posters (about 1.7 MB) and the grain come to under the folder's 45.
 */
const films = {
  light: { parts: [{ clip: 'light.mp4', secs: 12 }], loop: 'light', fade: 0.75, crf: 21, caps: { large: 6.5, small: 2.2 } },
  rim: {
    parts: [
      { clip: 'rim.mp4', secs: 12 },
      { clip: 'descent.mp4', secs: 14.9 },
    ],
    loop: 'rim-descent',
    fade: 1,
    crf: 22,
    caps: { large: 9.5, small: 3.3 },
  },
  shadow: { parts: [{ clip: 'shadow.mp4', secs: 12 }], scrub: 'shadow-scrub', from: 0, crf: 27, caps: { large: 8.4, small: 2.8 } },
  earth: { parts: [{ clip: 'earth.mp4', secs: 10 }], scrub: 'earth-scrub', from: 0, crf: 27, caps: { large: 8.4, small: 2.8 } },
}
// LARGE=1280 SMALL=960 builds a quicker, smaller pair for trying a change.
const SIZES = { large: Number(process.env.LARGE) || 1920, small: Number(process.env.SMALL) || 1280 }

function ffmpeg(args, quiet = true) {
  const full = ['-y', '-hide_banner', '-loglevel', quiet ? 'error' : 'info', ...args]
  console.log(`\n$ ffmpeg ${full.map((a) => (/[\s;\[\]()|]/.test(a) ? JSON.stringify(a) : a)).join(' ')}`)
  const r = spawnSync(FFMPEG, full, { encoding: 'utf8', maxBuffer: 1 << 28 })
  if (r.status !== 0) throw new Error(`ffmpeg failed (${r.status}):\n${(r.stderr || '').slice(-2000)}`)
}

/** What a source is: its picture size, frame count and colour tags. */
function probe(file) {
  const r = spawnSync(
    FFPROBE,
    ['-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,nb_frames,duration,r_frame_rate,color_space,color_transfer,color_primaries', '-of', 'json', file],
    { encoding: 'utf8' },
  )
  let s
  try {
    s = JSON.parse(r.stdout).streams[0]
  } catch {
    throw new Error(`cannot read ${file}`)
  }
  const [n, d] = String(s.r_frame_rate).split('/').map(Number)
  const frames = Number(s.nb_frames) || Math.round(Number(s.duration) * FPS)
  return {
    file,
    w: s.width,
    h: s.height,
    fps: d ? n / d : n,
    frames,
    matrix: s.color_space || 'unknown',
    trc: s.color_transfer || 'unknown',
    primaries: s.color_primaries || 'unknown',
  }
}

/** Integrated loudness (LUFS) and true peak of a file's audio. */
function lufs(file) {
  const r = spawnSync(FFMPEG, ['-hide_banner', '-nostats', '-i', file, '-vn', '-af', 'ebur128=peak=true', '-f', 'null', '-'], { encoding: 'utf8', maxBuffer: 1 << 28 })
  const m = /Integrated loudness:\s+I:\s+(-?[\d.]+) LUFS/.exec(r.stderr)
  const p = /True peak:\s+Peak:\s+(-?[\d.]+) dBFS/.exec(r.stderr)
  if (!m) throw new Error(`no loudness for ${file}`)
  return { lufs: Number(m[1]), peak: p ? Number(p[1]) : NaN }
}

const mb = (f) => statSync(f).size / 1e6

/** A source, probed and checked: the size asked for must not be an upscale, the rate must be ours, the length the one meant. */
function open(clip, secs) {
  const file = join(CLIPS, clip)
  if (!existsSync(file)) throw new Error(`missing ${file}`)
  const src = probe(file)
  if (src.w < SIZES.large) throw new Error(`${clip} is ${src.w} wide: that would be an upscale to ${SIZES.large}`)
  if (Math.abs(src.fps - FPS) > 0.01) throw new Error(`${clip} runs at ${src.fps} fps, not ${FPS}`)
  if (Math.abs(src.frames / FPS - secs) > 0.15) throw new Error(`${clip} is ${(src.frames / FPS).toFixed(2)} s, not about ${secs} s`)
  for (const k of ['matrix', 'trc', 'primaries']) if (src[k] === 'unknown') throw new Error(`${clip} has no colour ${k} tag: say what it is before encoding`)
  return src
}

/**
 * The picture filters for a source: the colour matrix to BT.709 where it is not that already (the clips are
 * tagged smpte170m, that is BT.601), with the transfer made sRGB and the primaries BT.709 (as tagged, so
 * nothing but the matrix changes), and the scale (down only; `open` refuses an upscale).
 */
function picture(src, width) {
  const colour =
    src.matrix === 'bt709'
      ? ''
      : `colorspace=space=bt709:trc=iec61966-2-1:primaries=bt709:ispace=${src.matrix}:itrc=${src.trc}:iprimaries=${src.primaries}` +
        `:fast=${src.trc === 'iec61966-2-1' && src.primaries === 'bt709' ? 1 : 0}:dither=fsb,`
  const scale = width === src.w ? '' : `scale=${width}:-2:flags=lanczos+accurate_rnd+full_chroma_int,`
  return `${colour}${scale}`.replace(/,$/, '') || 'null'
}

const tags = ['-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'iec61966-2-1', '-color_range', 'tv']
const x264 = (w, extra = '') => [
  '-c:v', 'libx264', '-preset', 'slow', '-tune', 'film', '-profile:v', 'high', '-level:v', w > 1280 ? '5.0' : '4.2',
  '-pix_fmt', 'yuv420p', '-x264-params', `aq-mode=3:aq-strength=1.0${extra}`,
]

/** Re-encodes with a higher CRF until the file is inside its cap. Returns the CRF used. */
function fit(encode, file, crf, capMB) {
  for (let tries = 0; tries < 10; tries++) {
    encode(crf)
    const size = mb(file)
    console.log(`  ${file.split(/[\\/]/).pop()}: CRF ${crf}, ${size.toFixed(2)} MB (cap ${capMB})`)
    if (size <= capMB) return crf
    crf += size > capMB * 1.3 ? 2 : 1
  }
  throw new Error(`${file} will not fit ${capMB} MB`)
}

/**
 * The loop version of one clip or of several played in turn. Every clip is cut into its head (the first `fade`
 * seconds), its middle and its tail (the last `fade` seconds); each tail is cross-faded into the next clip's
 * head, picture and sound, and the last clip's tail into the first clip's head. The file is
 *
 *     middle(0)  fade(tail 0, head 1)  middle(1)  fade(tail 1, head 2)  ...  middle(last)  fade(tail last, head 0)
 *
 * so it starts on a clean frame of the first clip and, played over and over, each end meets its start without a
 * cut. With one clip this is the plain loop; its length is the clips' together less one fade for each join.
 * `gains` (dB, one per clip) level the sound; the limiter only guards the peaks.
 */
function loopGraph(parts, film, width, gains) {
  const k = parts.length
  const F = Math.round(film.fade * FPS) // fade length in frames, and so in exact seconds below
  const fs = F / FPS
  const v = []
  const a = []
  parts.forEach((p, i) => {
    const N = p.frames
    const dur = N / FPS
    v.push(`[${i}:v]${picture(p, width)},fps=${FPS},split=3[vh${i}][vm${i}][vt${i}]`)
    v.push(`[vh${i}]trim=start_frame=0:end_frame=${F},setpts=PTS-STARTPTS,settb=1/${FPS}[h${i}]`)
    v.push(`[vm${i}]trim=start_frame=${F}:end_frame=${N - F},setpts=PTS-STARTPTS,settb=1/${FPS}[m${i}]`)
    v.push(`[vt${i}]trim=start_frame=${N - F}:end_frame=${N},setpts=PTS-STARTPTS,settb=1/${FPS}[t${i}]`)
    a.push(`[${i}:a]aformat=sample_rates=48000:channel_layouts=stereo,apad,atrim=0:${dur.toFixed(6)},asetpts=PTS-STARTPTS,volume=${gains[i].toFixed(2)}dB,asplit=3[ax${i}][ay${i}][az${i}]`)
    a.push(`[ax${i}]atrim=0:${fs},asetpts=PTS-STARTPTS[ah${i}]`)
    a.push(`[ay${i}]atrim=${fs}:${(dur - fs).toFixed(6)},asetpts=PTS-STARTPTS[am${i}]`)
    a.push(`[az${i}]atrim=${(dur - fs).toFixed(6)}:${dur.toFixed(6)},asetpts=PTS-STARTPTS[at${i}]`)
  })
  const vOrder = []
  const aOrder = []
  for (let i = 0; i < k; i++) {
    const j = (i + 1) % k
    v.push(`[t${i}][h${j}]xfade=transition=fade:duration=${fs}:offset=0,settb=1/${FPS}[x${i}]`)
    a.push(`[at${i}]afade=t=out:st=0:d=${fs}:curve=qsin[atf${i}]`)
    a.push(`[ah${j}]afade=t=in:st=0:d=${fs}:curve=qsin[ahf${i}]`)
    a.push(`[atf${i}][ahf${i}]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0[xa${i}]`)
    vOrder.push(`[m${i}]`, `[x${i}]`)
    aOrder.push(`[am${i}]`, `[xa${i}]`)
  }
  v.push(`${vOrder.join('')}concat=n=${2 * k}:v=1:a=0,format=yuv420p[vout]`)
  a.push(`${aOrder.join('')}concat=n=${2 * k}:v=0:a=1,alimiter=limit=0.89:level=0[aout]`)
  return { video: v.join(';'), audio: a.join(';'), frames: parts.reduce((n, p) => n + p.frames, 0) - k * F }
}

/** Where the sound of a loop lands: its audio alone, rendered to a scratch file and measured, so the video is encoded once. */
function levelled(parts, film, scratch) {
  const gains = parts.map((p) => TARGET_LUFS - lufs(p.file).lufs)
  const wav = join(scratch, 'level.wav')
  for (let attempt = 0; attempt < 3; attempt++) {
    const g = loopGraph(parts, film, SIZES.small, gains)
    ffmpeg([...parts.flatMap((p) => ['-i', p.file]), '-filter_complex', g.audio, '-map', '[aout]', '-c:a', 'pcm_f32le', wav])
    const got = lufs(wav)
    console.log(`  loop sound: ${got.lufs} LUFS, peak ${got.peak} dBFS (gains ${gains.map((x) => x.toFixed(2)).join(', ')} dB)`)
    if (Math.abs(got.lufs - TARGET_LUFS) <= 0.15) break
    for (let i = 0; i < gains.length; i++) gains[i] += TARGET_LUFS - got.lufs
  }
  return gains
}

function loop(parts, film, width, gains, kbps, file) {
  const g = loopGraph(parts, film, width, gains)
  return (crf) =>
    ffmpeg([
      ...parts.flatMap((p) => ['-i', p.file]), '-filter_complex', `${g.video};${g.audio}`, '-map', '[vout]', '-map', '[aout]',
      ...x264(width, ':keyint=120:min-keyint=24'), '-crf', String(crf), ...tags,
      '-c:a', 'aac', '-b:a', `${kbps}k`, '-ac', '2', '-ar', '48000', '-map_metadata', '-1', '-movflags', '+faststart', file,
    ])
}

/** The scroll-driven version: every other frame of 10 s, all keyframes, no sound. */
function scrub(src, film, width, file) {
  const step = FPS / SCRUB_FPS
  const start = Math.round((film.from || 0) * FPS)
  return (crf) =>
    ffmpeg([
      '-i', src.file,
      '-vf', `trim=start_frame=${start}:end_frame=${start + SCRUB_FRAMES * step},setpts=PTS-STARTPTS,select='not(mod(n,${step}))',setpts=N/${SCRUB_FPS}/TB,${picture(src, width)},format=yuv420p`,
      '-r', String(SCRUB_FPS), ...x264(width), '-crf', String(crf), '-g', '1', '-keyint_min', '1', ...tags,
      '-an', '-map_metadata', '-1', '-movflags', '+faststart', file,
    ])
}

/**
 * A still, from the source at the frame the film starts on. A JPEG is read with the BT.601 matrix, so the
 * picture goes to RGB with the source's own matrix (from its tag) and back to YCbCr with BT.601, full range.
 */
function poster(src, name, width, at) {
  ffmpeg([
    '-ss', at.toFixed(4), '-i', src.file, '-frames:v', '1',
    '-vf',
    `scale=${width}:-2:flags=lanczos+accurate_rnd+full_chroma_int,format=rgb24,` +
      `scale=out_color_matrix=bt601:out_range=pc:flags=accurate_rnd+full_chroma_int,format=yuvj420p`,
    '-q:v', '2', join(OUT, name),
  ])
}

function frameCount(file) {
  return probe(file).frames
}

mkdirSync(OUT, { recursive: true })
const scratch = mkdtempSync(join(tmpdir(), 'landing-video-'))
const report = []
try {
  for (const [key, film] of Object.entries(films)) {
    if (ONLY && ONLY !== key) continue
    const parts = film.parts.map((p) => open(p.clip, p.secs))
    console.log(`\n== ${key}: ${parts.map((p) => `${p.file} (${p.w}x${p.h}, ${p.frames} frames, ${p.matrix})`).join(' + ')}`)

    const stem = film.loop || film.scrub
    const startAt = film.loop ? Math.round(film.fade * FPS) / FPS : film.from || 0 // the loop starts after the first clip's fade-in
    const gains = film.loop ? levelled(parts, film, scratch) : []
    for (const size of ['large', 'small']) {
      const width = SIZES[size]
      const suffix = size === 'small' ? '-small' : ''
      const file = join(OUT, `${stem}${suffix}.mp4`)
      const base = film.crf + (size === 'small' ? 2 : 0)
      let crf
      if (film.loop) {
        crf = fit(loop(parts, film, width, gains, size === 'small' ? 96 : 128, file), file, base, film.caps[size])
        const got = lufs(file)
        console.log(`  ${stem}${suffix}: ${got.lufs} LUFS, peak ${got.peak} dBFS, ${frameCount(file)} frames (expected ${loopGraph(parts, film, width, gains).frames})`)
      } else {
        crf = fit(scrub(parts[0], film, width, file), file, base, film.caps[size])
        const n = frameCount(file)
        if (n !== SCRUB_FRAMES) throw new Error(`${file} has ${n} frames, not ${SCRUB_FRAMES}`)
      }
      poster(parts[0], `${stem.replace('-scrub', '')}-poster${suffix}.jpg`, width, startAt)
      report.push([`${stem}${suffix}.mp4`, width, crf])
    }
  }
} finally {
  rmSync(scratch, { recursive: true, force: true })
}

console.log('\nWrote:')
let total = 0
let biggest = 0
for (const f of readdirSync(OUT).sort()) {
  const p = join(OUT, f)
  total += statSync(p).size
  biggest = Math.max(biggest, mb(p))
  console.log(`  ${f.padEnd(30)} ${mb(p).toFixed(2)} MB`)
}
console.log(`  ${'total'.padEnd(30)} ${(total / 1e6).toFixed(2)} MB`)
console.log('CRF used:', report.map(([f, w, c]) => `${f} ${w}px crf ${c}`).join('; '))
if (!ONLY && (biggest > BUDGET.file || total / 1e6 > BUDGET.folder)) {
  console.error(`OVER BUDGET: largest ${biggest.toFixed(2)} MB (limit ${BUDGET.file}), folder ${(total / 1e6).toFixed(2)} MB (limit ${BUDGET.folder})`)
  process.exitCode = 1
}
