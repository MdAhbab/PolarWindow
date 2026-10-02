import {
  AdditiveBlending,
  BackSide,
  BufferGeometry,
  CanvasTexture,
  Color,
  Float32BufferAttribute,
  Group,
  Mesh,
  MeshBasicMaterial,
  type MeshStandardMaterial,
  Points,
  PointsMaterial,
  SphereGeometry,
  SRGBColorSpace,
  TextureLoader,
  type Texture,
} from 'three'
import moonMapUrl from '../assets/space/moon-lro-wac-2048.jpg'
import earthMapUrl from '../assets/space/earth-blue-marble-2048.jpg'

/**
 * The real surfaces and the sky, shared by the front page's Moon and the
 * dashboard's scenes.
 *
 * The Moon is NASA's Lunar Reconnaissance Orbiter wide-angle camera mosaic
 * (LROC WAC global morphologic mosaic, from NASA Moon Trek), equirectangular,
 * longitude 0 at the centre. Earth is NASA's Blue Marble (Visible Earth,
 * December 2004, topography and bathymetry). Both are public domain. The sky
 * is drawn here, in code: stars and a Milky Way for the picture, not a star
 * catalogue.
 *
 * On a three.js sphere the texture's centre (longitude 0) faces +x; the
 * scenes keep longitude 0 at +z with east toward +x, so a globe is turned by
 * `SURFACE_TURN` about its axis.
 */
export const SURFACE_TURN = -Math.PI / 2

const loader = new TextureLoader()
const cache = new Map<string, Promise<Texture>>()
function load(url: string): Promise<Texture> {
  let p = cache.get(url)
  if (!p) {
    p = new Promise((resolve, reject) =>
      loader.load(
        url,
        (t) => {
          t.colorSpace = SRGBColorSpace
          t.anisotropy = 8
          resolve(t)
        },
        undefined,
        reject,
      ),
    )
    cache.set(url, p)
  }
  return p
}

/**
 * Puts the Moon's real surface on a material once it has loaded, with the
 * same map as a faint bump so the relief catches a low Sun. `onReady` draws
 * again. The texture is shared and cached: it is not disposed with a scene.
 */
export function moonSurface(material: MeshStandardMaterial, onReady: () => void) {
  void load(moonMapUrl).then((t) => {
    material.map = t
    material.bumpMap = t
    material.bumpScale = 1.2
    material.color.setRGB(1, 1, 1)
    material.needsUpdate = true
    onReady()
  })
}

/** Earth's real surface, the same way. */
export function earthSurface(material: MeshStandardMaterial | MeshBasicMaterial, onReady: () => void) {
  void load(earthMapUrl).then((t) => {
    material.map = t
    material.color.setRGB(1, 1, 1)
    material.needsUpdate = true
    onReady()
  })
}

/** A small seeded generator, so the sky is the same on every visit. */
function rng(seed: number) {
  let s = seed >>> 0
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0
    return s / 2 ** 32
  }
}

/** Value noise on a sphere's map, a few octaves: the Milky Way's clouds and dust. */
function fbm(x: number, y: number, r: (i: number, j: number) => number) {
  let v = 0
  let a = 0.5
  let f = 1
  for (let o = 0; o < 5; o++) {
    const xi = Math.floor(x * f)
    const yi = Math.floor(y * f)
    const xf = x * f - xi
    const yf = y * f - yi
    const s = (t: number) => t * t * (3 - 2 * t)
    const n00 = r(xi, yi)
    const n10 = r(xi + 1, yi)
    const n01 = r(xi, yi + 1)
    const n11 = r(xi + 1, yi + 1)
    const nx0 = n00 + (n10 - n00) * s(xf)
    const nx1 = n01 + (n11 - n01) * s(xf)
    v += a * (nx0 + (nx1 - nx0) * s(yf))
    a *= 0.5
    f *= 2.03
  }
  return v
}

