import {
  AmbientLight,
  CanvasTexture,
  CatmullRomCurve3,
  Color,
  DirectionalLight,
  Mesh,
  MeshBasicMaterial,
  MeshStandardMaterial,
  PerspectiveCamera,
  Scene,
  SphereGeometry,
  Sprite,
  SpriteMaterial,
  SRGBColorSpace,
  TubeGeometry,
  Vector3,
  WebGLRenderer,
} from 'three'
import { token } from '../landing/moonScene'
import type { SceneFactory } from './SceneFrame'

/**
 * The path to the Moon on Trip: the lander's flown trajectory as NASA
 * reconstructed it (the section's own orbit file, Earth-centred EME2000),
 * at true distance. The path is amber where the lander was in sunlight and
 * grey where it was in shadow, from the section's own samples; the burns are
 * marked; nothing is drawn across a gap in the reconstruction. Earth sits at
 * the centre and the Moon where the trip ends, both drawn three times their
 * size so they can be seen at this distance. The path is drawn as seen from
 * Earth, so the lander's laps of the Moon show as a wavy line: the Moon was
 * moving on its own way round Earth under them. The lander moves along the
 * path as the card scrolls through the screen.
 */
export interface PathProps {
  /** The orbit file as CSV: time_utc, stretch, x_km, y_km, z_km, … */
  csv: string
  /** The section's samples: whether the lander was lit at each time. */
  light: { t: number; lit: boolean }[]
  burns: number[]
  /** 0 at the top of the card entering the screen, 1 at its foot leaving it. */
  progress: number
}

const UNIT_KM = 10_000
const BODY_SCALE = 3
const R_EARTH_KM = 6371
const R_MOON_KM = 1737.4

interface State {
  t: number
  stretch: string
  p: Vector3
}

export function parseStates(csv: string): State[] {
  const out: State[] = []
  for (const line of csv.split('\n')) {
    if (!line || line.startsWith('#') || line.startsWith('time_utc')) continue
    const [t, stretch, x, y, z] = line.split(',')
    const ms = Date.parse(t)
    if (Number.isNaN(ms)) continue
    // EME2000 has z toward the north celestial pole; the scene's up is y.
    out.push({ t: ms, stretch, p: new Vector3(Number(x), Number(z), -Number(y)).divideScalar(UNIT_KM) })
  }
  return out
}

function label(text: string, color: Color): Sprite {
  const c = document.createElement('canvas')
  c.width = 256
  c.height = 64
  const g = c.getContext('2d')!
  g.font = '600 30px Archivo, "Helvetica Neue", sans-serif'
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  g.fillStyle = `#${color.getHexString()}`
  g.fillText(text, 128, 34)
  const t = new CanvasTexture(c)
  t.colorSpace = SRGBColorSpace
  const s = new Sprite(new SpriteMaterial({ map: t, depthTest: false, transparent: true }))
  s.scale.set(6, 1.5, 1)
  return s
}

