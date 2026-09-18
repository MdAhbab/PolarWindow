/**
 * Sanity harness for the geometry engine. Not a unit test suite — a way to see
 * whether the physics produces numbers a mission planner would recognise.
 * Run: npm run check
 */
import { SITES } from '../src/lib/sites'
import { computeSiteMetrics, SURVIVAL_LIMIT_H, autonomyPacket } from '../src/lib/geometry/metrics'
import { SYNODIC_HOURS } from '../src/lib/geometry/ephemeris'

const WINDOW = SYNODIC_HOURS

const pad = (s: string, n: number) => s.padEnd(n)
const num = (v: number, n = 6, d = 0) => v.toFixed(d).padStart(n)

console.log(`window ${WINDOW.toFixed(1)} h — one lunar day\n`)
console.log(
  pad('site', 26),
  pad('lat', 8),
  pad('sun h', 8),
  pad('sun %', 7),
  pad('dark', 7),
  pad('±', 6),
  pad('dte h', 8),
  pad('dte %', 7),
  pad('rf gap', 8),
  pad('compound', 9),
  pad('mask max', 9),
  'ms',
)

for (const s of SITES) {
  const m = computeSiteMetrics(s, 0, WINDOW)
  const pk = autonomyPacket(m)
  console.log(
    pad(`${s.code} ${s.name}`, 26),
    pad(s.latDeg.toFixed(2), 8),
    num(m.sun.upHours, 8),
    pad(`${(m.sun.fractionUp * 100).toFixed(0)}%`, 7),
    num(m.sun.longestDownH, 7),
    num(m.sun.longestDownToleranceH, 6, 1),
    num(m.earth.upHours, 8),
    pad(`${(m.earth.fractionUp * 100).toFixed(0)}%`, 7),
    num(m.earth.longestDownH, 8),
    num(m.worstCompoundH, 9),
    pad(`${m.mask.maxElDeg.toFixed(2)}@${m.mask.maxElBearingDeg}`, 9),
    m.computeMs.toFixed(0),
    m.sun.longestDownH > SURVIVAL_LIMIT_H ? '  OVER LIMIT' : '',
    pk.compoundInsideDark ? ' [compound inside night]' : '',
  )
}

const a = computeSiteMetrics(SITES[0], 0, WINDOW)
console.log('\nSite A sun arcs:')
for (const arc of a.sun.arcs) {
  console.log(
    ' ',
    arc.up ? 'lit    ' : 'dark   ',
    `h${arc.startH.toFixed(1).padStart(6)} -> h${arc.endH.toFixed(1).padStart(6)}`,
    `${arc.hours.toFixed(1).padStart(6)} h`,
    `±${arc.toleranceH.toFixed(2)}`,
    arc.grazing ? 'GRAZING' : '',
    arc.blockedByBearingDeg !== undefined
      ? `by ${arc.blockedByBearingDeg.toFixed(0)}° at ${arc.blockedByElDeg?.toFixed(2)}°`
      : '',
  )
}

console.log('\nSite A sun elevation range:')
const els = a.sun.samples.map((s) => s.elDeg)
console.log(`  ${Math.min(...els).toFixed(2)}° .. ${Math.max(...els).toFixed(2)}°`)
const eels = a.earth.samples.map((s) => s.elDeg)
console.log('Site A earth elevation range:')
console.log(`  ${Math.min(...eels).toFixed(2)}° .. ${Math.max(...eels).toFixed(2)}°`)
