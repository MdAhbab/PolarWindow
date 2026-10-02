import {
  BackSide,
  BufferGeometry,
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
import milkyWayUrl from '../assets/space/milky-way-eso-4000.jpg'

/**
 * The real surfaces and the sky, shared by the front page's Moon and the
 * dashboard's scenes.
 *
 * The Moon is NASA's Lunar Reconnaissance Orbiter wide-angle camera mosaic
 * (LROC WAC global morphologic mosaic, from NASA Moon Trek), equirectangular,
 * longitude 0 at the centre. Earth is NASA's Blue Marble (Visible Earth,
 * December 2004, topography and bathymetry). Both are public domain. The
 * Milky Way is ESO's all-sky panorama by Serge Brunier (CC BY 4.0, credited
 * on the front page).
 *
 * On a three.js sphere the texture's centre (longitude 0) faces +x; the
 * scenes keep longitude 0 at +z with east toward +x, so a globe is turned by
 * `SURFACE_TURN` about its axis.
 */
export const SURFACE_TURN = -Math.PI / 2

/** How far the Milky Way's band is tipped from level in the first view, rising to the right. */
const BAND = 62 * (Math.PI / 180)

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

/** A small seeded generator, so the stars are the same on every visit. */
function rng(seed: number) {
  let s = seed >>> 0
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0
    return s / 2 ** 32
  }
}

/**
 * The night sky: the Milky Way as photographed by Serge Brunier for ESO (the
 * whole sky, in galactic coordinates, CC BY 4.0, credited on the page), on
 * the inside of a far sphere, turned so the galactic centre sits behind the
 * Moon in the first view and the band rises to the upper right; and a few
 * hundred crisp stars in front of it, so the sky stays sharp on any screen.
 * Call `dispose` with the scene.
 */
export function createSky(radius = 60, onReady?: () => void): { group: Group; dispose: () => void } {
  const group = new Group()
  const disposables: { dispose: () => void }[] = []

  const panoGeo = new SphereGeometry(radius * 1.05, 96, 48)
  const panoMat = new MeshBasicMaterial({ color: 0x000000, side: BackSide, depthWrite: false })
  const pano = new Mesh(panoGeo, panoMat)
  // Seen from inside, a sphere's map reads mirrored: un-mirror it, then turn the
  // galactic centre (the map's centre, now on -x) to -z and tip the band up to the right.
  pano.scale.x = -1
  pano.rotation.set(0, -Math.PI / 2, BAND, 'ZYX')
  // Then the core a little down and left of centre, so it glows just past the Moon's limb.
  const aim = new Group()
  aim.rotation.set(-0.2, 0.16, 0)
  aim.add(pano)
  group.add(aim)
  disposables.push(panoGeo, panoMat)
  void load(milkyWayUrl).then((t) => {
    panoMat.map = t
    // A little below the photograph's own brightness: it is the page's background.
    panoMat.color.setRGB(0.78, 0.78, 0.8)
    panoMat.needsUpdate = true
    onReady?.()
  })

  const r = rng(11)
  const pos: number[] = []
  const col: number[] = []
  for (let i = 0; i < 420; i++) {
    let x = r() * 2 - 1
    let y = r() * 2 - 1
    let z = r() * 2 - 1
    const l = Math.hypot(x, y, z) || 1
    x /= l
    y /= l
    z /= l
    pos.push(x * radius, y * radius, z * radius)
    const t = r()
    const c = t < 0.18 ? new Color(0.78, 0.85, 1) : t > 0.82 ? new Color(1, 0.88, 0.72) : new Color(1, 0.98, 0.95)
    col.push(c.r, c.g, c.b)
  }
  const geo = new BufferGeometry()
  geo.setAttribute('position', new Float32BufferAttribute(pos, 3))
  geo.setAttribute('color', new Float32BufferAttribute(col, 3))
  const mat = new PointsMaterial({ size: 1.8, sizeAttenuation: false, vertexColors: true, transparent: true, opacity: 0.85, depthWrite: false })
  disposables.push(geo, mat)
  group.add(new Points(geo, mat))
  return { group, dispose: () => disposables.forEach((d) => d.dispose()) }
}
