#!/usr/bin/env node
/**
 * Builds the front page's film files into public/landing/.
 *
 *   FFMPEG=/path/to/ffmpeg node scripts/landing-video.mjs [folder of masters]
 *   ONLY=shadow OUT=/some/folder node scripts/landing-video.mjs      (one film, elsewhere: for trying)
 *
 * Sources: the owner's four clips (1280x720, 24 fps, H.264, stereo AAC; light, shadow and earth 10 s,
 * "rin and descent" 20 s) were upscaled locally to 2560 wide masters, which are what the page's
 * files come from: video/up/{shadow,earth,light,rim-descent}-2560.mp4 under the audit folder (light
 * and earth already cropped of their black bars: 2560x1152; each master is a 50/50 blend of the upscale and the
 * original clip, lightly sharpened; the rim film's is rim-descent-2560.blend.mp4). The masters are never shipped. Where a master
 * is missing the original clip is used instead (and cropped here), so the script always builds
 * something; the originals in the workspace root are only ever read.
 *
 * Each film ships in two sizes, chosen on the page by what the screen can show (components/landing/film.ts,
 * filmSize): LARGE is 1920 wide (the default) and SMALL is 1280 wide (phones, small windows, slow
 * connections). Names: <film>.mp4 and <film>-small.mp4, <film>-poster.jpg and <film>-poster-small.jpg.
 *
 *   light.mp4, rim-descent.mp4            play by themselves: the last 0.75 s cross-faded into the first so the
 *                                         loop has no seam, audio levelled to -24 LUFS so the two match
 *   shadow-scrub.mp4, earth-scrub.mp4     scroll drives them: every frame a keyframe (a seek costs about the
 *                                         same anywhere), 120 frames (every second source frame, 12 per second),
 *                                         no audio
 *   <film>-poster.jpg                     a still, cut from the master (not from an encode) at the frame the
 *                                         film starts on, JPEG at -q:v 2 (about quality 95)
 *
 * Quality: H.264 high profile, -preset slow, -tune film, constant quality. The wanted CRF per film is
 * below; where the file comes out over its size cap the CRF is raised one or two steps at a time until it
 * fits (budget: no file over 10 MB, the folder under 45 MB; the caps below sum to the folder's budget).
 * Colour: an original clip (tagged BT.601) has its matrix converted to BT.709 (sRGB transfer), dithered, so
 * the dark sky does not band; a master is already BT.709 and is left alone.
 */
