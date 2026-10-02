import {
  AdditiveBlending,
  BackSide,
  BufferAttribute,
  BufferGeometry,
  CanvasTexture,
  Color,
  Mesh,
  RepeatWrapping,
  ShaderMaterial,
  SphereGeometry,
  SRGBColorSpace,
} from 'three'
import terrainUrl from '../assets/space/earthrise.bin?url'
export { default as cloudsUrl } from '../assets/space/earth-clouds-1024.jpg'

/**
 * The light theme's first picture: Earth rising over the Moon's horizon, seen
 * from Connecting Ridge near the south pole.
 *
 * The ground is the LOLA heights around the site, as `render_earthrise.py`
 * samples them: a fan in front of a viewer 2 m above the ground, looking
 * toward Earth, with the Moon's curvature in it and the terrain's own shadows
 * for a low Sun from the right. Earth stands at the elevation it has there on
 * average, which puts it half over the site's real skyline, and is NASA's
 * Blue Marble under NASA's cloud layer. The sky is
 * black, with the Milky Way. The front page's Moon scene (moonScene.ts) puts
 * the ground on its globe and flies from it out to the whole Moon as the page
 * scrolls; this file holds the ground and Earth's air.
 *
 * The ground is in kilometres, in a frame with the viewer's eye at the origin,
 * Earth's direction along -z and up along +y.
 */
export interface EarthriseState {
  /** Where the view points above level, degrees. */
  pitch: number
  /** The lens's vertical field of view, degrees: narrow is a telephoto. */
  fov: number
  /** How far the viewer has risen above the summit, km. */
  lift: number
}

export interface Earthrise {
  state: EarthriseState
  render: () => void
  dispose: () => void
}

const DEG = Math.PI / 180

/** A fine, even grain for the regolith near the viewer; its mipmaps average it away with distance. */
export function regolith(): CanvasTexture {
  const n = 256
  const c = document.createElement('canvas')
  c.width = c.height = n
  const g = c.getContext('2d')!
  const img = g.createImageData(n, n)
  let s = 7
  const r = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 2 ** 32)
  for (let i = 0; i < n * n; i++) {
    const v = 214 + (r() - 0.5) * 60
    img.data[i * 4] = img.data[i * 4 + 1] = img.data[i * 4 + 2] = v
    img.data[i * 4 + 3] = 255
  }
  g.putImageData(img, 0, 0)
  // A sprinkle of small craters: a dark floor and a lit rim toward the Sun.
  for (let i = 0; i < 160; i++) {
    const x = r() * n
    const y = r() * n
    const rad = 1 + r() ** 3 * 9
    g.beginPath()
    g.arc(x, y, rad, 0, Math.PI * 2)
    g.fillStyle = `rgba(60,60,60,${0.12 + r() * 0.12})`
    g.fill()
    g.beginPath()
    g.arc(x, y, rad, -Math.PI * 0.6, Math.PI * 0.4)
    g.strokeStyle = `rgba(255,255,255,${0.1 + r() * 0.12})`
    g.lineWidth = Math.max(0.6, rad * 0.25)
    g.stroke()
  }
  const t = new CanvasTexture(c)
  t.wrapS = t.wrapT = RepeatWrapping
  t.colorSpace = SRGBColorSpace
  t.anisotropy = 8
  return t
}

