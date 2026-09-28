/**
 * The contract fixtures, checked against docs/lifecycle-api.md at run time.
 *
 * JSON imports are typed loosely (string, not the unions), so the compiler
 * cannot hold them to the contract; these checks do: every Quantity has
 * exactly one margin form or a reason, a missing value says why, every enum
 * is one the contract names, and every section carries its meta envelope.
 * The screens are built and tested against these files, so a fixture that
 * drifts from the contract would test the wrong thing.
 */
import { describe, expect, it } from 'vitest'
import type { QuantityDTO } from './lifecycle'

// Every fixture file, as data (a copy, so a check can never change another's input).
const FILES = import.meta.glob('./__fixtures__/lifecycle/*.json', { eager: true, import: 'default' }) as Record<string, unknown>
const NAMES = Object.keys(FILES).map((k) => k.split('/').pop() as string)
const load = (name: string) => JSON.parse(JSON.stringify(FILES[`./__fixtures__/lifecycle/${name}`]))

const QUANTITY_KEYS = ['value', 'unit', 'provenance', 'pm', 'lo', 'hi', 'factor', 'open', 'no_margin_reason', 'missing_reason', 'source']
const PROVENANCE = ['computed', 'published', 'entered', 'assumed']

function isQuantityLike(x: unknown): x is QuantityDTO {
  return Boolean(x && typeof x === 'object' && 'provenance' in x && 'unit' in x && 'value' in x)
}

/** ADR-9: exactly one margin form, or a reason; a null value (not a range) has a reason. */
function quantityProblems(q: QuantityDTO, at: string): string[] {
  const out: string[] = []
  for (const k of QUANTITY_KEYS) if (!(k in q)) out.push(`${at}: missing ${k}`)
  if (!PROVENANCE.includes(q.provenance)) out.push(`${at}: provenance ${q.provenance}`)
  const range = q.lo !== null && q.hi !== null
  if ((q.lo === null) !== (q.hi === null)) out.push(`${at}: lo and hi come together`)
  if (range && (q.lo as number) > (q.hi as number)) out.push(`${at}: lo above hi`)
  if (q.value === null && !range) {
    if (!q.missing_reason) out.push(`${at}: null value without missing_reason`)
    return out
  }
  const forms = [q.pm !== null, range && q.pm === null, q.factor !== null, q.no_margin_reason !== null].filter(Boolean).length
  if (forms !== 1) out.push(`${at}: ${forms} margin forms (one expected)`)
  if (q.factor !== null && q.factor < 1) out.push(`${at}: factor below 1`)
  if (q.pm !== null && q.pm < 0) out.push(`${at}: negative ±`)
  return out
}

function walk(x: unknown, at: string, found: string[]): number {
  let n = 0
  if (isQuantityLike(x)) {
    found.push(...quantityProblems(x, at))
    return 1
  }
  if (Array.isArray(x)) x.forEach((v, i) => (n += walk(v, `${at}[${i}]`, found)))
  else if (x && typeof x === 'object') for (const [k, v] of Object.entries(x)) n += walk(v, `${at}.${k}`, found)
  return n
}

const SECTION_FILES = ['ready.json', 'ready-empty.json', 'launch.json', 'launch-weather.json', 'trip.json', 'trip-none.json', 'contact.json', 'rover.json', 'rover-unresolvable.json', 'return.json', 'space-weather.json']

