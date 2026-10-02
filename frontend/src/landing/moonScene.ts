import { createSky, earthSurface, loadTexture, moonSurface, SURFACE_TURN } from './space'
import { atmosphere, cloudsUrl, loadGround, type Ground } from './earthrise'
import {
  AmbientLight,
  CanvasTexture,
  Color,
  DirectionalLight,
  Group,
  type Material,
  Matrix4,
  Mesh,
  MeshBasicMaterial,
  MeshStandardMaterial,
  PerspectiveCamera,
  Quaternion,
  Scene,
  SphereGeometry,
  SRGBColorSpace,
  Vector3,
  WebGLRenderer,
} from 'three'

/**
 * The front page's Moon.
 *
 * The surface is real: NASA's LRO wide-angle camera mosaic over the whole
 * globe (space.ts), and from 80°S to the pole the LOLA hillshade tiles the
 * Map draws, placed in the same south polar stereographic projection
 * (longitude 0 at grid +y, east clockwise). In the dark theme the night sky
 * is behind it.
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
  /**
   * With the ground (light theme): 1 standing on it at Connecting Ridge with
   * Earth rising, 0 out at the whole Moon; the flight between is the scroll.
   */
  ground?: number
  /** With the ground: 1 the black sky and the Milky Way, 0 the page's own ground behind the Moon. */
  space?: number
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

/** Connecting Ridge (candidate site B), where the light theme's first picture stands. */
const SITE = { latDeg: -89.43804, lonDeg: 222.71699 }
const R_KM = R_MOON_M / 1000
/** Earth from the Moon: 384,400 km away, 6,371 km in radius, in Moon radii. */
const EARTH_AT = 384_400 / R_KM
const EARTH_R = 6_371 / R_KM

/** A point on the unit Moon in the scene's Moon-fixed axes: +y north, longitude 0 at +z, east toward +x. */
const onMoon = (latDeg: number, lonDeg: number) =>
  new Vector3(
    Math.cos(latDeg * DEG) * Math.sin(lonDeg * DEG),
    Math.sin(latDeg * DEG),
    Math.cos(latDeg * DEG) * Math.cos(lonDeg * DEG),
  )
/** The sky's own lens, degrees top to bottom. */
const SKY_FOV = 72
const smooth = (a: number, b: number, x: number) => {
  const t = Math.max(0, Math.min(1, (x - a) / (b - a)))
  return t * t * (3 - 2 * t)
}

