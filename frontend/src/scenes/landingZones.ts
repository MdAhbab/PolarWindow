import {
  AmbientLight,
  BufferGeometry,
  CanvasTexture,
  DirectionalLight,
  Group,
  Line,
  LineBasicMaterial,
  LineLoop,
  type Material,
  Mesh,
  MeshBasicMaterial,
  MeshStandardMaterial,
  PerspectiveCamera,
  Scene,
  SphereGeometry,
  Sprite,
  SpriteMaterial,
  SRGBColorSpace,
  Vector3,
  WebGLRenderer,
} from 'three'
import { atmosphere } from '../landing/earthrise'
import { earthSurface, SURFACE_TURN } from '../landing/space'
import { easeOut } from '../hooks/useMotion'
import type { SceneFactory } from './SceneFrame'

/**
 * The landing zones on Return: Earth turned to where the booster comes down
 * and where a capsule splashes down. The surface is NASA's Blue Marble. Each
 * zone is a bead on a short stalk with its name, and a ring of the zone's own
 * size when that is published (a ring a few kilometres across is smaller than
 * the bead, and then the bead is the mark). The light is for the picture, not
 * for the hour of the landing: whether a splashdown is in daylight is said in
 * its own row. The caption under the scene says so.
 *
 * Earth-fixed axes: +y is north, longitude 0 is +z, east toward +x.
 */
export interface Zone {
  key: string
  /** Its name on the picture. */
  label: string
  latDeg: number
  lonDeg: number
  /** The zone's radius, km; null when its size is not published. */
  radiusKm: number | null
}
export interface ZonesProps {
  zones: Zone[]
}

const DEG = Math.PI / 180
const R_EARTH_KM = 6371
const ARRIVE_MS = 1800

const at = (latDeg: number, lonDeg: number, r = 1) =>
  new Vector3(Math.cos(latDeg * DEG) * Math.sin(lonDeg * DEG), Math.sin(latDeg * DEG), Math.cos(latDeg * DEG) * Math.cos(lonDeg * DEG)).multiplyScalar(r)

/** A name beside its bead: light letters with a dark edge, so it reads over sea, cloud or land. */
function nameTag(text: string): Sprite {
  const c = document.createElement('canvas')
  c.width = 512
  c.height = 96
  const g = c.getContext('2d')!
  g.font = '600 44px Archivo, "Helvetica Neue", sans-serif'
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  g.lineJoin = 'round'
  g.lineWidth = 9
  g.strokeStyle = 'rgba(8, 10, 13, 0.85)'
  g.strokeText(text, 256, 50)
  g.fillStyle = '#ffffff'
  g.fillText(text, 256, 50)
  const t = new CanvasTexture(c)
  t.colorSpace = SRGBColorSpace
  const s = new Sprite(new SpriteMaterial({ map: t, depthTest: false, transparent: true }))
  s.scale.set(0.4, 0.075, 1)
  return s
}

