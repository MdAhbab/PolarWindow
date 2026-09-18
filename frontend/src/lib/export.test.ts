/**
 * The exports are the only artefact that leaves the browser, so they are the
 * only place where a wrong number survives the session. Every assertion here
 * is against the same fixture the adapter tests use, adapted through the same
 * adapter the screens use — if the file and the screen ever disagree, one of
 * these breaks.
 */
import { describe, expect, it } from 'vitest'
import type { MetricsDTO, WindowsDTO } from './api/client'
import { adaptAutonomy, adaptMeta, adaptSite } from './api/adapters'
import { arcsCsv, comparisonCsv, spiceWindows, utcAt, type ExportSite } from './export'
import metricsFixture from './api/__fixtures__/connecting-ridge.metrics.json'
import windowsFixture from './api/__fixtures__/connecting-ridge.windows.json'

const metrics = metricsFixture as unknown as MetricsDTO
const windows = windowsFixture as unknown as WindowsDTO

const MASK = {
  elDeg: new Float32Array([0]),
  rangeM: new Float32Array([0]),
  tolDeg: new Float32Array([0]),
  maxElDeg: 0,
  maxElBearingDeg: 0,
}

const adapted = adaptSite('connecting-ridge', windows, metrics, MASK)
const site: ExportSite = {
  id: 'connecting-ridge',
  name: 'Connecting Ridge',
  metrics: adapted.metrics,
  meta: adaptMeta(metrics.meta),
  autonomy: adaptAutonomy(metrics),
}

const body = (text: string) => text.split('\n').filter((l) => l && !l.startsWith('#'))

describe('arcsCsv', () => {
  const csv = arcsCsv(site)
  const rows = body(csv)
  const header = rows[0].split(',')
  const cell = (row: string, name: string) => row.split(',')[header.indexOf(name)]

  it('says what produced it, in comment lines a spreadsheet ignores', () => {
    expect(csv).toMatch(/^# POLAR WINDOW export -- site connecting-ridge/)
    expect(csv).toContain('engine hz-2/vis-2')
    expect(csv).toContain('not flight values')
    expect(csv).toContain('open_start/open_end')
  })

  it('emits one row per arc plus the compound events', () => {
    const m = adapted.metrics
    expect(rows.length - 1).toBe(m.sun.arcs.length + m.earth.arcs.length + m.compound.length)
  })

  it('orders the two bodies together, by time', () => {
    const starts = rows.slice(1).map((r) => Date.parse(cell(r, 'start_utc')))
    const arcRows = starts.slice(0, adapted.metrics.sun.arcs.length + adapted.metrics.earth.arcs.length)
    expect(arcRows).toEqual([...arcRows].sort((a, b) => a - b))
  })

  it('writes instants the window start and the arc hours agree on', () => {
    const m = adapted.metrics
    const first = rows[1]
    expect(cell(first, 'start_utc')).toBe(utcAt(m, m.sun.arcs[0].startH))
    expect(Date.parse(cell(first, 'start_utc'))).toBe(Date.parse(m.windowStartIso as string))
  })

  it('carries the window-edge flags, so a censored duration reads as one', () => {
    const firstSun = rows.slice(1).find((r) => cell(r, 'body') === 'sun') as string
    expect(cell(firstSun, 'open_start')).toBe('true')
    const lastSun = rows.slice(1).filter((r) => cell(r, 'body') === 'sun').at(-1) as string
    expect(cell(lastSun, 'open_end')).toBe('true')
  })

  it('leaves the tolerance empty for a grazing crossing rather than faking one', () => {
    const grazing: ExportSite = {
      ...site,
      metrics: {
        ...adapted.metrics,
        sun: {
          ...adapted.metrics.sun,
          arcs: [{ ...adapted.metrics.sun.arcs[0], grazing: true, toleranceH: 99 }],
        },
        earth: { ...adapted.metrics.earth, arcs: [] },
        compound: [],
      },
    }
    const row = body(arcsCsv(grazing))[1]
    expect(row.split(',')[header.indexOf('tolerance_h')]).toBe('')
    expect(row.split(',')[header.indexOf('grazing')]).toBe('true')
  })

  it('quotes any field that would otherwise split a row (RFC 4180)', () => {
    const awkward: ExportSite = { ...site, name: 'Rim, "east" shoulder' }
    expect(arcsCsv(awkward)).toContain('Rim, "east" shoulder')
    const rowsOut = body(comparisonCsv([{ site: awkward, rank: 1 }], 'dark gap'))
    expect(rowsOut[1]).toContain('"Rim, ""east"" shoulder"')
    // One row in, one row out: the comma inside the name did not add a row.
    expect(rowsOut).toHaveLength(2)
  })
})

describe('spiceWindows', () => {
  const text = spiceWindows(site)

  it('tells the reader how to load it', () => {
    expect(text).toContain('spiceypy.wninsd')
    expect(text).toContain('str2et')
  })

  it('has a matched BEGIN/END block for each of the three states', () => {
    for (const name of ['SUN_ABOVE_SKYLINE', 'EARTH_ABOVE_SKYLINE', 'NO_SUN_AND_NO_EARTH']) {
      expect(text).toContain(`BEGIN_WINDOW ${name}`)
      expect(text).toContain(`END_WINDOW ${name}`)
    }
    expect((text.match(/BEGIN_WINDOW/g) ?? []).length).toBe(3)
    expect((text.match(/END_WINDOW/g) ?? []).length).toBe(3)
  })

  it('lists only the intervals where the body is up', () => {
    const block = text.split('BEGIN_WINDOW SUN_ABOVE_SKYLINE')[1].split('END_WINDOW')[0]
    const intervals = block.split('\n').filter((l) => /^\d{4}-/.test(l))
    expect(intervals).toHaveLength(adapted.metrics.sun.arcs.filter((a) => a.up).length)
  })

  it('writes every interval as an increasing UTC pair', () => {
    for (const line of text.split('\n').filter((l) => /^\d{4}-/.test(l))) {
      const [a, b] = line.split('#')[0].trim().split(/\s+/)
      expect(a).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/)
      expect(b).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/)
      expect(Date.parse(b)).toBeGreaterThan(Date.parse(a))
    }
  })

  it('marks the intervals the window cut short', () => {
    const open = text.split('\n').filter((l) => l.endsWith('# open'))
    expect(open.length).toBeGreaterThan(0)
  })
})

