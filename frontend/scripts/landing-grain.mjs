#!/usr/bin/env node
/**
 * Writes public/landing/grain.png: a 128 px tile of film grain, made once and
 * committed. Grey noise around mid-grey (128), so laid over a film with
 * mix-blend-mode: overlay at a few percent it lightens and darkens the picture
 * evenly and shifts nothing else. The tile is laid out so its edges meet (the
 * noise is independent per pixel, so it repeats without a seam).
 *
 *   node scripts/landing-grain.mjs
 *
 * No dependencies: the PNG is written by hand (zlib from Node, a CRC table).
 */
import { deflateSync } from 'node:zlib'
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const SIZE = 128
const SIGMA = 38 // spread of the grey around 128; the CSS opacity sets how strong it is on the page

// A seeded generator, so the file is the same every time it is made.
let seed = 0x9e3779b9
const rand = () => {
  seed = (seed + 0x6d2b79f5) | 0
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296
}
// Sum of four uniforms: close enough to bell-shaped for grain.
const gauss = () => (rand() + rand() + rand() + rand() - 2) / Math.sqrt(4 / 12)

const raw = Buffer.alloc(SIZE * (SIZE + 1))
for (let y = 0; y < SIZE; y++) {
  raw[y * (SIZE + 1)] = 0 // filter: none
  for (let x = 0; x < SIZE; x++) {
    raw[y * (SIZE + 1) + 1 + x] = Math.max(0, Math.min(255, Math.round(128 + SIGMA * gauss())))
  }
}

const crcTable = Array.from({ length: 256 }, (_, n) => {
  let c = n
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
  return c >>> 0
})
const crc32 = (buf) => {
  let c = 0xffffffff
  for (const b of buf) c = crcTable[(c ^ b) & 0xff] ^ (c >>> 8)
  return (c ^ 0xffffffff) >>> 0
}
const chunk = (type, data) => {
  const len = Buffer.alloc(4)
  len.writeUInt32BE(data.length)
  const body = Buffer.concat([Buffer.from(type, 'ascii'), data])
  const crc = Buffer.alloc(4)
  crc.writeUInt32BE(crc32(body))
  return Buffer.concat([len, body, crc])
}
const ihdr = Buffer.alloc(13)
ihdr.writeUInt32BE(SIZE, 0)
ihdr.writeUInt32BE(SIZE, 4)
ihdr[8] = 8 // bit depth
ihdr[9] = 0 // colour type: greyscale

const png = Buffer.concat([
  Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
  chunk('IHDR', ihdr),
  chunk('IDAT', deflateSync(raw, { level: 9 })),
  chunk('IEND', Buffer.alloc(0)),
])

const out = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'landing')
mkdirSync(out, { recursive: true })
writeFileSync(join(out, 'grain.png'), png)
console.log(`public/landing/grain.png ${(png.length / 1024).toFixed(1)} KB`)
