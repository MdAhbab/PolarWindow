import {
  AmbientLight,
  CanvasTexture,
  Color,
  DirectionalLight,
  Group,
  Mesh,
  MeshBasicMaterial,
  MeshStandardMaterial,
  PerspectiveCamera,
  Scene,
  SphereGeometry,
  SRGBColorSpace,
  WebGLRenderer,
} from 'three'

/**
 * The front page's Moon.
 *
 * The globe itself is drawn for illustration: a grey sphere with made-up
 * shading, because no global map ships with this project. The cap from 80°S
 * to the pole is real: the LOLA hillshade tiles the Map draws, placed in the
 * same south polar stereographic projection (longitude 0 at grid +y, east
 * clockwise). The page says which is which.
 *
 * The Sun is a light that circles the Moon in its equator plane, which is
 * what it does as seen from the pole: along the horizon, never overhead.
 * Earth is a small sphere in the direction of longitude 0, low over the
 * pole's horizon. Neither is to scale, and the page says so.
 *
 * Colours come from the page's CSS tokens, so sunlight is the Sun's amber and
 * Earth is Earth's cyan, in either theme.
 */

const R_MOON_M = 1_737_400
const TILE_HALF_EXTENT_M = 303_960
const CAP_COLAT_DEG = 10
const DEG = Math.PI / 180

/** What the scroll position drives. Every field is plain numbers GSAP can tween. */
export interface SceneState {
  /** Tilt of the Moon about the screen's x axis, radians: negative shows the south pole. */
  tilt: number
  /** Spin about the Moon's own axis, radians. */
  spin: number
  /** Camera distance, Moon radii. */
  distance: number
  /** Where the Sun is along the horizon, radians. */
  sunAz: number
  /** How far Earth has faded in, 0 to 1. */
  earth: number
  /** Where the Moon sits across the screen, as a fraction of its half-width: 0 centre, 1 right edge. */
  shift: number
}

export interface MoonScene {
  state: SceneState
  setPointer: (x: number, y: number) => void
  setAutoSpin: (on: boolean) => void
  render: () => void
  start: () => void
  stop: () => void
  dispose: () => void
}

function token(name: string, fallback: string): Color {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  try {
    return new Color(v || fallback)
  } catch {
    return new Color(fallback)
  }
}

/** A small seeded generator, so the drawn globe looks the same on every visit. */
function rng(seed: number) {
  let s = seed >>> 0
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0
    return s / 2 ** 32
  }
}

/** The illustrative globe: soft dark patches and craters on grey, equirectangular. */
function drawnGlobe(): CanvasTexture {
  const w = 2048
  const h = 1024
  const c = document.createElement('canvas')
  c.width = w
  c.height = h
  const g = c.getContext('2d')!
  g.fillStyle = '#8e8e8e'
  g.fillRect(0, 0, w, h)
  const r = rng(7)
  const blob = (x: number, y: number, rad: number, rgba: string) => {
    const grd = g.createRadialGradient(x, y, 0, x, y, rad)
    grd.addColorStop(0, rgba)
    grd.addColorStop(1, rgba.replace(/[\d.]+\)$/, '0)'))
    g.fillStyle = grd
    g.fillRect(x - rad, y - rad, rad * 2, rad * 2)
  }
  // Broad darker plains, mostly away from the poles.
  for (let i = 0; i < 40; i++) {
    blob(r() * w, h * (0.25 + r() * 0.5), 60 + r() * 180, `rgba(70,70,70,${0.25 + r() * 0.3})`)
  }
  // Mottling at every scale.
  for (let i = 0; i < 2600; i++) {
    const light = r() > 0.5
    blob(r() * w, r() * h, 3 + r() ** 2 * 40, light ? `rgba(200,200,200,${r() * 0.06})` : `rgba(40,40,40,${r() * 0.08})`)
  }
  // Craters: mostly small, a faint floor and a thin bright rim.
  for (let i = 0; i < 900; i++) {
    const x = r() * w
    const y = r() * h
    const rad = 1 + r() ** 5 * 26
    g.beginPath()
    g.arc(x, y, rad, 0, Math.PI * 2)
    g.fillStyle = `rgba(50,50,50,${0.06 + r() * 0.1})`
    g.fill()
    g.beginPath()
    g.arc(x - rad * 0.12, y - rad * 0.12, rad, Math.PI * 0.9, Math.PI * 1.9)
    g.lineWidth = Math.max(0.5, rad * 0.12)
    g.strokeStyle = `rgba(230,230,230,${0.05 + r() * 0.1})`
    g.stroke()
  }
  const t = new CanvasTexture(c)
  t.colorSpace = SRGBColorSpace
  t.anisotropy = 4
  return t
}