describe('lifecycle contract fixtures', () => {
  it('every Quantity in every fixture has one margin form or a reason (ADR-9)', () => {
    const problems: string[] = []
    let count = 0
    expect(NAMES.length).toBeGreaterThan(15)
    for (const f of NAMES) count += walk(load(f), f, problems)
    expect(problems).toEqual([])
    expect(count).toBeGreaterThan(40)
  })

  it('every section answer carries the meta envelope, never an empty uncertainty', () => {
    for (const f of [...SECTION_FILES, 'sections.json']) {
      const s = load(f)
      expect(s, f).toHaveProperty('data')
      expect(typeof s.meta.computed_at, f).toBe('string')
      expect(s.meta.uncertainty.kind, f).toBe('composite')
      expect(Array.isArray(s.meta.uncertainty.parts), f).toBe(true)
      expect(typeof s.meta.engines, f).toBe('object')
      expect(Array.isArray(s.meta.sources), f).toBe(true)
      expect(typeof s.meta.stale, f).toBe('boolean')
    }
  })

  it('the six steps, in order, each with a state the contract names', () => {
    const s = load('sections.json').data as { section: string; state: string; summary: string }[]
    expect(s.map((x) => x.section)).toEqual(['ready', 'launch', 'trip', 'landing', 'contact', 'return'])
    for (const x of s) {
      expect(['available', 'computing', 'needs_input', 'not_applicable', 'no_data']).toContain(x.state)
      expect(x.summary.length).toBeGreaterThan(0)
    }
  })

  it('readiness: counts match the items, states and kinds are the contract’s, and there is no percentage', () => {
    const r = load('ready.json').data
    const states = ['not_started', 'in_build', 'in_test', 'test_passed', 'delivered', 'integrated', 'verified_on_lander', 'ready', 'blocked']
    for (const it of r.items) {
      expect(states).toContain(it.state)
      expect(['lander', 'payload', 'rover', 'launch_vehicle', 'range', 'ground_booking', 'relay_agreement', 'ops_team', 'licence']).toContain(it.kind)
      if (it.state === 'blocked') expect(it.blocked_reason).toBeTruthy()
    }
    // Counts cover only items with an entered state; the rest are `not_entered`.
    const known = r.items.filter((i: { state_known: boolean }) => i.state_known)
    for (const s of states) expect(r.counts[s]).toBe(known.filter((i: { state: string }) => i.state === s).length)
    expect(r.not_entered).toBe(r.items.length - known.length)
    for (const it of r.items) for (const n of it.allowed_next) expect(states).toContain(n)
    expect(JSON.stringify(r)).not.toMatch(/percent|score/i)
    for (const risk of r.risks) for (const x of risk.ratings) expect(Object.keys(x).sort()).toEqual(['category', 'consequence', 'likelihood'])
  })

  it('weather: shares are k of n with an interval inside 0 to 1, and systems are never pooled', () => {
    const w = load('launch-weather.json').data
    for (const r of w.rules) {
      expect(['model', 'proxy', 'observation']).toContain(r.class)
      for (const p of r.per_system) {
        expect(['GEFS', 'ECMWF-ENS', 'AIFS-ENS']).toContain(p.system)
        if (p.share) {
          expect(p.share.k).toBeLessThanOrEqual(p.share.n)
          expect(p.share.lo).toBeGreaterThanOrEqual(0)
          expect(p.share.hi).toBeLessThanOrEqual(1)
          expect(p.share.lo).toBeLessThanOrEqual(p.share.k / p.share.n)
          expect(p.share.hi).toBeGreaterThanOrEqual(p.share.k / p.share.n)
        } else expect(p.missing_reason).toBeTruthy()
      }
      const systems = r.per_system.map((p: { system: string }) => p.system)
      expect(new Set(systems).size).toBe(systems.length)
    }
    expect(w).not.toHaveProperty('overall')
  })

  it('trip: samples in time order, at most 2,000, stretches inside the trip', () => {
    const t = load('trip.json').data
    expect(t.samples.length).toBeLessThanOrEqual(2000)
    const ts = t.samples.map((s: { t: string }) => Date.parse(s.t))
    expect([...ts].sort((a, b) => a - b)).toEqual(ts)
    for (const s of [...t.shadow, ...t.heard]) {
      expect(Date.parse(s.start)).toBeGreaterThanOrEqual(Date.parse(t.start))
      expect(Date.parse(s.end)).toBeLessThanOrEqual(Date.parse(t.end))
    }
  })

  it('contact: every link joins two known nodes; a planned relay is a range, not a timeline', () => {
    const c = load('contact.json').data
    const ids = new Set(c.nodes.map((n: { id: string }) => n.id))
    for (const l of c.links) {
      expect(ids.has(l.from)).toBe(true)
      expect(ids.has(l.to)).toBe(true)
    }
    const via = c.numbers.via_relay_h
    expect(via.lo).not.toBeNull()
    expect(via.hi).not.toBeNull()
  })

  it('a job reference has the polling fields the client needs', () => {
    for (const f of ['job-running.json', 'job-done.json']) {
      const j = load(f)
      expect(['queued', 'running', 'done', 'failed']).toContain(j.status)
      expect(j.poll_after_s).toBeGreaterThan(0)
      expect(typeof j.job_id).toBe('number')
    }
  })
})
