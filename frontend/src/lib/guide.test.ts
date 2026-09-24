// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'

async function fresh() {
  vi.resetModules()
  return import('./guide')
}

beforeEach(() => localStorage.clear())

describe('guide', () => {
  it('opens on the first visit, at the first step', async () => {
    const g = await fresh()
    expect(g.useGuide.getState()).toMatchObject({ open: true, step: 0 })
  })

  it('introduces each feature once: no two steps point at the same thing', async () => {
    const { GUIDE_STEPS } = await fresh()
    const keys = GUIDE_STEPS.map((s) => `${s.path} ${s.target}`)
    expect(new Set(keys).size).toBe(keys.length)
    expect(new Set(GUIDE_STEPS.map((s) => s.title)).size).toBe(GUIDE_STEPS.length)
  })

  it('puts the mission page last, so the steps before it keep the default dates', async () => {
    const { GUIDE_STEPS } = await fresh()
    const first = GUIDE_STEPS.findIndex((s) => s.path.startsWith('/missions/'))
    expect(GUIDE_STEPS.slice(first).every((s) => s.path.startsWith('/missions/'))).toBe(true)
  })

  it('remembers where it was left, and that it was closed', async () => {
    let g = await fresh()
    g.useGuide.getState().go(3)
    g.useGuide.getState().setOpen(false)
    g = await fresh()
    expect(g.useGuide.getState()).toMatchObject({ open: false, step: 3 })
  })

  it('keeps a step inside the list, and starts over when storage is unreadable', async () => {
    let g = await fresh()
    g.useGuide.getState().go(99)
    expect(g.useGuide.getState().step).toBe(g.GUIDE_STEPS.length - 1)
    localStorage.setItem('pw-guide', '{broken')
    g = await fresh()
    expect(g.useGuide.getState()).toMatchObject({ open: true, step: 0 })
  })
})