/**
 * The real south polar cap: the 16 hillshade tiles at zoom 2 stitched into one
 * 1,024-pixel square, with its edge faded so it meets the drawn globe softly.
 */
async function poleRelief(tileUrl: (z: number, x: number, y: number) => string): Promise<CanvasTexture | null> {
  const n = 4
  const px = 256
  const c = document.createElement('canvas')
  c.width = c.height = n * px
  const g = c.getContext('2d')!
  const loads: Promise<boolean>[] = []
  for (let tx = 0; tx < n; tx++) {
    for (let ty = 0; ty < n; ty++) {
      loads.push(
        new Promise((resolve) => {
          const img = new Image()
          img.crossOrigin = 'anonymous'
          img.onload = () => {
            g.drawImage(img, tx * px, ty * px, px, px)
            resolve(true)
          }
          img.onerror = () => resolve(false)
          img.src = tileUrl(2, tx, ty)
        }),
      )
    }
  }
  const ok = (await Promise.all(loads)).filter(Boolean).length
  if (ok < n * n) return null
  // Fade the square to a circle at 80°S.
  const half = (n * px) / 2
  const edge = (2 * R_MOON_M * Math.tan((CAP_COLAT_DEG * DEG) / 2) / TILE_HALF_EXTENT_M) * half
  const mask = g.createRadialGradient(half, half, edge * 0.82, half, half, edge)
  mask.addColorStop(0, 'rgba(0,0,0,1)')
  mask.addColorStop(1, 'rgba(0,0,0,0)')
  g.globalCompositeOperation = 'destination-in'
  g.fillStyle = mask
  g.fillRect(0, 0, c.width, c.height)
  const t = new CanvasTexture(c)
  t.colorSpace = SRGBColorSpace
  return t
}

/**
 * A cap from the south pole to 80°S whose texture coordinates are the south
 * polar stereographic grid, so each tile pixel lands where it belongs.
 */
function capGeometry(radius: number): SphereGeometry {
  const theta = CAP_COLAT_DEG * DEG
  const geo = new SphereGeometry(radius, 256, 48, 0, Math.PI * 2, Math.PI - theta, theta)
  const pos = geo.attributes.position
  const uv = geo.attributes.uv
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i) / radius
    const y = pos.getY(i) / radius
    const z = pos.getZ(i) / radius
    const colat = Math.acos(Math.max(-1, Math.min(1, -y)))
    const lon = Math.atan2(x, z)
    const rM = 2 * R_MOON_M * Math.tan(colat / 2)
    const gx = rM * Math.sin(lon)
    const gy = rM * Math.cos(lon)
    uv.setXY(i, (gx + TILE_HALF_EXTENT_M) / (2 * TILE_HALF_EXTENT_M), (gy + TILE_HALF_EXTENT_M) / (2 * TILE_HALF_EXTENT_M))
  }
  uv.needsUpdate = true
  return geo
}

