import { describe, expect, it } from 'vitest'
import { adaptMission } from './api/adapters'
import type { MissionListDTO } from './api/client'
import listFixture from './api/__fixtures__/missions.list.json'
import { centralAngle, missionAccessibleName, missionDate, nearestCandidates } from './missions'
import { windowParamsFor, stepForHours } from './mission'
import { hasVisited, markVisited } from './firstVisit'
import type { Site } from './types'

const list = listFixture as unknown as MissionListDTO
const mission = (id: string) => adaptMission(list.items.find((m) => m.id === id)!)

const site = (id: string, latDeg: number, lonDeg: number, kind: Site['kind'] = 'candidate'): Site => ({
  id,
  code: id.toUpperCase(),
  name: id,
  latDeg,
  lonDeg,
  elevM: null,
  note: '',
  searchKind: 'rim',
  kind,
  coordinateRule: 'derived_open_sky',
  terrainModelled: true,
})

describe('nearestCandidates ("nearest by distance")', () => {
  const sites = [
    site('a', -89.9, 0),
    site('b', -85, 30),
    site('c', -84.8, 29),
    site('d', -80, 180),
    site('mission-x', -84.79, 29.2, 'mission_target'),
  ]

  it('orders candidates by great-circle distance and never includes a mission target', () => {
    const got = nearestCandidates(-84.79, 29.2, sites, 3).map((s) => s.id)
    expect(got).toEqual(['c', 'b', 'a'])
  })

  it('handles longitude wrap-around', () => {
    expect(centralAngle(-10, 359, -10, 1)).toBeCloseTo(centralAngle(-10, -1, -10, 1), 12)
    expect(centralAngle(0, 0, 0, 180)).toBeCloseTo(Math.PI, 12)
  })
})

describe('mission list words', () => {
  it('names a row in the handoff order, with precision in words', () => {
    expect(missionAccessibleName(mission('blue-moon-mk1-viper'))).toMatch(
      /^VIPER delivery \(Blue Moon MK1\), Blue Origin, landing late 2027 \(to the year\), Planned, carries /,
    )
  })

  it('says a missing provider is unconfirmed rather than leaving a gap', () => {
    expect(missionAccessibleName(mission('cs-8'))).toMatch(/provider unconfirmed/)
    expect(missionAccessibleName(mission('cs-8'))).toMatch(/some details unconfirmed$/)
  })

  it('places a mission lost before landing at its launch', () => {
    const d = missionDate(mission('peregrine-m1'))
    expect(d?.which).toBe('launch')
  })
})

describe('window sampling step', () => {
  it('keeps the golden 900 s step for a lunar day and coarsens long windows inside API bounds', () => {
    expect(stepForHours(708.734)).toBe(900)
    expect(stepForHours(90 * 24)).toBe(1800)
    expect(stepForHours(365 * 24)).toBe(3600)
    expect(stepForHours(730 * 24)).toBe(7200)
    for (const h of [12.75, 336, 720, 2160, 8760, 17520]) {
      const w = windowParamsFor(0, h)
      const samples = (Date.parse(w.end) - Date.parse(w.start)) / 1000 / w.stepS
      expect(samples).toBeLessThanOrEqual(9000)
      expect(w.stepS).toBeGreaterThanOrEqual(300)
      expect(w.stepS).toBeLessThanOrEqual(7200)
    }
  })
})

describe('first visit (U1)', () => {
  it('treats a visitor with no flag as new, and a marked one as returning', () => {
    const store = new Map<string, string>()
    const s = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) }
    expect(hasVisited(s)).toBe(false)
    markVisited(s)
    expect(hasVisited(s)).toBe(true)
  })

  it('sends a visitor to Missions when storage throws, and never throws itself', () => {
    const broken = {
      getItem: () => {
        throw new Error('SecurityError')
      },
      setItem: () => {
        throw new Error('QuotaExceededError')
      },
    }
    expect(hasVisited(broken)).toBe(true)
    expect(() => markVisited(broken)).not.toThrow()
  })
})