import { spawnSync } from 'node:child_process'
import { mkdirSync, statSync, existsSync, readdirSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const REPO = resolve(here, '..', '..')
const FFMPEG = process.env.FFMPEG || 'ffmpeg'
const FFPROBE = process.env.FFPROBE || FFMPEG.replace(/ffmpeg(\.exe)?$/i, 'ffprobe$1')
const MASTERS = resolve(process.argv[2] || join(REPO, '.local', 'review', 'audit-2026-11-12', 'video', 'up'))
const ORIGINALS = resolve(REPO, '..')
const OUT = resolve(process.env.OUT || join(here, '..', 'public', 'landing'))
const ONLY = process.env.ONLY
const TARGET_LUFS = -24
const FPS = 24
const FADE_S = 0.75

/** Where each film's size, cap and wanted quality are. Caps in MB: 4 large + 4 small + posters + grain come to under 45. */
const films = {
  light: { master: 'light-2560.mp4', original: 'light.mp4', secs: 10, crop: true, loop: 'light', crf: 20, caps: { large: 7, small: 2 } },
  rim: { master: 'rim-descent-2560.blend.mp4', original: 'rin and descent.mp4', secs: 20, crop: false, loop: 'rim-descent', crf: 20, caps: { large: 9.9, small: 3.5 } },
  shadow: { master: 'shadow-2560.mp4', original: 'shadow.mp4', secs: 10, crop: false, scrub: 'shadow-scrub', crf: 21, caps: { large: 9, small: 3 } },
  earth: { master: 'earth-2560.mp4', original: 'earth.mp4', secs: 10, crop: true, scrub: 'earth-scrub', crf: 21, caps: { large: 9, small: 3 } },
}
// LARGE=1280 SMALL=960 builds the interim pair from an original clip, when no master is there yet.
const SIZES = { large: Number(process.env.LARGE) || 1920, small: Number(process.env.SMALL) || 1280 }

function ffmpeg(args, quiet = true) {
  const full = ['-y', '-hide_banner', '-loglevel', quiet ? 'error' : 'info', ...args]
  console.log(`\n$ ffmpeg ${full.map((a) => (/[\s;\[\]()|]/.test(a) ? JSON.stringify(a) : a)).join(' ')}`)
  const r = spawnSync(FFMPEG, full, { encoding: 'utf8', maxBuffer: 1 << 28 })
  if (r.status !== 0) throw new Error(`ffmpeg failed (${r.status}):\n${(r.stderr || '').slice(-2000)}`)
}

/** What the source is: its picture size and colour matrix. */
function probe(file) {
  const r = spawnSync(FFPROBE, ['-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,color_space', '-of', 'json', file], { encoding: 'utf8' })
  try {
    const s = JSON.parse(r.stdout).streams[0]
    return { w: s.width, h: s.height, matrix: s.color_space || 'unknown' }
  } catch {
    return { w: 0, h: 0, matrix: 'unknown' }
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

/**
 * The picture filters for a source: the crop (an original with bars, 20:9), the colour matrix where it is
 * the clips' BT.601 one, and the scale (down from a master; from an original this is an upscale, which is
 * only what the script falls back to when there is no master).
 */
function picture(src, film, width) {
  const info = probe(src.file)
  const crop = src.original && film.crop ? 'crop=1280:576:0:72,' : ''
  // The clips are tagged BT.601 (smpte170m); the masters were made from them and are already BT.709 in the
  // pixels (checked: the same colours as the converted clip) but carry no matrix tag, so they are left alone.
  const colour = src.original && info.matrix !== 'bt709' ? 'colorspace=space=bt709:trc=iec61966-2-1:primaries=bt709:fast=1:dither=fsb,' : ''
  const nativeW = src.original ? 1280 : info.w
  const scale = width === nativeW ? '' : `scale=${width}:-2:flags=lanczos+accurate_rnd+full_chroma_int,`
  return `${crop}${colour}${scale}`.replace(/,$/, '') || 'null'
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
 * The loop version: the last FADE_S of the clip is cross-faded over its first FADE_S, in picture and sound,
 * and the clip then plays from the end of the fade to the start of the tail. Played over and over, the end
 * meets the start without a cut. `gainDb` levels the sound.
 */
function loop(src, film, width, gainDb, kbps, file) {
  const frames = film.secs * FPS
  const F = Math.round(FADE_S * FPS)
  const fc = [
    `[0:v]${picture(src, film, width)},split=3[v1][v2][v3]`,
    `[v1]trim=start_frame=0:end_frame=${F},setpts=PTS-STARTPTS[head]`,
    `[v2]trim=start_frame=${F}:end_frame=${frames - F},setpts=PTS-STARTPTS[mid]`,
    `[v3]trim=start_frame=${frames - F}:end_frame=${frames},setpts=PTS-STARTPTS[tail]`,
    `[tail][head]xfade=transition=fade:duration=${FADE_S}:offset=0[xf]`,
    `[xf][mid]concat=n=2:v=1:a=0,format=yuv420p[vout]`,
    `[0:a]asplit=3[a1][a2][a3]`,
    `[a1]atrim=0:${FADE_S},asetpts=PTS-STARTPTS[ah]`,
    `[a2]atrim=${FADE_S}:${film.secs - FADE_S},asetpts=PTS-STARTPTS[am]`,
    `[a3]atrim=${film.secs - FADE_S}:${film.secs},asetpts=PTS-STARTPTS[at]`,
    `[at]afade=t=out:st=0:d=${FADE_S}:curve=qsin[atf]`,
    `[ah]afade=t=in:st=0:d=${FADE_S}:curve=qsin[ahf]`,
    `[atf][ahf]amix=inputs=2:duration=longest:dropout_transition=0,volume=2[xa]`,
    `[xa][am]concat=n=2:v=0:a=1,volume=${gainDb.toFixed(2)}dB,alimiter=limit=0.89:level=0[aout]`,
  ].join(';')
  return (crf) =>
    ffmpeg([
      '-i', src.file, '-filter_complex', fc, '-map', '[vout]', '-map', '[aout]',
      ...x264(width, ':keyint=120:min-keyint=24'), '-crf', String(crf), ...tags,
      '-c:a', 'aac', '-b:a', `${kbps}k`, '-ac', '2', '-ar', '48000', '-map_metadata', '-1', '-movflags', '+faststart', file,
    ])
}

/** The scroll-driven version: every other frame, all keyframes, no sound. */
function scrub(src, film, width, file) {
  return (crf) =>
    ffmpeg([
      '-i', src.file,
      '-vf', `select='not(mod(n,2))',setpts=N/12/TB,${picture(src, film, width)},format=yuv420p`,
      '-r', '12', ...x264(width), '-crf', String(crf), '-g', '1', '-keyint_min', '1', ...tags,
      '-an', '-map_metadata', '-1', '-movflags', '+faststart', file,
    ])
}

/** A still, from the source at the frame the film starts on (a loop starts on the clip's last 0.75 s). */
function poster(src, film, name, width, at) {
  ffmpeg([
    '-ss', String(at), '-i', src.file, '-frames:v', '1',
    '-vf', `${picture(src, film, width)},format=yuvj420p`, '-q:v', '2', join(OUT, name),
  ])
}

mkdirSync(OUT, { recursive: true })
const report = []
for (const [key, film] of Object.entries(films)) {
  if (ONLY && ONLY !== key) continue
  const master = join(MASTERS, film.master)
  const src = existsSync(master)
    ? { file: master, original: false }
    : { file: join(ORIGINALS, film.original), original: true }
  if (!existsSync(src.file)) throw new Error(`missing ${src.file}`)
  console.log(`\n== ${key}: from ${src.original ? 'the ORIGINAL clip (no master yet)' : 'the master'} ${src.file}`)

  const stem = film.loop || film.scrub
  const startAt = film.loop ? film.secs - FADE_S : 0
  // The loop's sound: levelled to the target from the source's own loudness, then checked on the file.
  let gain = film.loop ? TARGET_LUFS - lufs(src.file).lufs : 0
  for (const size of ['large', 'small']) {
    const width = SIZES[size]
    const suffix = size === 'small' ? '-small' : ''
    const file = join(OUT, `${stem}${suffix}.mp4`)
    let crf = film.crf + (size === 'small' ? 2 : 0)
    if (film.loop) {
      for (let attempt = 0; attempt < 2; attempt++) {
        crf = fit(loop(src, film, width, gain, size === 'small' ? 96 : 128, file), file, crf, film.caps[size])
        const got = lufs(file)
        console.log(`  ${stem}${suffix}: ${got.lufs} LUFS, peak ${got.peak} dBFS (gain ${gain.toFixed(2)} dB)`)
        if (Math.abs(got.lufs - TARGET_LUFS) <= 0.4) break
        gain += TARGET_LUFS - got.lufs
      }
    } else {
      crf = fit(scrub(src, film, width, file), file, crf, film.caps[size])
    }
    poster(src, film, `${stem.replace('-scrub', '')}-poster${suffix}.jpg`, width, startAt)
    report.push([`${stem}${suffix}.mp4`, width, crf])
  }
}

console.log('\nWrote:')
let total = 0
for (const f of readdirSync(OUT).sort()) {
  const p = join(OUT, f)
  total += statSync(p).size
  console.log(`  ${f.padEnd(30)} ${mb(p).toFixed(2)} MB`)
}
console.log(`  ${'total'.padEnd(30)} ${(total / 1e6).toFixed(2)} MB`)
console.log('CRF used:', report.map(([f, w, c]) => `${f} ${w}px crf ${c}`).join('; '))