describe('comparisonCsv', () => {
  it('reports the four numbers side by side and no composite score', () => {
    const csv = comparisonCsv([{ site, rank: 1 }], 'dark gap')
    const header = body(csv)[0].split(',')
    for (const col of ['sunlight_h', 'earth_contact_h', 'longest_dark_h', 'longest_blackout_h']) {
      expect(header).toContain(col)
    }
    expect(header.join(' ')).not.toMatch(/score|rating|index/)
    expect(csv).toContain('No composite score')
  })

  it('keeps a tie a tie rather than inventing an order', () => {
    const csv = comparisonCsv(
      [
        { site, rank: 1, tied: true },
        { site: { ...site, id: 'other', name: 'Other' }, rank: 1, tied: true },
      ],
      'sunlight',
    )
    const ranks = body(csv)
      .slice(1)
      .map((r) => r.split(',')[0])
    expect(ranks).toEqual(['1', '1'])
  })
})

describe('utcAt', () => {
  it('refuses to guess a window with no start instant', () => {
    const noStart: ExportSite = {
      ...site,
      metrics: { ...adapted.metrics, windowStartIso: undefined },
    }
    expect(() => arcsCsv(noStart)).toThrow(/no start instant/)
  })

  it('rounds to the whole second, which is what a SPICE reader parses', () => {
    expect(utcAt(adapted.metrics, 0)).toMatch(/Z$/)
    expect(utcAt(adapted.metrics, 1 / 3600)).toBe(
      new Date(Date.parse(windows.start) + 1000).toISOString().replace(/\.\d{3}Z$/, 'Z'),
    )
  })
})
