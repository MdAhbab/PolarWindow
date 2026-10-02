import {
  AdditiveBlending,
  BackSide,
  BufferAttribute,
  BufferGeometry,
  Color,
  DataTexture,
  LinearFilter,
  LinearMipmapLinearFilter,
  Mesh,
  RepeatWrapping,
  RGBAFormat,
  ShaderMaterial,
  SphereGeometry,
  UnsignedByteType,
  Vector2,
  Vector3,
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
 * for a low Sun from the right (ten degrees up: placed for the picture, and
 * higher than it ever stands there). Earth stands at the elevation it has
 * there on average, which puts it half over the site's real skyline, and is
 * NASA's Blue Marble under NASA's cloud layer. The sky is black, with the Milky Way.
 * The front page's Moon scene (moonScene.ts) puts the ground on its globe and
 * flies from it out to the whole Moon as the page scrolls; this file holds
 * the ground, its small relief and Earth's air.
 *
 * The heights are 80 m apart, so on their own the ground near the viewer is
 * smooth. What is smaller than that is drawn, not measured: craters, rocks
 * and the roughness of the soil, generated here and lit by the same low Sun
 * (`detailTile`). The page's footer says the picture is not to scale; nothing
 * on the page reads a number from it.
 *
 * The ground is in kilometres, in a frame with the viewer's eye at the origin,
 * Earth's direction along -z and up along +y.
 */
const DEG = Math.PI / 180

/** A small seeded generator, so the ground is the same on every visit. */
function rng(seed: number) {
  let s = seed >>> 0
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0
    return s / 2 ** 32
  }
}

/** How steep a slope the detail tiles can carry; steeper is clipped. */
const SLOPE_MAX = 1.2

/**
 * One tile of small relief, as a texture that repeats: craters, rocks and the
 * soil's roughness as heights, then what a Sun `sunElDeg` above the horizon
 * does to them. The tile's u axis points toward the Sun, so the shadow each
 * height casts is one sweep along a row.
 *
 * R and G hold the slope toward the Sun and across it (square-root coded, so
 * gentle slopes keep their precision), B how much of the Sun's disc reaches
 * the texel (0 in shadow, 255 in full light), A how bright the soil is there.
 */
