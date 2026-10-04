import {
  AmbientLight,
  BufferGeometry,
  DirectionalLight,
  Float32BufferAttribute,
  Group,
  LineBasicMaterial,
  LineLoop,
  Line,
  Mesh,
  MeshBasicMaterial,
  MeshStandardMaterial,
  PerspectiveCamera,
  Scene,
  SphereGeometry,
  SRGBColorSpace,
  Vector3,
  WebGLRenderer,
} from 'three'
import { capGeometry, poleRelief, token } from '../landing/moonScene'
import { moonSurface, SURFACE_TURN } from '../landing/space'
import { easeOut } from '../hooks/useMotion'
import type { SceneFactory } from './SceneFrame'

/**
 * The target globe on a mission's home: the Moon turned to the landing spot,
 * with the spot marked and the circle at 80°S. The surface is NASA's LRO
 * wide-angle camera mosaic, and inside the circle the LOLA relief (the same
 * tiles the Map draws). The light is for the picture, not for any date: the
 * Surface step has the Sun for the mission's own days. The caption under the
 * scene says so.
 *
 * Moon-fixed axes as the front page's Moon: +y is north, longitude 0 is +z,
 * east toward +x. Turning the Moon by -longitude about y and by the latitude
 * about x brings the spot to face the camera.
 */
export interface GlobeProps {
  latDeg: number
  lonDeg: number
  tileUrl: (z: number, x: number, y: number) => string
}

const DEG = Math.PI / 180
const ARRIVE_MS = 1800

const at = (latDeg: number, lonDeg: number, r: number) =>
  new Vector3(Math.cos(latDeg * DEG) * Math.sin(lonDeg * DEG), Math.sin(latDeg * DEG), Math.cos(latDeg * DEG) * Math.cos(lonDeg * DEG)).multiplyScalar(r)

export const createTargetGlobe: SceneFactory<GlobeProps> = async (canvas, props, { reduced }) => {
  const renderer = new WebGLRenderer({ canvas, antialias: true, alpha: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.outputColorSpace = SRGBColorSpace
  const scene = new Scene()
  const camera = new PerspectiveCamera(30, 1, 0.01, 50)
  camera.position.set(0, 0, 4.1)

  const moon = new Group()
  scene.add(moon)
  const globeMat = new MeshStandardMaterial({ color: 0x8e8e8e, roughness: 1, metalness: 0 })
  const globe = new Mesh(new SphereGeometry(1, 96, 48), globeMat)
  globe.rotation.y = SURFACE_TURN
  moon.add(globe)
  moonSurface(globeMat, () => draw())
  const capMat = new MeshStandardMaterial({ roughness: 1, metalness: 0, transparent: true, opacity: 0, emissiveIntensity: 0.22 })
  const cap = new Mesh(capGeometry(1.0015), capMat)
  moon.add(cap)

  // The light is the picture's, from the upper left of the frame; ink lights the night side faintly.
  scene.add(new AmbientLight(token('--color-ink-3', '#8d99a5'), 0.35))
  const key = new DirectionalLight(0xffffff, 3.2)
  key.position.set(-4, 2.5, 4)
  scene.add(key)

  // The circle at 80°S, where the real terrain begins.
  const ringPts: number[] = []
  for (let i = 0; i <= 180; i++) {
    const p = at(-80, (i / 180) * 360, 1.004)
    ringPts.push(p.x, p.y, p.z)
  }
  const ringGeo = new BufferGeometry()
  ringGeo.setAttribute('position', new Float32BufferAttribute(ringPts, 3))
  const ringMat = new LineBasicMaterial({ color: token('--color-ink-3', '#8d99a5'), transparent: true, opacity: 0.7 })
  moon.add(new LineLoop(ringGeo, ringMat))

  // The spot: a short stalk and a bead in ink, standing off the surface so the relief never hides it.
  const ink = token('--color-ink', '#e6ebf0')
  const stalkGeo = new BufferGeometry()
  const stalkMat = new LineBasicMaterial({ color: ink })
  const stalk = new Line(stalkGeo, stalkMat)
  moon.add(stalk)
  const beadGeo = new SphereGeometry(0.022, 20, 12)
  const beadMat = new MeshBasicMaterial({ color: ink })
  const bead = new Mesh(beadGeo, beadMat)
  moon.add(bead)

  let target = { lat: props.latDeg, lon: props.lonDeg }
  const place = () => {
    const a = at(target.lat, target.lon, 1.0)
    const b = at(target.lat, target.lon, 1.09)
    stalkGeo.setFromPoints([a, b])
    bead.position.copy(b)
  }
  place()

  let disposed = false
  void poleRelief(props.tileUrl).then((t) => {
    if (!t || disposed) return
    capMat.map = t
    capMat.emissiveMap = t
    capMat.emissive.setRGB(1, 1, 1)
    capMat.opacity = 1
    capMat.needsUpdate = true
    draw()
  })

  // Facing the spot: a little off it to begin with, turning onto it as the scene arrives.
  const face = () => ({ tilt: target.lat * DEG * 0.92, spin: -target.lon * DEG })
  const start = { tilt: face().tilt * 0.35 + 0.15, spin: face().spin + 0.9 }
  let t0 = 0
  let raf = 0

  const size = () => {
    const w = canvas.clientWidth || 1
    const h = canvas.clientHeight || 1
    renderer.setSize(w, h, false)
    camera.aspect = w / h
    // Keep the whole globe in frame whatever the shape.
    camera.position.z = camera.aspect < 1 ? 4.1 / camera.aspect : 4.1
    camera.updateProjectionMatrix()
  }

  const draw = () => {
    if (disposed) return
    const end = face()
    const k = reduced || !t0 ? 1 : easeOut(Math.min(1, (performance.now() - t0) / ARRIVE_MS))
    moon.rotation.set(start.tilt + (end.tilt - start.tilt) * k, 0, 0)
    moon.rotateY(start.spin + (end.spin - start.spin) * k)
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

  return {
    update: (p) => {
      if (p.latDeg === target.lat && p.lonDeg === target.lon) return
      target = { lat: p.latDeg, lon: p.lonDeg }
      place()
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
      cap.geometry.dispose()
      capMat.map?.dispose()
      capMat.dispose()
      ringGeo.dispose()
      ringMat.dispose()
      stalkGeo.dispose()
      stalkMat.dispose()
      beadGeo.dispose()
      beadMat.dispose()
      renderer.dispose()
      renderer.forceContextLoss()
    },
  }
}
