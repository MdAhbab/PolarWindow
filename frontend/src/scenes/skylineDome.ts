import {
  BufferGeometry,
  CanvasTexture,
  Color,
  DoubleSide,
  Float32BufferAttribute,
  Line,
  LineBasicMaterial,
  LineDashedMaterial,
  LineLoop,
  Mesh,
  MeshBasicMaterial,
  PerspectiveCamera,
  Points,
  PointsMaterial,
  Scene,
  SphereGeometry,
  Sprite,
  SpriteMaterial,
  SRGBColorSpace,
  Vector3,
  WebGLRenderer,
} from 'three'
import { token } from '../landing/moonScene'
import { easeOut } from '../hooks/useMotion'
import type { TrackSample } from '../lib/types'
import type { SceneFactory } from './SceneFrame'

/**
 * The skyline dome: standing at the site and looking out. The site's own
 * skyline (one height for every degree of bearing, from the terrain map) is
 * a wall around the viewer; the Sun's path and Earth's small loop over the
 * chosen dates are drawn in the sky behind it, so the wall hides them where
 * the terrain does, and what is hidden shows faintly over it; the Sun
 * and Earth sit where they are at the date slider's moment. The dashed ring
 * is level ground, where a smooth Moon's horizon would be.
 *
 * Heights are drawn six times taller than they are: near the pole the whole
 * story happens within a few degrees of level, which at true scale would be
 * a hairline. The caption under the scene says so. Drag to look around.
 */
export interface DomeProps {
  elDeg: Float32Array
  sun: TrackSample[]
  earth: TrackSample[]
  /** Model hours of the date slider's moment. */
  nowH: number
}

const DEG = Math.PI / 180
/** Said in words under the scene (words.ts): change both together. */
export const DOME_EXAGGERATION = 6
const R = 10
const FLOOR_DEG = -78

/** A direction from the viewer: bearing clockwise from north (-z), elevation drawn exaggerated. */
function dir(azDeg: number, elDeg: number, r: number, exaggerate = true): Vector3 {
  const e = Math.max(-88, Math.min(88, exaggerate ? elDeg * DOME_EXAGGERATION : elDeg)) * DEG
  const a = azDeg * DEG
  return new Vector3(Math.sin(a) * Math.cos(e), Math.sin(e), -Math.cos(a) * Math.cos(e)).multiplyScalar(r)
}

function label(text: string, color: Color): Sprite {
  const c = document.createElement('canvas')
  c.width = 64
  c.height = 64
  const g = c.getContext('2d')!
  g.font = '600 34px "IBM Plex Mono", ui-monospace, monospace'
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  g.fillStyle = `#${color.getHexString()}`
  g.fillText(text, 32, 34)
  const t = new CanvasTexture(c)
  t.colorSpace = SRGBColorSpace
  const s = new Sprite(new SpriteMaterial({ map: t, depthTest: false, transparent: true }))
  s.scale.setScalar(0.9)
  return s
}