function detailTile(
  seed: number,
  o: {
    craters: number
    rMin: number
    rMax: number
    rocks: number
    rockMin: number
    rockMax: number
    /** The soil's gentle unevenness, as a slope: kept far under the Sun's height, or the ground reads as ripples. */
    rough: number
    /** How much one texel's brightness differs from the next. */
    grain: number
    sunElDeg: number
  },
): DataTexture {
  const n = 512
  const r = rng(seed)
  const h = new Float32Array(n * n)
  const albedo = new Float32Array(n * n).fill(1)
  const wrap = (i: number) => ((i % n) + n) % n

  // A power law between the smallest and largest radius: many small, few large.
  const radius = (lo: number, hi: number, b: number) => lo * (1 - r() * (1 - (lo / hi) ** b)) ** (-1 / b)

  for (let c = 0; c < o.craters; c++) {
    const rad = radius(o.rMin, o.rMax, 2) * n
    // Most small craters on the Moon are worn shallow; a few are fresh, a fifth as deep as they are wide.
    const fresh = 0.15 + 0.85 * r() ** 2.5
    const depth = 0.4 * rad * fresh
    const rim = 0.07 * rad * fresh
    const cu = r() * n
    const cv = r() * n
    const reach = Math.ceil(rad * 2.5)
    // A fresh crater throws a little bright soil around itself.
    const bright = fresh > 0.75 ? 0.1 * r() : 0
    for (let dv = -reach; dv <= reach; dv++) {
      for (let du = -reach; du <= reach; du++) {
        const rho = Math.hypot(du, dv) / rad
        if (rho >= 2.5) continue
        const k = wrap(Math.round(cv) + dv) * n + wrap(Math.round(cu) + du)
        if (rho <= 1) h[k] += rim - depth * (1 - rho * rho)
        else {
          const w = ((2.5 - rho) / 1.5) ** 2 / rho ** 3
          h[k] += rim * w
          albedo[k] += bright * w
        }
      }
    }
  }

  for (let c = 0; c < o.rocks; c++) {
    const rad = radius(o.rockMin, o.rockMax, 2.2) * n
    const cu = r() * n
    const cv = r() * n
    const tall = rad * (0.5 + 0.6 * r())
    const reach = Math.ceil(rad)
    const tone = 0.85 + 0.25 * r()
    for (let dv = -reach; dv <= reach; dv++) {
      for (let du = -reach; du <= reach; du++) {
        const rho = Math.hypot(du, dv) / rad
        if (rho >= 1) continue
        const k = wrap(Math.round(cv) + dv) * n + wrap(Math.round(cu) + du)
        h[k] += tall * (1 - rho * rho) ** 0.6
        albedo[k] = tone
      }
    }
  }

  // The soil's own roughness: three octaves of smooth noise that repeat with the tile.
  for (const period of [16, 48, 128]) {
    const lattice = new Float32Array(period * period)
    for (let i = 0; i < lattice.length; i++) lattice[i] = r() - 0.5
    const cell = n / period
    const amp = o.rough * cell * 1.6
    const ease = (t: number) => t * t * (3 - 2 * t)
    for (let v = 0; v < n; v++) {
      const fv = v / cell
      const v0 = Math.floor(fv)
      const tv = ease(fv - v0)
      for (let u = 0; u < n; u++) {
        const fu = u / cell
        const u0 = Math.floor(fu)
        const tu = ease(fu - u0)
        const a = lattice[(v0 % period) * period + (u0 % period)]
        const b = lattice[(v0 % period) * period + ((u0 + 1) % period)]
        const c = lattice[((v0 + 1) % period) * period + (u0 % period)]
        const d = lattice[((v0 + 1) % period) * period + ((u0 + 1) % period)]
        const val = a + (b - a) * tu + (c - a + (a - b - c + d) * tu) * tv
        h[v * n + u] += val * amp
        if (period === 48) albedo[v * n + u] *= 1 + val * 0.12
      }
    }
  }
  // Soil is grains, not paint: each texel a little lighter or darker than the next.
  for (let k = 0; k < albedo.length; k++) albedo[k] *= 1 + (r() - 0.5) * o.grain

  // The Sun's disc is half a degree wide: a texel is lit by as much of it as
  // clears the heights toward the Sun. Two sweeps, for the disc's two edges.
  const lo = Math.tan((o.sunElDeg - 0.27) * DEG)
  const hi = Math.tan((o.sunElDeg + 0.27) * DEG)
  const light = new Float32Array(n * n)
  for (let v = 0; v < n; v++) {
    // The shadow's edge for the lower and the upper limb of the Sun, falling as it runs down-Sun.
    let s1 = -Infinity
    let s2 = -Infinity
    // Twice round the row, so a shadow can fall across the tile's own edge.
    for (let pass = 0; pass < 2; pass++) {
      for (let u = n - 1; u >= 0; u--) {
        const k = v * n + u
        const a1 = s1 - lo
        const a2 = s2 - hi
        if (pass === 1) light[k] = h[k] >= a1 ? 1 : h[k] <= a2 ? 0 : (h[k] - a2) / (a1 - a2)
        s1 = Math.max(h[k], a1)
        s2 = Math.max(h[k], a2)
      }
    }
  }

  const data = new Uint8Array(n * n * 4)
  const code = (g: number) => {
    const x = Math.max(-1, Math.min(1, g / SLOPE_MAX))
    return Math.round((0.5 + 0.5 * Math.sign(x) * Math.sqrt(Math.abs(x))) * 255)
  }
  for (let v = 0; v < n; v++) {
    for (let u = 0; u < n; u++) {
      const k = v * n + u
      data[k * 4] = code((h[v * n + wrap(u + 1)] - h[v * n + wrap(u - 1)]) / 2)
      data[k * 4 + 1] = code((h[wrap(v + 1) * n + u] - h[wrap(v - 1) * n + u]) / 2)
      data[k * 4 + 2] = Math.round(light[k] * 255)
      data[k * 4 + 3] = Math.round(Math.max(0, Math.min(1, albedo[k] * 0.8)) * 255)
    }
  }
  const t = new DataTexture(data, n, n, RGBAFormat, UnsignedByteType)
  t.wrapS = t.wrapT = RepeatWrapping
  t.magFilter = LinearFilter
  t.minFilter = LinearMipmapLinearFilter
  t.generateMipmaps = true
  t.anisotropy = 16
  t.needsUpdate = true
  return t
}

