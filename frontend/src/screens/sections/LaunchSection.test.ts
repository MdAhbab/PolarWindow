// @vitest-environment jsdom
/**
 * V53: the Launch headline's "the next is …" and the opportunity the tiles
 * open on come from one choice, so they never name two different launches,
 * and the tiles never open on one already past.
 */
import { describe, expect, it } from 'vitest'
import { nextOpportunity, openingChoice } from './LaunchSection'
import type { LaunchCalendarDTO } from '../../lib/api/lifecycle'
import launchFixture from '../../lib/api/__fixtures__/lifecycle/launch.json'

const cal = (launchFixture as unknown as { data: LaunchCalendarDTO }).data
const at = (id: string) => (cal.opportunities.find((o) => o.id === id)!.t0.value as number) * 1000
const unpublished: LaunchCalendarDTO = { ...cal, published_t0: null }

describe('the opportunity a Launch page opens on', () => {
  it('is the next one, the same the headline names, when no launch time is published', () => {
    // The calendar starts at 00:00 UTC and is kept for the day: by evening its first opportunity is past.
    const now = at('opp-1') + 3_600_000
    expect(nextOpportunity(unpublished, now)?.id).toBe('opp-2')
    expect(openingChoice(unpublished, now).id).toBe('opp-2')
  })

  it('is the one nearest the published launch time, among those not yet past', () => {
    expect(openingChoice(cal, at('opp-1') - 1000).id).toBe('opp-2')
    // The published time has gone by: never back to a past opportunity.
    expect(openingChoice(cal, at('opp-3') + 1000).id).toBe('opp-4')
  })

  it('is the one nearest the published time when every opportunity is past (a flown mission)', () => {
    const later = at('opp-6') + 86_400_000
    expect(nextOpportunity(cal, later)).toBeUndefined()
    expect(openingChoice(cal, later).id).toBe('opp-2')
  })
})