/** The band of the Milky Way across the sky, as a faint glowing map on the inside of a sphere. */
function milkyWay(): CanvasTexture {
  // Low resolution on purpose: the glow is soft, and the map is worked out on the page's own thread.
  const w = 512
  const h = 256
  const c = document.createElement('canvas')
  c.width = w
  c.height = h
  const g = c.getContext('2d')!
  const img = g.createImageData(w, h)
  const hash = (i: number, j: number) => {
    const s = Math.sin(i * 127.1 + j * 311.7) * 43758.5453
    return s - Math.floor(s)
  }
  // The galactic plane, tilted across the scene's sky.
  const tilt = 62 * (Math.PI / 180)
  const ny = Math.cos(tilt)
  const nz = Math.sin(tilt)
  for (let y = 0; y < h; y++) {
    const lat = (0.5 - y / h) * Math.PI
    for (let x = 0; x < w; x++) {
      const lon = (x / w) * Math.PI * 2
      const px = Math.cos(lat) * Math.cos(lon)
      const py = Math.sin(lat)
      const pz = Math.cos(lat) * Math.sin(lon)
      const b = Math.asin(Math.max(-1, Math.min(1, py * ny + pz * nz))) // galactic latitude
      const along = Math.atan2(pz * ny - py * nz, px)
      // Brighter towards one side of the band, as toward the galactic centre.
      const core = 0.55 + 0.45 * Math.max(0, Math.cos(along - 0.6)) ** 3
      const band = Math.exp(-((b / 0.2) ** 2)) * core
      const clouds = fbm(x / 32, y / 32, hash)
      const dust = fbm(x / 11 + 40, y / 11 + 40, hash)
      let v = band * (0.35 + 0.9 * clouds) - band * Math.max(0, dust - 0.52) * 2.4
      v = Math.max(0, v) * 0.55
      const i = (y * w + x) * 4
      img.data[i] = Math.min(255, v * 235)
      img.data[i + 1] = Math.min(255, v * 228)
      img.data[i + 2] = Math.min(255, v * 255)
      img.data[i + 3] = 255
    }
  }
  g.putImageData(img, 0, 0)
  const t = new CanvasTexture(c)
  t.colorSpace = SRGBColorSpace
  return t
}

/**
 * The night sky: a few thousand stars of every brightness, thicker along the
 * Milky Way, and the Milky Way's glow. Drawn far away, so the scene can turn
 * it a little for depth. Call `dispose` with the scene.
 */
export function createSky(radius = 60): { group: Group; dispose: () => void } {
  const group = new Group()
  const r = rng(11)
  const tilt = 62 * (Math.PI / 180)
  const disposables: { dispose: () => void }[] = []
  const classes = [
    { n: 5200, size: 1.1, opacity: 0.55 },
    { n: 1400, size: 1.7, opacity: 0.8 },
    { n: 260, size: 2.6, opacity: 1 },
  ]
  for (const k of classes) {
    const pos: number[] = []
    const col: number[] = []
    for (let i = 0; i < k.n; i++) {
      // Half the stars crowd toward the galactic plane.
      let x = r() * 2 - 1
      let y = r() * 2 - 1
      let z = r() * 2 - 1
      const l = Math.hypot(x, y, z) || 1
      x /= l
      y /= l
      z /= l
      if (r() < 0.45) {
        const b = (r() - 0.5) * 0.45
        const along = r() * Math.PI * 2
        // A point near the plane through the x axis tilted by `tilt`.
        const px = Math.cos(along)
        const py = -Math.sin(along) * Math.sin(tilt) + b * Math.cos(tilt)
        const pz = Math.sin(along) * Math.cos(tilt) + b * Math.sin(tilt)
        const m = Math.hypot(px, py, pz)
        x = px / m
        y = py / m
        z = pz / m
      }
      pos.push(x * radius, y * radius, z * radius)
      // Colour by temperature: mostly white, some blue, some warm.
      const t = r()
      const c = t < 0.15 ? new Color(0.75, 0.83, 1) : t > 0.85 ? new Color(1, 0.86, 0.7) : new Color(1, 0.98, 0.95)
      col.push(c.r, c.g, c.b)
    }
    const geo = new BufferGeometry()
    geo.setAttribute('position', new Float32BufferAttribute(pos, 3))
    geo.setAttribute('color', new Float32BufferAttribute(col, 3))
    const mat = new PointsMaterial({
      size: k.size,
      sizeAttenuation: false,
      vertexColors: true,
      transparent: true,
      opacity: k.opacity,
      depthWrite: false,
    })
    disposables.push(geo, mat)
    group.add(new Points(geo, mat))
  }
  const glowTex = milkyWay()
  const glowGeo = new SphereGeometry(radius * 1.05, 64, 32)
  const glowMat = new MeshBasicMaterial({ map: glowTex, side: BackSide, transparent: true, blending: AdditiveBlending, depthWrite: false, opacity: 0.9 })
  disposables.push(glowTex, glowGeo, glowMat)
  group.add(new Mesh(glowGeo, glowMat))
  return { group, dispose: () => disposables.forEach((d) => d.dispose()) }
}