export interface Ground {
  mesh: Mesh
  /** How much of the ground shows, 0 to 1. */
  setOpacity: (o: number) => void
  earthElDeg: number
  sunRelAzDeg: number
  sunElDeg: number
  dispose: () => void
}

/**
 * The ground: the fan of LOLA heights as a mesh, shaded as regolith is.
 *
 * Lunar soil does not shade like chalk: it scatters light back much the same
 * whatever the slope, so ground under a Sun two degrees high is still bright
 * where plain diffuse shading would leave it black (the Lommel-Seeliger law,
 * mu0 / (mu0 + mu)). The view is taken from the eye on the ground, so the
 * ground keeps its look as the camera lifts away from it.
 */
export async function loadGround(): Promise<Ground> {
  const buf = await (await fetch(terrainUrl)).arrayBuffer()
  const head = new Float32Array(buf, 0, 8)
  const [nAz, nR, r0, r1, halfDeg, earthElDeg, sunRelAzDeg, sunElDeg] = Array.from(head)
  const count = nAz * nR
  const heights = new Int16Array(buf, 32, count)
  const light = new Uint8Array(buf, 32 + count * 2, count)
  const pos = new Float32Array(count * 3)
  const shade = new Float32Array(count)
  for (let i = 0; i < nR; i++) {
    const r = r0 * (r1 / r0) ** (i / (nR - 1))
    for (let j = 0; j < nAz; j++) {
      const k = i * nAz + j
      const a = (-halfDeg + (2 * halfDeg * j) / (nAz - 1)) * DEG
      pos[k * 3] = r * Math.sin(a)
      // The height's step grows with the range (render_earthrise.py): metres, then km.
      pos[k * 3 + 1] = (heights[k] * (0.005 + r * 1000 * 1.25e-4)) / 1000
      pos[k * 3 + 2] = -r * Math.cos(a)
      shade[k] = light[k] / 255
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
  geometry.setAttribute('shade', new BufferAttribute(shade, 1))
  geometry.setIndex(new BufferAttribute(idx, 1))
  geometry.computeVertexNormals()

  // Small relief at three sizes: stones and pits a few steps away, craters a
  // stone's throw across, and the ones that fill the middle distance.
  const near = detailTile(3, { craters: 90, rMin: 0.008, rMax: 0.07, rocks: 140, rockMin: 0.003, rockMax: 0.011, rough: 0.012, grain: 0.3, sunElDeg })
  const far = detailTile(8, { craters: 130, rMin: 0.007, rMax: 0.075, rocks: 40, rockMin: 0.003, rockMax: 0.008, rough: 0.012, grain: 0.14, sunElDeg })

  const sun = new Vector3(
    Math.sin(sunRelAzDeg * DEG) * Math.cos(sunElDeg * DEG),
    Math.sin(sunElDeg * DEG),
    -Math.cos(sunRelAzDeg * DEG) * Math.cos(sunElDeg * DEG),
  )
  const material = new ShaderMaterial({
    uniforms: {
      tNear: { value: near },
      tFar: { value: far },
      sunDir: { value: sun },
      // The horizontal direction toward the Sun, which the tiles' u axis follows.
      sunH: { value: new Vector2(sun.x, sun.z).normalize() },
      soil: { value: new Color(0.8, 0.78, 0.75) },
      opacity: { value: 1 },
    },
    vertexShader: /* glsl */ `
      #include <common>
      #include <logdepthbuf_pars_vertex>
      attribute float shade;
      varying vec3 vP;
      varying vec3 vN;
      varying float vShade;
      void main() {
        vP = position;
        vN = normal;
        vShade = shade;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        #include <logdepthbuf_vertex>
      }`,
    fragmentShader: /* glsl */ `
      #include <common>
      #include <logdepthbuf_pars_fragment>
      uniform sampler2D tNear;
      uniform sampler2D tFar;
      uniform vec3 sunDir;
      uniform vec2 sunH;
      uniform vec3 soil;
      uniform float opacity;
      varying vec3 vP;
      varying vec3 vN;
      varying float vShade;

      float hash(vec2 p) {
        return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
      }
      // Smooth noise, 0 to 1: which of a tile's two layings shows where.
      float patches(vec2 p) {
        vec2 i = floor(p);
        vec2 f = fract(p);
        f = f * f * (3.0 - 2.0 * f);
        return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
      }

      // A tile read at one place: its slope (toward the Sun, across it), its shadow, its soil.
      vec4 tap(sampler2D t, vec2 uv, float flip) {
        vec4 c = texture2D(t, uv);
        vec2 g = c.rg * 2.0 - 1.0;
        g = sign(g) * g * g * ${SLOPE_MAX.toFixed(1)};
        return vec4(g.x, g.y * flip, c.b, c.a / 0.8);
      }

      // One size of relief, size km to a tile. A tile laid edge to edge shows
      // as a lattice, so it is laid twice, the second time mirrored across the
      // Sun's direction (which keeps its shadows true), a little larger and
      // shifted, and patches of each show through the other.
      void relief(sampler2D t, vec2 q, float size, float weight, inout vec2 slope, inout float lit, inout float tone) {
        vec4 a = tap(t, q / size, 1.0);
        vec4 b = tap(t, vec2(q.x, -q.y) / (size * 1.27) + vec2(0.37, 0.61), -1.0);
        vec4 c = mix(a, b, smoothstep(0.42, 0.58, patches(q / (size * 0.8) + 7.3)));
        slope += c.xy * weight;
        lit *= mix(1.0, c.z, weight);
        tone *= mix(1.0, c.w, weight);
      }

      void main() {
        #include <logdepthbuf_fragment>
        vec2 across = vec2(-sunH.y, sunH.x);
        vec2 q = vec2(dot(vP.xz, sunH), dot(vP.xz, across));
        float d = length(vP);
        vec2 slope = vec2(0.0);
        float lit = 1.0;
        float tone = 1.0;
        // Tiles 14 m, 95 m and 700 m across. The largest is for the far slopes
        // only: its craters are as wide as the near ground itself.
        relief(tNear, q, 0.014, 1.0, slope, lit, tone);
        relief(tFar, q + 0.031, 0.095, 1.0, slope, lit, tone);
        relief(tFar, q + 0.57, 0.7, smoothstep(0.3, 1.5, d), slope, lit, tone);

        // Not all of the small relief's slope goes into the shading: under a low Sun the whole of
        // it would swing every pit wall from black to white. Its shadows, above, are the full ones.
        slope *= 0.8;
        vec3 n = normalize(vN);
        n = normalize(vec3(n.x - slope.x * sunH.x - slope.y * across.x, n.y, n.z - slope.x * sunH.y - slope.y * across.y));
        vec3 v = normalize(-vP);
        float mu0 = dot(n, sunDir);
        float mu = max(dot(n, v), 0.0);
        // The added term keeps a slope's tilt in the shading: without it everything the low Sun
        // reaches is one brightness, and a crater is a hole cut in paper.
        float ls = mu0 > 0.0 ? 2.0 * mu0 / (mu0 + mu + 0.22) : 0.0;
        float sunlit = min(ls, 1.5) * lit * vShade;
        // In shadow the ground is not quite black: the sunlit ground around it scatters a little light in.
        vec3 c = soil * tone * (0.014 + 0.3 * sunlit);
        gl_FragColor = vec4(c, opacity);
        #include <colorspace_fragment>
      }`,
    transparent: true,
  })
  const mesh = new Mesh(geometry, material)
  return {
    mesh,
    setOpacity: (o) => {
      material.uniforms.opacity.value = o
      mesh.visible = o > 0.01
    },
    earthElDeg,
    sunRelAzDeg,
    sunElDeg,
    dispose: () => {
      geometry.dispose()
      material.dispose()
      near.dispose()
      far.dispose()
    },
  }
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