export function createMoonScene(
  canvas: HTMLCanvasElement,
  tileUrl: (z: number, x: number, y: number) => string,
  initial: SceneState,
): MoonScene {
  const renderer = new WebGLRenderer({ canvas, antialias: true, alpha: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.outputColorSpace = SRGBColorSpace

  const scene = new Scene()
  const camera = new PerspectiveCamera(35, 1, 0.01, 100)

  const moon = new Group()
  scene.add(moon)

  const globeTex = drawnGlobe()
  const globe = new Mesh(
    new SphereGeometry(1, 128, 64),
    new MeshStandardMaterial({ map: globeTex, roughness: 1, metalness: 0 }),
  )
  moon.add(globe)

  // The relief glows faintly on its own, so the real terrain stays readable on
  // the night side too; the Sun adds its light on the day side.
  const capMaterial = new MeshStandardMaterial({
    roughness: 1,
    metalness: 0,
    transparent: true,
    opacity: 0,
    emissive: new Color(1, 1, 1),
    emissiveIntensity: 0.28,
  })
  const cap = new Mesh(capGeometry(1.0015), capMaterial)
  moon.add(cap)
  let disposed = false
  void poleRelief(tileUrl).then((t) => {
    if (!t || disposed) return
    capMaterial.map = t
    capMaterial.emissiveMap = t
    capMaterial.opacity = 1
    capMaterial.needsUpdate = true
  })

  // The Sun: a light carried with the Moon, circling in its equator plane.
  // Warm white: white tinted a quarter of the way to the Sun's amber, the same
  // in either theme (the light theme's ink is dark and would dim it).
  const sun = new DirectionalLight(new Color(1, 1, 1).lerp(token('--color-sun-fill', '#f2a33c'), 0.25), 4.5)
  moon.add(sun)
  moon.add(sun.target)
  scene.add(new AmbientLight(token('--color-ink-3', '#8d99a5'), 0.3))

  // Earth, in the Moon's equator plane (so on the pole's horizon), drawn close
  // beside the limb so it is in the picture. Not to scale.
  const earthMat = new MeshBasicMaterial({ color: token('--color-earth', '#4fc6e0'), transparent: true, opacity: 0 })
  const earth = new Mesh(new SphereGeometry(0.075, 32, 16), earthMat)
  earth.position.set(Math.sin(-35 * DEG) * 1.14, -0.08, Math.cos(-35 * DEG) * 1.14)
  moon.add(earth)

  const state: SceneState = { ...initial }
  const pointer = { x: 0, y: 0, sx: 0, sy: 0 }
  let autoSpin = false
  let spinExtra = 0
  let raf = 0
  let last = performance.now()

  const resize = () => {
    const w = canvas.clientWidth || window.innerWidth
    const h = canvas.clientHeight || window.innerHeight
    renderer.setSize(w, h, false)
    camera.aspect = w / h
    camera.updateProjectionMatrix()
  }
  resize()
  window.addEventListener('resize', resize)

  const render = () => {
    const now = performance.now()
    const dt = Math.min(0.1, (now - last) / 1000)
    last = now
    if (autoSpin) spinExtra += dt * 0.06
    // Ease the pointer so the Moon leans toward it rather than jumping.
    pointer.sx += (pointer.x - pointer.sx) * Math.min(1, dt * 4)
    pointer.sy += (pointer.y - pointer.sy) * Math.min(1, dt * 4)

    moon.rotation.set(state.tilt + pointer.sy * 0.12, 0, 0)
    moon.rotateY(state.spin + spinExtra + pointer.sx * 0.25)
    // `shift` moves the picture, not the Moon: an offset view keeps the Moon
    // seen head-on (no sideways perspective) while it sits right of the text.
    // On a tall screen it stays centred, behind the text.
    const w = canvas.clientWidth || window.innerWidth
    const h = canvas.clientHeight || window.innerHeight
    const dx = camera.aspect > 1.1 ? -state.shift * (w / 2) : 0
    camera.setViewOffset(w, h, dx, 0, w, h)
    camera.position.set(0, 0, state.distance)
    camera.lookAt(0, 0, 0)

    sun.position.set(Math.sin(state.sunAz) * 10, 0.3, Math.cos(state.sunAz) * 10)
    earthMat.opacity = state.earth
    earth.visible = state.earth > 0.01
    renderer.render(scene, camera)
  }

  const loop = () => {
    render()
    raf = requestAnimationFrame(loop)
  }

  return {
    state,
    setPointer: (x, y) => {
      pointer.x = x
      pointer.y = y
    },
    setAutoSpin: (on) => {
      autoSpin = on
    },
    render,
    start: () => {
      if (!raf) {
        last = performance.now()
        raf = requestAnimationFrame(loop)
      }
    },
    stop: () => {
      cancelAnimationFrame(raf)
      raf = 0
    },
    dispose: () => {
      disposed = true
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
      globe.geometry.dispose()
      cap.geometry.dispose()
      earth.geometry.dispose()
      ;(globe.material as MeshStandardMaterial).dispose()
      capMaterial.map?.dispose()
      capMaterial.dispose()
      earthMat.dispose()
      globeTex.dispose()
      renderer.dispose()
    },
  }
}