export const createLandingZones: SceneFactory<ZonesProps> = async (canvas, props, { reduced }) => {
  if (!props.zones.length) throw new Error('no zone to show')
  const renderer = new WebGLRenderer({ canvas, antialias: true, alpha: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.outputColorSpace = SRGBColorSpace
  const scene = new Scene()
  const camera = new PerspectiveCamera(30, 1, 0.01, 50)

  const earth = new Group()
  scene.add(earth)
  const globeMat = new MeshStandardMaterial({ color: 0x2a4d7a, roughness: 0.9, metalness: 0 })
  const globe = new Mesh(new SphereGeometry(1, 96, 48), globeMat)
  globe.rotation.y = SURFACE_TURN
  earth.add(globe)
  const air = atmosphere(1)
  earth.add(air)

  // The light is the picture's, from the upper left of the frame.
  scene.add(new AmbientLight(0xffffff, 0.55))
  const key = new DirectionalLight(0xffffff, 2.6)
  key.position.set(-3, 2.5, 5)
  scene.add(key)

  const disposables: { dispose: () => void }[] = []
  const keep = <T extends { dispose: () => void }>(x: T) => (disposables.push(x), x)
  const white = 0xffffff
  const stalkMat = keep(new LineBasicMaterial({ color: white }))
  const ringMat = keep(new LineBasicMaterial({ color: white, transparent: true, opacity: 0.85 }))
  const beadGeo = keep(new SphereGeometry(0.016, 20, 12))
  const beadMat = keep(new MeshBasicMaterial({ color: white }))

  let marks = new Group()
  let tags: { sprite: Sprite; at: Vector3; lift: number }[] = []
  let centre = new Vector3(0, 0, 1)
  let spread = 0
  const build = (zones: Zone[]) => {
    earth.remove(marks)
    tags.forEach((t) => scene.remove(t.sprite))
    tags = []
    marks = new Group()
    const sum = new Vector3()
    zones.forEach((z, i) => {
      const p = at(z.latDeg, z.lonDeg)
      sum.add(p)
      const top = p.clone().multiplyScalar(1.07)
      marks.add(new Line(keep(new BufferGeometry().setFromPoints([p.clone().multiplyScalar(1.001), top])), stalkMat))
      const bead = new Mesh(beadGeo, beadMat)
      bead.position.copy(top)
      marks.add(bead)
      const tag = nameTag(z.label)
      keep(tag.material.map!)
      keep(tag.material)
      // The name stands clear of its bead on the screen, not along the stalk: over it,
      // and under it for a second zone, so two close together do not sit on each other.
      tags.push({ sprite: tag, at: top, lift: i % 2 ? -0.075 : 0.075 })
      scene.add(tag)
      if (z.radiusKm) {
        const a = z.radiusKm / R_EARTH_KM
        const north = new Vector3(0, 1, 0)
        const east = new Vector3().crossVectors(north, p).normalize()
        const up = new Vector3().crossVectors(p, east).normalize()
        const pts: Vector3[] = []
        for (let k = 0; k < 96; k++) {
          const b = (k / 96) * Math.PI * 2
          pts.push(
            p
              .clone()
              .multiplyScalar(Math.cos(a))
              .add(east.clone().multiplyScalar(Math.sin(a) * Math.cos(b)))
              .add(up.clone().multiplyScalar(Math.sin(a) * Math.sin(b)))
              .multiplyScalar(1.003),
          )
        }
        marks.add(new LineLoop(keep(new BufferGeometry().setFromPoints(pts)), ringMat))
      }
    })
    earth.add(marks)
    centre = sum.lengthSq() > 1e-6 ? sum.normalize() : at(zones[0].latDeg, zones[0].lonDeg)
    spread = Math.max(...zones.map((z) => at(z.latDeg, z.lonDeg).angleTo(centre)))
  }
  build(props.zones)

  let disposed = false
  earthSurface(globeMat, () => draw(), 1.25)

  // Facing the middle of the zones: a little off it to begin with, turning onto it as the scene arrives.
  const face = () => ({ tilt: Math.asin(Math.max(-1, Math.min(1, centre.y))) * 0.9, spin: -Math.atan2(centre.x, centre.z) })
  const start = { tilt: face().tilt * 0.4, spin: face().spin + 0.8 }
  let t0 = 0
  let raf = 0

  const size = () => {
    const w = canvas.clientWidth || 1
    const h = canvas.clientHeight || 1
    renderer.setSize(w, h, false)
    camera.aspect = w / h
    // Close enough that the region fills the frame; back to the whole Earth when the zones are far apart.
    const near = spread > 0.6 ? 4.1 : 2.9
    camera.position.set(0, 0, camera.aspect < 1 ? near / Math.max(0.6, camera.aspect) : near)
    camera.updateProjectionMatrix()
  }

  const draw = () => {
    if (disposed) return
    const end = face()
    const k = reduced || !t0 ? 1 : easeOut(Math.min(1, (performance.now() - t0) / ARRIVE_MS))
    earth.rotation.set(start.tilt + (end.tilt - start.tilt) * k, 0, 0)
    earth.rotateY(start.spin + (end.spin - start.spin) * k)
    earth.updateMatrixWorld()
    for (const t of tags) {
      t.sprite.position.copy(t.at).applyMatrix4(earth.matrixWorld)
      t.sprite.position.y += t.lift
    }
    renderer.render(scene, camera)
    return k
  }

  const frame = () => {
    raf = 0
    if ((draw() ?? 1) < 1) raf = requestAnimationFrame(frame)
  }

  size()
  if (reduced) draw()
  else {
    t0 = performance.now()
    raf = requestAnimationFrame(frame)
  }

  let shown = JSON.stringify(props.zones)
  return {
    update: (p) => {
      const next = JSON.stringify(p.zones)
      if (next === shown || !p.zones.length) return
      shown = next
      build(p.zones)
      size()
      draw()
    },
    resize: () => {
      size()
      draw()
    },
    dispose: () => {
      disposed = true
      cancelAnimationFrame(raf)
      globe.geometry.dispose()
      globeMat.dispose()
      air.geometry.dispose()
      ;(air.material as Material).dispose()
      disposables.forEach((d) => d.dispose())
      renderer.dispose()
    },
  }
}
