// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, screen } from '@testing-library/react'
import type { ActivityDTO, ActivityItemDTO } from '../../lib/api/experience.types'
import { renderApp } from '../../test/render'
import { ActivityList } from './ActivityTray'
import { finishedScenarios, progressWords, ringLabel, ringState, whenWords } from './model'

const item = (over: Partial<ActivityItemDTO>): ActivityItemDTO => ({
  key: 'scenario:s1',
  kind: 'scenario',
  label: 'Scenario: Falcon 9 from LC-39A',
  mission_id: 'im-3',
  mission_name: 'IM-3',
  href: '/missions/im-3/launch?scenario=s1',
  status: 'running',
  progress: 0.4,
  message: 'Launch opportunities',
  started_at: '2026-11-11T11:57:00Z',
  finished_at: null,
  ...over,
})
const feed = (active: ActivityItemDTO[], recent: ActivityItemDTO[] = []): ActivityDTO => ({ active, recent, poll_after_s: 3 })

afterEach(cleanup)

describe('the activity ring', () => {
  it('is empty with nothing active, the mean of the progress figures otherwise', () => {
    expect(ringState(undefined)).toEqual({ count: 0, fraction: 0 })
    const two = ringState(feed([item({ progress: 0.4 }), item({ key: 'job:2', progress: 0.8 })]))
    expect(two.count).toBe(2)
    expect(two.fraction).toBeCloseTo(0.6)
  })

  it('counts a queued item with no figure as not started, and claims no figure when none has one', () => {
    expect(ringState(feed([item({ progress: 1 }), item({ key: 'job:2', status: 'queued', progress: null })])).fraction).toBe(0.5)
    expect(ringState(feed([item({ progress: null })]))).toEqual({ count: 1, fraction: null })
  })

  it('says what it holds in words, and that a saved copy has none', () => {
    expect(ringLabel({ count: 0, fraction: 0 }, true)).toBe('Activity: nothing is being worked out')
    expect(ringLabel({ count: 2, fraction: 0.25 }, true)).toBe('Activity: 2 things are being worked out, 25% done')
    expect(ringLabel({ count: 1, fraction: null }, true)).toBe('Activity: 1 thing is being worked out')
    expect(ringLabel({ count: 0, fraction: 0 }, false)).toBe('Activity: not available in the saved copy')
  })
})

describe('the activity words', () => {
  it('gives progress only while working, and the age from the item’s own times', () => {
    expect(progressWords(item({ progress: 0.423 }))).toBe('42% done')
    expect(progressWords(item({ status: 'done', progress: 1 }))).toBeNull()
    expect(progressWords(item({ progress: null }))).toBeNull()
    const now = Date.parse('2026-11-11T12:00:00Z')
    expect(whenWords(item({}), now)).toBe('started 3 min ago')
    expect(whenWords(item({ finished_at: '2026-11-11T11:59:30Z' }), now)).toBe('finished just now')
  })

  it('toasts a scenario only once it was seen active and has now finished', () => {
    const done = item({ status: 'done', progress: 1, finished_at: '2026-11-11T12:00:00Z' })
    const other = item({ key: 'job:7', kind: 'launch', status: 'done' })
    expect(finishedScenarios(new Set(['scenario:s1', 'job:7']), feed([], [done, other]))).toEqual([done])
    expect(finishedScenarios(new Set(), feed([], [done]))).toEqual([])
    expect(finishedScenarios(new Set(['scenario:s1']), feed([item({})], [done]))).toEqual([])
  })
})

describe('the activity tray', () => {
  const state = (data: ActivityDTO | undefined, extra: Partial<{ isPending: boolean; error: unknown }> = {}) => ({
    data,
    isPending: false,
    error: null,
    refetch: () => undefined,
    ...extra,
  })

  it('lists what is being worked out with its progress, and what just finished, each linking back', () => {
    const recent = item({ key: 'job:9', kind: 'trip', label: 'Trip for IM-3', status: 'done', progress: 1, href: '/missions/im-3/trip', finished_at: '2026-11-11T11:58:00Z' })
    renderApp(<ActivityList live feed={state(feed([item({})], [recent]))} />)
    expect(screen.getByRole('progressbar', { name: 'Progress of Scenario: Falcon 9 from LC-39A' }).getAttribute('aria-valuenow')).toBe('40')
    expect(screen.getByText(/Working it out, 40% done/)).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Go to where it will show: Scenario: Falcon 9 from LC-39A' }).getAttribute('href')).toBe(
      '/missions/im-3/launch?scenario=s1',
    )
    expect(screen.getByRole('link', { name: 'Open the answer: Trip for IM-3' }).getAttribute('href')).toBe('/missions/im-3/trip')
  })

  it('says plainly when nothing is being worked out', () => {
    renderApp(<ActivityList live feed={state(feed([]))} />)
    expect(screen.getByText('Nothing is being worked out')).toBeTruthy()
  })

  it('a saved copy calls nothing and says so', () => {
    renderApp(<ActivityList live={false} feed={state(undefined, { isPending: true })} />)
    expect(screen.getByText('This is a saved copy')).toBeTruthy()
    expect(screen.queryByText(/Checking what is being worked out/)).toBeNull()
  })
})
