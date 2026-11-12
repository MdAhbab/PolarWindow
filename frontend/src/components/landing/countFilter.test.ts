import { describe, expect, it } from 'vitest'
import { candidateSiteCount, catalogueMissionCount } from './countFilter'

describe('the front page counts', () => {
  it('counts the catalogue’s missions and not the projects people added', () => {
    const items = [
      { origin: 'catalogue' as const },
      { origin: 'catalogue' as const },
      { origin: 'project' as const },
      { origin: 'project' as const },
      { origin: 'project' as const },
    ]
    expect(catalogueMissionCount(items)).toBe(2)
  })

  it('counts a mission with no origin (an older answer) as the catalogue’s', () => {
    expect(catalogueMissionCount([{}, { origin: 'project' }])).toBe(1)
  })

  it('is zero for none, and for projects alone', () => {
    expect(catalogueMissionCount([])).toBe(0)
    expect(catalogueMissionCount([{ origin: 'project' }])).toBe(0)
  })

  it('counts candidate sites and not mission targets or the sites a project brings', () => {
    const items = [
      { site: { id: 'shackleton-rim', kind: 'candidate' } },
      { site: { id: 'connecting-ridge', kind: 'candidate' } },
      { site: { id: 'mission-im-1', kind: 'mission_target' } },
      { site: { id: 'project-aurora-scout-1', kind: 'mission_target' } },
      { site: { id: 'project-by-hand', kind: 'candidate' } },
    ]
    expect(candidateSiteCount(items)).toBe(2)
    expect(candidateSiteCount([])).toBe(0)
  })
})