export const createSkylineDome: SceneFactory<DomeProps> = async (canvas, props, { reduced }) => {
  const renderer = new WebGLRenderer({ canvas, antialias: true, alpha: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.outputColorSpace = SRGBColorSpace
  const scene = new Scene()
  const camera = new PerspectiveCamera(62, 1, 0.1, 100)
  const disposables: { dispose: () => void }[] = []
  const keep = <T extends { dispose: () => void }>(x: T) => (disposables.push(x), x)

  const c = {
    low: token('--color-terrain-low', '#262d34'),
    high: token('--color-terrain-high', '#8a949e'),
    ink3: token('--color-ink-3', '#8d99a5'),
    sun: token('--color-sun-fill', '#f2a33c'),
    earth: token('--color-earth-fill', '#4fc6e0'),
  }

  // The wall: from the floor up to the skyline, bearing by bearing, and its top edge.
  const wallGeo = keep(new BufferGeometry())
  const edgeGeo = keep(new BufferGeometry())
  const buildWall = (el: Float32Array) => {
    const n = el.length
    const pos: number[] = []
    const idx: number[] = []
    const edge: number[] = []
    for (let b = 0; b <= n; b++) {
      const az = (b * 360) / n
      const top = dir(az, el[b % n], R)
      const bottom = dir(az, FLOOR_DEG, R, false)
      pos.push(top.x, top.y, top.z, bottom.x, bottom.y, bottom.z)
      edge.push(top.x, top.y, top.z)
      if (b < n) {
        const i = b * 2
        idx.push(i, i + 1, i + 2, i + 1, i + 3, i + 2)
      }
    }
    wallGeo.setAttribute('position', new Float32BufferAttribute(pos, 3))
    wallGeo.setIndex(idx)
    edgeGeo.setAttribute('position', new Float32BufferAttribute(edge, 3))
  }
  buildWall(props.elDeg)
  scene.add(new Mesh(wallGeo, keep(new MeshBasicMaterial({ color: c.low, side: DoubleSide }))))
  scene.add(new Line(edgeGeo, keep(new LineBasicMaterial({ color: c.high }))))

  // Level ground: where a smooth Moon's horizon would be.
  const level: Vector3[] = []
  for (let i = 0; i <= 180; i++) level.push(dir(i * 2, 0, R * 1.002))
  const levelGeo = keep(new BufferGeometry().setFromPoints(level))
  const levelLine = new LineLoop(levelGeo, keep(new LineDashedMaterial({ color: c.ink3, dashSize: 0.25, gapSize: 0.25, transparent: true, opacity: 0.8 })))
  levelLine.computeLineDistances()
  scene.add(levelLine)

  // The compass, just below level.
  const compass = [
    ['N', 0],
    ['E', 90],
    ['S', 180],
    ['W', 270],
  ] as const
  for (const [t, az] of compass) {
    const s = label(t, c.ink3)
    keep(s.material.map!)
    keep(s.material)
    s.position.copy(dir(az, -1.6, R * 0.9))
    scene.add(s)
  }

  // A round dot for the paths: a path is drawn as its samples, so it has
  // weight on screen (a WebGL line is one pixel wide whatever is asked).
  const dotTex = (() => {
    const d = document.createElement('canvas')
    d.width = d.height = 32
    const g = d.getContext('2d')!
    g.beginPath()
    g.arc(16, 16, 14, 0, Math.PI * 2)
    g.fillStyle = '#fff'
    g.fill()
    return keep(new CanvasTexture(d))
  })()

  // A body's path over the dates: solid where it is seen, faint where the
  // terrain hides it (drawn over the wall), and the body itself at the moment.
  const path = (color: Color) => {
    const geo = keep(new BufferGeometry())
    const seen = new Points(geo, keep(new PointsMaterial({ color, size: 3.5, sizeAttenuation: false, map: dotTex, transparent: true, alphaTest: 0.4 })))
    const hidden = new Points(geo, keep(new PointsMaterial({ color, size: 2.5, sizeAttenuation: false, map: dotTex, transparent: true, opacity: 0.32, depthTest: false })))
    hidden.renderOrder = 1
    const disc = new Mesh(keep(new SphereGeometry(0.34, 24, 16)), keep(new MeshBasicMaterial({ color })))
    const ghost = new Mesh(disc.geometry, keep(new MeshBasicMaterial({ color, transparent: true, opacity: 0.3, depthTest: false })))
    ghost.renderOrder = 1
    scene.add(seen, hidden, disc, ghost)
    let last: TrackSample[] | null = null
    const index = (nowH: number) => {
      if (!last?.length) return -1
      const step = last.length > 1 ? last[1].tH - last[0].tH : 1
      return Math.max(0, Math.min(last.length - 1, Math.round((nowH - last[0].tH) / step)))
    }
    return {
      set(samples: TrackSample[], nowH: number) {
        if (samples !== last) {
          last = samples
          geo.setFromPoints(samples.map((s) => dir(s.azDeg, s.elDeg, R * 1.04)))
        }
        const i = index(nowH)
        disc.visible = ghost.visible = i >= 0
        if (i < 0) return
        const p = dir(samples[i].azDeg, samples[i].elDeg, R * 1.03)
        disc.position.copy(p)
        ghost.position.copy(p)
      },
      az(nowH: number) {
        const i = index(nowH)
        return i < 0 ? 0 : last![i].azDeg
      },
    }
  }
  const sun = path(c.sun)
  const earth = path(c.earth)
  let current = props
  sun.set(props.sun, props.nowH)
  earth.set(props.earth, props.nowH)

  // Where the viewer looks: toward the Sun at the slider's moment, a little above level.
  let yaw = sun.az(props.nowH)
  let pitch = 6
  const arriveFrom = yaw - 50
  let t0 = reduced ? 0 : performance.now()
  let raf = 0

  const size = () => {
    const w = canvas.clientWidth || 1
    const h = canvas.clientHeight || 1
    renderer.setSize(w, h, false)
    camera.aspect = w / h
    camera.updateProjectionMatrix()
  }
  const draw = () => {
    const k = t0 ? easeOut(Math.min(1, (performance.now() - t0) / 1600)) : 1
    const y = arriveFrom + (yaw - arriveFrom) * k
    camera.position.set(0, 0, 0)
    camera.lookAt(dir(y, pitch, 1, false))
    renderer.render(scene, camera)
    if (k >= 1) t0 = 0
    return k
  }
  const frame = () => {
    raf = 0
    if (draw() < 1) raf = requestAnimationFrame(frame)
  }
  const request = () => {
    if (!raf) raf = requestAnimationFrame(frame)
  }

  // Drag to look around: sideways turns, up and down tilts a little.
  let drag: { x: number; y: number; yaw: number; pitch: number } | null = null
  const down = (e: PointerEvent) => {
    t0 = 0
    drag = { x: e.clientX, y: e.clientY, yaw, pitch }
    canvas.setPointerCapture(e.pointerId)
  }
  const move = (e: PointerEvent) => {
    if (!drag) return
    const per = camera.fov / (canvas.clientHeight || 1)
    yaw = drag.yaw - (e.clientX - drag.x) * per
    pitch = Math.max(-20, Math.min(40, drag.pitch + (e.clientY - drag.y) * per))
    request()
  }
  const up = () => {
    drag = null
  }
  canvas.addEventListener('pointerdown', down)
  canvas.addEventListener('pointermove', move)
  canvas.addEventListener('pointerup', up)
  canvas.addEventListener('pointercancel', up)
  canvas.style.cursor = 'grab'

  size()
  request()

  return {
    update: (p) => {
      if (p.elDeg !== current.elDeg) buildWall(p.elDeg)
      sun.set(p.sun, p.nowH)
      earth.set(p.earth, p.nowH)
      current = p
      request()
    },
    resize: () => {
      size()
      request()
    },
    dispose: () => {
      cancelAnimationFrame(raf)
      canvas.removeEventListener('pointerdown', down)
      canvas.removeEventListener('pointermove', move)
      canvas.removeEventListener('pointerup', up)
      canvas.removeEventListener('pointercancel', up)
      canvas.style.cursor = ''
      disposables.forEach((d) => d.dispose())
      renderer.dispose()
    },
  }
}
