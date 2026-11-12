// @vitest-environment jsdom
/**
 * R1 and V135: the Plan chart's axis is dated from the dates' own start, not
 * the model epoch, and the "now" line never runs through a word.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render } from '@testing-library/react'
import { BlackoutTimeline, axisDate } from './BlackoutTimeline'
import { adaptHorizon, adaptSite } from '../lib/api/adapters'
import type { MetricsDTO, WindowsDTO } from '../lib/api/client'
import type { SiteMetrics } from '../lib/types'
import metricsFixture from '../lib/api/__fixtures__/connecting-ridge.metrics.json'
import windowsFixture from '../lib/api/__fixtures__/connecting-ridge.windows.json'

afterEach(cleanup)

const mask = adaptHorizon({
  site_id: 'connecting-ridge',
  azimuth_step_deg: 90,
  azimuth_count: 4,
  el_deg: [0, 0, 0, 0],
  range_m: [0, 0, 0, 0],
  tol_deg: [0, 0, 0, 0],
  max_el_deg: 0,
  max_el_bearing_deg: 0,
  meta: (metricsFixture as unknown as MetricsDTO).meta,
} as never)

const real = (): SiteMetrics =>
  adaptSite('connecting-ridge', windowsFixture as unknown as WindowsDTO, metricsFixture as unknown as MetricsDTO, mask).metrics

/** The same hours, on dates the reader chose: one lunar day from 1 June 2027. */
const june = (): SiteMetrics => ({ ...real(), windowStartIso: '2027-06-01T00:00:00Z', windowHours: 709 })

const ticks = (svg: Element) =>
  [...svg.querySelectorAll('text')]
    .map((t) => (t.textContent ?? '').replace(/ /g, ' '))
    .filter((t) => /^\d{1,2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/.test(t))

describe('BlackoutTimeline', () => {
  it('dates the axis from the dates the reader chose: 1 June to 30 June, not the model epoch', () => {
    const { container } = render(<BlackoutTimeline metrics={june()} cursorH={0} />)
    const svg = container.querySelector('svg')!
    expect(ticks(svg)).toEqual(['1 Jun', '8 Jun', '15 Jun', '23 Jun', '30 Jun'])
    expect((svg.getAttribute('aria-label') ?? '').replace(/ /g, ' ')).toContain('1 Jun 2027 to 30 Jun 2027')
  })

  it('still dates the default dates from 14 March', () => {
    const { container } = render(<BlackoutTimeline metrics={real()} cursorH={0} />)
    const t = ticks(container.querySelector('svg')!)
    expect(t[0]).toBe('14 Mar')
    expect(t[t.length - 1]).toBe('12 Apr')
  })

  it('cuts the "now" line where it would cross a word (V135)', () => {
    const { container } = render(<BlackoutTimeline metrics={june()} cursorH={200} />)
    const line = [...container.querySelectorAll('line')].find((l) => l.getAttribute('y1') === '30')!
    const id = /url\(#(.+)\)/.exec(line.getAttribute('mask') ?? '')?.[1]
    expect(id).toBeTruthy()
    const m = container.querySelector(`mask[id="${id}"]`)!
    const hidden = [...m.querySelectorAll('text')].map((t) => t.textContent)
    expect(hidden).toContain('DARK AND OUT OF CONTACT')
    expect(hidden.some((t) => t?.includes('the longest time dark and out of contact'))).toBe(true)
  })

  it('draws the longest night in the alert hatch only when it runs past the limit by more than its margin', () => {
    // Connecting Ridge's 122 h night carries ±17.1 h: within the margin of 120 h, so not over.
    const alerts = (limitH?: number) => {
      const { container } = render(<BlackoutTimeline metrics={real()} cursorH={0} limitH={limitH} />)
      const n = [...container.querySelectorAll('rect')].filter(
        (r) => r.getAttribute('y') === '36' && r.getAttribute('fill') === 'url(#pw-alert)',
      ).length
      cleanup()
      return n
    }
    expect(alerts(120)).toBe(0)
    expect(alerts(undefined)).toBe(0)
    expect(alerts(80)).toBe(1)
  })

  it('writes a tick as a day, with the time when the dates are short', () => {
    expect(axisDate(Date.UTC(2027, 5, 15, 18, 22), 709)).toBe('15 Jun')
    expect(axisDate(Date.UTC(2027, 5, 15, 18, 22), 48)).toBe('15 Jun 18:22')
  })
})