export const createTripPath: SceneFactory<PathProps> = async (canvas, props, { reduced }) => {
  const states = parseStates(props.csv)
  if (states.length < 2) throw new Error('no trajectory')

  const renderer = new WebGLRenderer({ canvas, antialias: true, alpha: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.outputColorSpace = SRGBColorSpace
  const scene = new Scene()
  const camera = new PerspectiveCamera(32, 1, 0.1, 2000)
  const disposables: { dispose: () => void }[] = []
  const keep = <T extends { dispose: () => void }>(x: T) => (disposables.push(x), x)
  const c = {
    sun: token('--color-sun-fill', '#f2a33c'),
    dark: token('--color-hatch', '#5f6a75'),
    earth: token('--color-earth-fill', '#4fc6e0'),
    moon: token('--color-terrain-high', '#8a949e'),
    ink: token('--color-ink', '#e6ebf0'),
    ink3: token('--color-ink-3', '#8d99a5'),
  }

  scene.add(new AmbientLight(0xffffff, 0.9))
  const key = new DirectionalLight(0xffffff, 1.6)
  key.position.set(-40, 30, 60)
  scene.add(key)

  // Earth at the centre, the Moon where the trip ends.
  const earth = new Mesh(keep(new SphereGeometry((R_EARTH_KM / UNIT_KM) * BODY_SCALE, 48, 24)), keep(new MeshStandardMaterial({ color: c.earth, roughness: 0.8 })))
  scene.add(earth)
  const end = states[states.length - 1].p
  const moon = new Mesh(keep(new SphereGeometry((R_MOON_KM / UNIT_KM) * BODY_SCALE, 40, 20)), keep(new MeshStandardMaterial({ color: c.moon, roughness: 1 })))
  moon.position.copy(end)
  scene.add(moon)
  const earthLabel = label('Earth', c.ink3)
  const moonLabel = label('Moon', c.ink3)
  keep(earthLabel.material.map!)
  keep(earthLabel.material)
  keep(moonLabel.material.map!)
  keep(moonLabel.material)
  scene.add(earthLabel, moonLabel)

  // The path, a tube per run of sunlight or shadow inside each covered stretch.
  const lit = (t: number) => {
    const L = props.light
    if (!L.length) return true
    let lo = 0
    let hi = L.length - 1
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1
      if (L[mid].t <= t) lo = mid
      else hi = mid
    }
    return (Math.abs(L[lo].t - t) <= Math.abs(L[hi].t - t) ? L[lo] : L[hi]).lit
  }
  const litMat = keep(new MeshBasicMaterial({ color: c.sun }))
  const darkMat = keep(new MeshBasicMaterial({ color: c.dark }))
  let run: Vector3[] = []
  let runLit = lit(states[0].t)
  let runStretch = states[0].stretch
  const flush = () => {
    if (run.length >= 2) {
      const curve = new CatmullRomCurve3(run)
      const geo = keep(new TubeGeometry(curve, Math.min(800, run.length * 2), 0.09, 6, false))
      scene.add(new Mesh(geo, runLit ? litMat : darkMat))
    }
  }
  for (let i = 0; i < states.length; i++) {
    const s = states[i]
    const l = lit(s.t)
    if (s.stretch !== runStretch) {
      // A gap in the reconstruction: nothing is drawn across it.
      flush()
      run = [s.p]
      runLit = l
      runStretch = s.stretch
      continue
    }
    if (l !== runLit) {
      run.push(s.p)
      flush()
      run = [s.p]
      runLit = l
      continue
    }
    run.push(s.p)
  }
  flush()

  // The burns, as small ink beads on the path.
  const near = (t: number) => {
    let best = states[0]
    for (const s of states) if (Math.abs(s.t - t) < Math.abs(best.t - t)) best = s
    return best.p
  }
  const beadGeo = keep(new SphereGeometry(0.22, 16, 10))
  const beadMat = keep(new MeshBasicMaterial({ color: c.ink }))
  for (const b of props.burns) {
    if (b < states[0].t || b > states[states.length - 1].t) continue
    const m = new Mesh(beadGeo, beadMat)
    m.position.copy(near(b))
    scene.add(m)
  }

  // The lander, moved along the path by the scroll.
  const lander = new Mesh(keep(new SphereGeometry(0.42, 20, 12)), keep(new MeshBasicMaterial({ color: c.ink })))
  scene.add(lander)
  const halo = new Mesh(keep(new SphereGeometry(0.8, 20, 12)), keep(new MeshBasicMaterial({ color: c.ink, transparent: true, opacity: 0.18 })))
  scene.add(halo)

  // Look down on the plane the trip lies in, tipped back a little, with all
  // of it in frame: Earth to the left, the Moon to the right.
  const normal = new Vector3()
  for (let i = 1; i < states.length; i++) normal.add(new Vector3().crossVectors(states[i - 1].p, states[i].p))
  if (normal.lengthSq() < 1e-9) normal.set(0, 1, 0)
  normal.normalize()
  const across = end.clone().sub(normal.clone().multiplyScalar(end.dot(normal))).normalize()
  const up = new Vector3().crossVectors(normal, across).normalize()
  // The smallest box in that plane that holds Earth, the Moon and the whole path.
  let x0 = 0
  let x1 = 0
  let y0 = 0
  let y1 = 0
  for (const s of states) {
    const x = s.p.dot(across)
    const y = s.p.dot(up)
    x0 = Math.min(x0, x)
    x1 = Math.max(x1, x)
    y0 = Math.min(y0, y)
    y1 = Math.max(y1, y)
  }
  const PAD = 5
  const centre = across
    .clone()
    .multiplyScalar((x0 + x1) / 2)
    .add(up.clone().multiplyScalar((y0 + y1) / 2))
  const halfW = (x1 - x0) / 2 + PAD
  const halfH = (y1 - y0) / 2 + PAD
  const TILT = 24 * (Math.PI / 180)
  const from = normal.clone().multiplyScalar(Math.cos(TILT)).sub(up.clone().multiplyScalar(Math.sin(TILT)))

  const size = () => {
    const w = canvas.clientWidth || 1
    const h = canvas.clientHeight || 1
    renderer.setSize(w, h, false)
    camera.aspect = w / h
    const t = Math.tan((camera.fov / 2) * (Math.PI / 180))
    // Far enough to hold the box's height, and its width at this shape of frame.
    const dist = Math.max(halfH / t, halfW / (t * camera.aspect))
    camera.position.copy(centre).add(from.clone().multiplyScalar(dist))
    camera.up.copy(up)
    camera.lookAt(centre)
    camera.updateProjectionMatrix()
  }

  const earthR = (R_EARTH_KM / UNIT_KM) * BODY_SCALE
  const moonR = (R_MOON_KM / UNIT_KM) * BODY_SCALE
  let progress = reduced ? 1 : props.progress
  const place = () => {
    const i = Math.round(Math.max(0, Math.min(1, progress)) * (states.length - 1))
    lander.position.copy(states[i].p)
    halo.position.copy(states[i].p)
    // Each name over its body, clear of it.
    earthLabel.position.copy(up).multiplyScalar(earthR + 1.8)
    moonLabel.position.copy(end).add(up.clone().multiplyScalar(moonR + 1.8))
  }
  let raf = 0
  const draw = () => {
    raf = 0
    place()
    renderer.render(scene, camera)
  }
  const request = () => {
    if (!raf) raf = requestAnimationFrame(draw)
  }
  size()
  request()

  return {
    update: (p) => {
      if (!reduced) progress = p.progress
      request()
    },
    resize: () => {
      size()
      request()
    },
    dispose: () => {
      cancelAnimationFrame(raf)
      disposables.forEach((d) => d.dispose())
      renderer.dispose()
      renderer.forceContextLoss()
    },
  }
}