export async function loadGround(): Promise<{
  geometry: BufferGeometry
  earthElDeg: number
  sunRelAzDeg: number
  sunElDeg: number
}> {
  const buf = await (await fetch(terrainUrl)).arrayBuffer()
  const head = new Float32Array(buf, 0, 8)
  const [nAz, nR, r0, r1, halfDeg, earthElDeg, sunRelAzDeg, sunElDeg] = Array.from(head)
  const count = nAz * nR
  const heights = new Int16Array(buf, 32, count)
  const light = new Uint8Array(buf, 32 + count * 2, count)
  const pos = new Float32Array(count * 3)
  const col = new Float32Array(count * 3)
  const uv = new Float32Array(count * 2)
  for (let i = 0; i < nR; i++) {
    const r = r0 * (r1 / r0) ** (i / (nR - 1))
    for (let j = 0; j < nAz; j++) {
      const k = i * nAz + j
      const a = (-halfDeg + (2 * halfDeg * j) / (nAz - 1)) * DEG
      const x = r * Math.sin(a)
      const z = -r * Math.cos(a)
      pos[k * 3] = x
      pos[k * 3 + 1] = heights[k] / 2000 // half metres to km
      pos[k * 3 + 2] = z
      // Shadow to sunlight, never quite black: the ground is lit faintly by Earth.
      const l = 0.035 + 0.965 * (light[k] / 255)
      col[k * 3] = col[k * 3 + 1] = col[k * 3 + 2] = l
      uv[k * 2] = x * 40
      uv[k * 2 + 1] = z * 40
    }
  }
  const idx = new Uint32Array((nR - 1) * (nAz - 1) * 6)
  let p = 0
  for (let i = 0; i < nR - 1; i++) {
    for (let j = 0; j < nAz - 1; j++) {
      const a = i * nAz + j
      const b = a + nAz
      // Counter-clockwise seen from above, so the ground faces up.
      idx[p++] = a
      idx[p++] = a + 1
      idx[p++] = b
      idx[p++] = a + 1
      idx[p++] = b + 1
      idx[p++] = b
    }
  }
  const geometry = new BufferGeometry()
  geometry.setAttribute('position', new BufferAttribute(pos, 3))
  geometry.setAttribute('uv', new BufferAttribute(uv, 2))
  geometry.setIndex(new BufferAttribute(idx, 1))
  geometry.computeVertexNormals()

  // Regolith shading, baked for the viewer at the origin: the Lommel-Seeliger
  // law, mu0 / (mu0 + mu), which keeps ground under a Sun two degrees high
  // bright where plain diffuse shading would leave it black, as the Moon looks
  // in photographs; times the terrain's own shadow. Unlit by the scene after this.
  const n = geometry.getAttribute('normal')
  const L = [
    Math.sin(sunRelAzDeg * DEG) * Math.cos(sunElDeg * DEG),
    Math.sin(sunElDeg * DEG),
    -Math.cos(sunRelAzDeg * DEG) * Math.cos(sunElDeg * DEG),
  ]
  for (let k = 0; k < count; k++) {
    const nx = n.getX(k)
    const ny = n.getY(k)
    const nz = n.getZ(k)
    const px = pos[k * 3]
    const py = pos[k * 3 + 1]
    const pz = pos[k * 3 + 2]
    const d = Math.hypot(px, py, pz) || 1
    const mu0 = Math.max(0, nx * L[0] + ny * L[1] + nz * L[2])
    const mu = Math.max(0.02, -(nx * px + ny * py + nz * pz) / d)
    const ls = mu0 / (mu0 + mu)
    const v = 0.03 + 1.25 * ls * (col[k * 3] - 0.035) / 0.965
    col[k * 3] = col[k * 3 + 1] = col[k * 3 + 2] = Math.min(1, v)
  }
  geometry.setAttribute('color', new BufferAttribute(col, 3))
  return { geometry, earthElDeg, sunRelAzDeg, sunElDeg }
}

/** Earth's thin atmosphere: a blue rim, brightest at the limb. */
export function atmosphere(radius: number): Mesh {
  const mat = new ShaderMaterial({
    uniforms: { glow: { value: new Color(0.45, 0.68, 1) } },
    vertexShader: `varying vec3 vN; varying vec3 vV;
      void main() { vec4 mv = modelViewMatrix * vec4(position, 1.0); vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix * mv; }`,
    fragmentShader: `uniform vec3 glow; varying vec3 vN; varying vec3 vV;
      void main() { float f = pow(1.0 - abs(dot(vN, vV)), 3.0); gl_FragColor = vec4(glow * f * 1.4, f); }`,
    side: BackSide,
    blending: AdditiveBlending,
    transparent: true,
    depthWrite: false,
  })
  return new Mesh(new SphereGeometry(radius * 1.035, 64, 32), mat)
}
