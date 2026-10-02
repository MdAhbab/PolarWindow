import { createSky, earthSurface, moonSurface, SURFACE_TURN } from './space'
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
 * The surface is real: NASA's LRO wide-angle camera mosaic over the whole
 * globe (space.ts), and from 80°S to the pole the LOLA hillshade tiles the
 * Map draws, placed in the same south polar stereographic projection
 * (longitude 0 at grid +y, east clockwise). In the dark theme the night sky
 * is behind it; in the light theme Earth stands in front of it at first.
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
  /** Light theme only: how far into the picture Earth stands, in front of the Moon, 0 to 1. */
  near?: number
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

export function token(name: string, fallback: string): Color {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  try {
    return new Color(v || fallback)
  } catch {
    return new Color(fallback)
  }
}

/**
 * The real south polar cap: the 16 hillshade tiles at zoom 2 stitched into one
 * 1,024-pixel square, with its edge faded so it meets the drawn globe softly.
 */
export async function poleRelief(tileUrl: (z: number, x: number, y: number) => string): Promise<CanvasTexture | null> {
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
export function capGeometry(radius: number): SphereGeometry {
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
  { theme = 'dark' }: { theme?: 'dark' | 'light' } = {},
): MoonScene {
  const renderer = new WebGLRenderer({ canvas, antialias: true, alpha: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.outputColorSpace = SRGBColorSpace

  const scene = new Scene()
  const camera = new PerspectiveCamera(35, 1, 0.01, 100)

  const moon = new Group()
  scene.add(moon)

  // The real Moon: NASA's LRO wide-angle camera mosaic, grey until it has loaded.
  const globeMat = new MeshStandardMaterial({ color: 0x8e8e8e, roughness: 1, metalness: 0 })
  const globe = new Mesh(new SphereGeometry(1, 128, 64), globeMat)
  globe.rotation.y = SURFACE_TURN
  moon.add(globe)
  let disposed = false
  const redraw = () => {
    if (!disposed && !raf) render()
  }
  moonSurface(globeMat, redraw)

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
  void poleRelief(tileUrl).then((t) => {
    if (!t || disposed) return
    capMaterial.map = t
    capMaterial.emissiveMap = t
    capMaterial.opacity = 1
    capMaterial.needsUpdate = true
    redraw()
  })

  // The Sun: a light carried with the Moon, circling in its equator plane.
  // Warm white: white tinted a quarter of the way to the Sun's amber, the same
  // in either theme (the light theme's ink is dark and would dim it).
  const sunColor = new Color(1, 1, 1).lerp(token('--color-sun-fill', '#f2a33c'), 0.25)
  const sun = new DirectionalLight(sunColor, 6.2)
  moon.add(sun)
  moon.add(sun.target)
  // Grazing light: a second, weaker Sun a little behind the first, so the
  // line between day and night is a soft band, as it is on the Moon from
  // afar, rather than a cut.
  const sunSoft = new DirectionalLight(sunColor, 0.9)
  moon.add(sunSoft)
  moon.add(sunSoft.target)
  // In the dark the night side is nearly black, as it is; on a light page it
  // is lifted to the grey of a Moon in a daytime sky, so it is never a hole.
  const dark = theme === 'dark'
  scene.add(new AmbientLight(dark ? 0x9aa5b1 : 0xb8bec6, dark ? 0.12 : 0.55))
  // Earthshine: sunlight off Earth, a faint cool light on the night side from
  // where Earth stands.
  const earthshine = new DirectionalLight(new Color(0.62, 0.7, 0.8), dark ? 0.32 : 0.45)
  earthshine.position.set(Math.sin(-35 * DEG) * 10, -0.8, Math.cos(-35 * DEG) * 10)
  moon.add(earthshine)
  moon.add(earthshine.target)

  // Earth, in the Moon's equator plane (so on the pole's horizon), drawn close
  // beside the limb so it is in the picture. Not to scale.
  const earthMat = new MeshBasicMaterial({ color: token('--color-earth', '#4fc6e0'), transparent: true, opacity: 0 })
  const earth = new Mesh(new SphereGeometry(0.075, 32, 16), earthMat)
  earth.position.set(Math.sin(-35 * DEG) * 1.14, -0.08, Math.cos(-35 * DEG) * 1.14)
  moon.add(earth)
  earthSurface(earthMat, redraw)

  // Dark: the night sky behind the Moon. Light: Earth in front of it, low in
  // the picture, which the scroll then leaves behind on the way to the pole.
  const sky = dark ? createSky() : null
  if (sky) scene.add(sky.group)
  const nearMat = new MeshStandardMaterial({ color: 0x6f8fb0, roughness: 0.85, metalness: 0 })
  const nearEarth = new Mesh(new SphereGeometry(0.95, 96, 48), nearMat)
  // Africa and Europe toward the viewer (longitude 20°E), tipped a little north.
  nearEarth.rotation.set(0.22, SURFACE_TURN - 20 * DEG, 0)
  nearEarth.visible = !dark
  scene.add(nearEarth)
  if (!dark) earthSurface(nearMat, redraw)

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
    // The sky turns a little with the Moon, for depth; it is far away.
    if (sky) sky.group.rotation.set(state.tilt * 0.15, (state.spin + spinExtra) * 0.12 + state.sunAz * 0.015, 0)
    if (!dark) {
      // In front of the Moon and below it; it sinks out of the picture as `near` falls.
      const n = state.near ?? 0
      nearEarth.visible = n > 0.01
      nearEarth.position.set(0.5, -1.12 - (1 - n) * 2.6, 1.75)
    }
    sunSoft.position.set(Math.sin(state.sunAz - 0.38) * 10, 0.3, Math.cos(state.sunAz - 0.38) * 10)
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
      nearEarth.geometry.dispose()
      globeMat.dispose()
      capMaterial.map?.dispose()
      capMaterial.dispose()
      earthMat.dispose()
      nearMat.dispose()
      sky?.dispose()
      renderer.dispose()
    },
  }
}