export function createMoonScene(
  canvas: HTMLCanvasElement,
  tileUrl: (z: number, x: number, y: number) => string,
  initial: SceneState,
  { theme = 'dark', ground: withGround = false }: { theme?: 'dark' | 'light'; ground?: boolean } = {},
): MoonScene {
  // The ground needs depth from two metres to Earth's distance: a logarithmic depth buffer.
  const renderer = new WebGLRenderer({ canvas, antialias: true, alpha: true, logarithmicDepthBuffer: withGround })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.outputColorSpace = SRGBColorSpace

  const scene = new Scene()
  const camera = new PerspectiveCamera(35, 1, withGround ? 5e-7 : 0.01, withGround ? 2000 : 100)

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
    // The relief map is a neutral grey; the photograph around it is warmer and a little lighter.
    color: new Color(1.2, 1.15, 1.08),
    roughness: 1,
    metalness: 0,
    transparent: true,
    opacity: 0,
    emissive: new Color(1, 0.96, 0.9),
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
  const ambient = new AmbientLight(dark ? 0x9aa5b1 : 0xb8bec6, dark ? 0.12 : 0.55)
  scene.add(ambient)
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

  // The ground and Earth (light theme): Connecting Ridge's real terrain on the
  // globe, Earth at its true distance and size over it. The globe sits 8 km
  // low while the viewer is on the ground, so it never shows through a
  // crater the terrain dips into; from orbit the difference cannot be seen.
  const S = onMoon(SITE.latDeg, SITE.lonDeg)
  const toEarth = new Vector3(0, 0, 1)
  const fwd = toEarth.clone().sub(S.clone().multiplyScalar(toEarth.dot(S))).normalize()
  const right = fwd.clone().cross(S).normalize()
  let ground: Ground | null = null
  let eyeR = 1
  /** The eye's height over the ground, in Moon radii: two metres. */
  const EYE_UP = 0.002 / R_KM
  let sunAzGround = 0
  let sunElGround = 1.4
  const bigEarthMat = new MeshStandardMaterial({ color: 0x2a4d7a, roughness: 0.9, metalness: 0 })
  const bigEarth = new Mesh(new SphereGeometry(EARTH_R, 96, 48), bigEarthMat)
  const cloudMat = new MeshStandardMaterial({ color: 0xffffff, transparent: true, opacity: 0, roughness: 1, depthWrite: false })
  const clouds = new Mesh(new SphereGeometry(EARTH_R * 1.008, 96, 48), cloudMat)
  const air = atmosphere(EARTH_R)
  let groundReady = !withGround
  let groundLost = false
  if (withGround) {
    bigEarth.position.copy(toEarth).multiplyScalar(EARTH_AT)
    // Africa and the Atlantic toward the Moon, tipped a little north.
    bigEarth.rotation.set(0.35, SURFACE_TURN - 10 * DEG, 0)
    clouds.position.copy(bigEarth.position)
    clouds.rotation.copy(bigEarth.rotation)
    air.position.copy(bigEarth.position)
    moon.add(bigEarth, clouds, air)
    // Earth from the Moon is far brighter than the Moon's own ground; a gain keeps it from looking dim beside it.
    earthSurface(bigEarthMat, redraw, 1.7)
    void loadTexture(cloudsUrl).then((t) => {
      cloudMat.alphaMap = t
      cloudMat.opacity = 0.95
      cloudMat.needsUpdate = true
      redraw()
    })
    void loadGround().then((g) => {
      if (disposed) return g.dispose()
      ground = g
      // The ground's own frame (eye at the origin, Earth along -z, up +y), in km, onto the globe.
      const surfaceKm = R_KM + 1.9575 + 0.002 // Connecting Ridge stands 1,957 m above the datum; the eye 2 m over it
      eyeR = surfaceKm / R_KM
      const basis = new Group()
      basis.matrixAutoUpdate = false
      // Columns: x = right, y = up, z = -forward; then scaled to Moon radii and placed at the eye.
      basis.matrix.makeBasis(right, S, fwd.clone().negate())
      basis.matrix.scale(new Vector3(1 / R_KM, 1 / R_KM, 1 / R_KM))
      basis.matrix.setPosition(S.clone().multiplyScalar(eyeR))
      // Shaded by its own material (earthrise.ts), for the Sun its shadows were worked out for.
      basis.add(g.mesh)
      moon.add(basis)
      sunAzGround = g.sunRelAzDeg
      sunElGround = g.sunElDeg
      groundReady = true
      redraw()
    }).catch(() => {
      // Without the ground the flight starts in orbit: the Moon in the night sky.
      groundLost = true
      groundReady = true
      redraw()
    })
  }

  // The night sky. Dark theme: always, behind the Moon. Light theme: while on
  // the ground and on the way out, then it gives way to the page. On the
  // ground the galaxy's core stands up and to the left of Earth.
  const sky = dark || withGround ? createSky(60, redraw, withGround ? [0.2, 0.3] : [-0.2, 0.16]) : null
  // The sky as it stands over the site, in the Moon's own axes: straight ahead
  // of it is the horizon under Earth. Earth and the stars keep their places
  // against each other, whatever the camera does.
  const skyAtSite = new Quaternion().setFromRotationMatrix(new Matrix4().makeBasis(right, S, fwd.clone().negate()))
  // The sky is drawn through its own, wider lens first, then the Moon over it:
  // a wide-angle sky shows more of the galaxy, at about the photograph's own
  // sharpness, where the Moon's narrow lens would blow it up.
  const skyScene = new Scene()
  const skyCam = new PerspectiveCamera(SKY_FOV, 1, 0.1, 200)
  if (sky) skyScene.add(sky.group)
  renderer.autoClear = false

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
    skyCam.aspect = w / h
    skyCam.updateProjectionMatrix()
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

    // On the ground, the Moon holds still under the viewer; the lean toward the pointer comes in with the flight out.
    const g = withGround && !groundLost ? (state.ground ?? 0) : 0
    const u = 1 - g
    const lean = smooth(0.6, 1, u)
    moon.rotation.set(state.tilt + pointer.sy * 0.12 * lean, 0, 0)
    moon.rotateY(state.spin + spinExtra * lean + pointer.sx * 0.25 * lean)
    moon.updateMatrixWorld()
    // `shift` moves the picture, not the Moon: an offset view keeps the Moon
    // seen head-on (no sideways perspective) while it sits right of the text.
    // On a tall screen it stays centred, behind the text.
    const w = canvas.clientWidth || window.innerWidth
    const h = canvas.clientHeight || window.innerHeight
    const portrait = camera.aspect < 1
    const dx = camera.aspect > 1.1 ? -state.shift * (w / 2) * smooth(0.55, 1, u) : 0
    camera.setViewOffset(w, h, dx, 0, w, h)
    if (g > 0) {
      // The flight: from the eye on the ground, up over the site, round and out
      // to where the Moon is seen whole, the lens widening from a telephoto.
      const q = moon.getWorldQuaternion(new Quaternion())
      const up = S.clone().applyQuaternion(q)
      const eye = up.clone().multiplyScalar(eyeR)
      // On the ground: look toward Earth, a little left of it, so Earth stands
      // right of the words, 62% of the way across a wide screen and in the
      // middle of a tall one.
      const across = 0.5 + 0.12 * smooth(1, 1.3, camera.aspect)
      const yaw = -Math.atan((2 * across - 1) * Math.tan(5.5 * DEG) * camera.aspect)
      const look = fwd
        .clone()
        .multiplyScalar(Math.cos(yaw))
        .add(right.clone().multiplyScalar(Math.sin(yaw)))
        .applyQuaternion(q)
      // Wide: the skyline about 60% down, Earth sitting on it. Tall: look up, so
      // the sky is behind the words and Earth rises near the foot of the screen.
      const lookPitch = (portrait ? 6.7 : 0.1) * DEG
      const groundTarget = eye.clone().add(look.multiplyScalar(Math.cos(lookPitch)).add(up.clone().multiplyScalar(Math.sin(lookPitch))).multiplyScalar(0.2))
      const orbit = new Vector3(0, 0, state.distance)
      const r = eyeR * (state.distance / eyeR) ** u
      const dir = new Vector3().copy(up).lerp(orbit.clone().normalize(), smooth(0.12, 1, u)).normalize()
      camera.position.copy(dir.multiplyScalar(r))
      camera.up.copy(up).lerp(new Vector3(0, 1, 0), smooth(0.1, 0.9, u)).normalize()
      camera.lookAt(groundTarget.lerp(new Vector3(0, 0, 0), smooth(0.04, 0.55, u)))
      const fov = 11 + (35 - 11) * smooth(0, 0.75, u)
      camera.fov = portrait ? fov * (1.9 - 0.9 * smooth(0, 0.75, u)) : fov
      // As near as a fifth of the height over the ground, so the soil at the viewer's feet is never cut away.
      camera.near = Math.max(5e-7, (r - eyeR + EYE_UP) * 0.2)
      camera.updateProjectionMatrix()
    } else {
      if (withGround && camera.fov !== 35) {
        camera.fov = 35
        camera.near = 0.01
        camera.updateProjectionMatrix()
      }
      camera.up.set(0, 1, 0)
      camera.position.set(0, 0, state.distance)
      camera.lookAt(0, 0, 0)
    }
    globe.scale.setScalar(1 - (8 / R_KM) * g)
    cap.scale.setScalar(1 - (8 / R_KM) * g)
    // The ground hands over to the globe's own relief as the viewer climbs.
    ground?.setOpacity(smooth(0.86, 0.98, g))
    bigEarth.visible = clouds.visible = air.visible = withGround
    // By day the Moon is pale: on the light page its night side is lifted well
    // clear of black. In the black sky of the flight it keeps its contrast.
    const space = withGround ? (state.space ?? 0) : dark ? 1 : 0
    ambient.intensity = dark ? 0.12 : 0.1 * space + 2.6 * (1 - space)

    // The Sun: on the ground, where the ground's shadows were worked out for
    // (low, just above the horizon); out at the Moon, where the scroll puts it.
    if (g > 0) {
      const sunDir = fwd
        .clone()
        .multiplyScalar(Math.cos(sunAzGround * DEG))
        .add(right.clone().multiplyScalar(Math.sin(sunAzGround * DEG)))
        .multiplyScalar(Math.cos(sunElGround * DEG))
        .add(S.clone().multiplyScalar(Math.sin(sunElGround * DEG)))
        .multiplyScalar(10)
      const out = new Vector3(Math.sin(state.sunAz) * 10, 0.3, Math.cos(state.sunAz) * 10)
      sun.position.copy(sunDir.lerp(out, smooth(0.3, 1, u)))
    } else {
      sun.position.set(Math.sin(state.sunAz) * 10, 0.3, Math.cos(state.sunAz) * 10)
    }
    if (sky && withGround) {
      // Earth and the stars are both too far for the camera's own movement to
      // shift one against the other, so the sky is fixed to Earth: whatever
      // the camera does, the stars around Earth move across the screen with
      // it. The sky is drawn through a wider lens than the ground (below), so
      // it is turned by as much more as that lens is wider, which keeps the
      // star behind Earth behind Earth.
      const qMoon = moon.getWorldQuaternion(new Quaternion())
      const earthWorld = bigEarth.getWorldPosition(new Vector3())
      const seen = earthWorld.clone().sub(camera.position).normalize().applyQuaternion(camera.quaternion.clone().invert())
      const wider = Math.tan((SKY_FOV / 2) * DEG) / Math.tan((camera.fov / 2) * DEG)
      const drawn = new Vector3(seen.x * wider, seen.y * wider, seen.z).normalize().applyQuaternion(camera.quaternion)
      const turn = new Quaternion().setFromUnitVectors(earthWorld.normalize(), drawn)
      sky.group.quaternion.copy(turn).multiply(qMoon).multiply(skyAtSite)
      sky.setOpacity(state.space ?? 0)
    } else if (sky) {
      // The sky turns a little with the Moon, for depth; it is far away.
      sky.group.rotation.set(state.tilt * 0.15, (state.spin + spinExtra) * 0.12 + state.sunAz * 0.015, 0)
    }
    sunSoft.position.set(Math.sin(state.sunAz - 0.38) * 10, 0.3, Math.cos(state.sunAz - 0.38) * 10)
    earthMat.opacity = state.earth
    earth.visible = state.earth > 0.01
    if (!groundReady) return
    // With the ground, the sky is black while the viewer is out in space and
    // clears to the page as the Moon is reached.
    if (withGround) renderer.setClearColor(0x000000, state.space ?? 0)
    renderer.clear()
    if (sky && (!withGround || (state.space ?? 0) > 0.001)) {
      // Same direction and the same shift on screen, so what is behind the Moon stays behind it.
      skyCam.quaternion.copy(camera.quaternion)
      skyCam.setViewOffset(w, h, dx, 0, w, h)
      skyCam.updateProjectionMatrix()
      renderer.render(skyScene, skyCam)
      renderer.clearDepth()
    }
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
      globeMat.dispose()
      capMaterial.map?.dispose()
      capMaterial.dispose()
      earthMat.dispose()
      bigEarth.geometry.dispose()
      bigEarthMat.dispose()
      clouds.geometry.dispose()
      cloudMat.dispose()
      air.geometry.dispose()
      ;(air.material as Material).dispose()
      ground?.dispose()
      sky?.dispose()
      renderer.dispose()
    },
  }
}
