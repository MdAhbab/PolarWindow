/**
 * Exports: the arc list as CSV, the arcs as SPICE interval lists, and the
 * comparison as CSV.
 *
 * Built from the same `Arc[]` the charts and `ArcTable` draw, never from a
 * second request or a re-derivation, so the file a planner downloads cannot say
 * something the screen does not. Pure functions over data: the download itself
 * is the only side effect, and it is isolated in `download`.
 */
import type { Arc, CompoundEvent, SiteMetrics } from './types'
import type { Autonomy, Meta } from './api/adapters'

export interface ExportSite {
  id: string
  name: string
  metrics: SiteMetrics
  meta?: Meta
  autonomy?: Autonomy
}

/** The window's opening instant in ms, from the server's own ISO string. */
function originMs(m: SiteMetrics): number {
  if (!m.windowStartIso) {
    throw new Error('this window has no start instant; it cannot be exported to UTC')
  }
  return Date.parse(m.windowStartIso)
}

/** Hours from the window start -> ISO 8601 UTC, to the second. */
export function utcAt(m: SiteMetrics, tH: number): string {
  return new Date(originMs(m) + Math.round(tH * 3600) * 1000)
    .toISOString()
    .replace(/\.\d{3}Z$/, 'Z')
}

/** RFC 4180: quote a field that contains a comma, quote or newline. */
function field(v: string | number | boolean | undefined | null): string {
  if (v === undefined || v === null) return ''
  const s = typeof v === 'number' ? (Number.isFinite(v) ? String(v) : '') : String(v)
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

const row = (cells: (string | number | boolean | undefined | null)[]) => cells.map(field).join(',')
const r3 = (v: number | undefined) => (v === undefined ? undefined : Math.round(v * 1000) / 1000)

/** `#`-prefixed provenance lines, so the file says what produced it. */
function provenance(site: ExportSite, extra: string[] = []): string[] {
  const out = [
    `# POLAR WINDOW export -- site ${site.id} (${site.name})`,
    `# window start ${site.metrics.windowStartIso ?? 'unknown'}, ${r3(site.metrics.windowHours)} h`,
  ]
  const meta = site.meta
  if (meta) {
    const u = meta.uncertainty
    out.push(
      `# engine ${meta.engineVersion}; terrain ${meta.resolution.demProduct}; ephemeris ${meta.resolution.ephemeris}; frame ${meta.resolution.frame}`,
      `# DEM vertical error ${u.demVerticalErrorM} m; edge timing ${
        u.edgeTimingH === null ? 'not timeable (grazing crossing present)' : `+-${r3(u.edgeTimingH)} h`
      }; terrain coverage ${Math.round(u.coverage * 1000) / 10}%`,
    )
  }
  out.push(
    '# open_start/open_end = the window, not the geometry, bounds the arc: its duration is a lower bound.',
    '# Derived values for planning study only; not flight values and not an official product of any space agency.',
    ...extra,
  )
  return out
}

/** The arc list, one row per arc, both bodies interleaved by start time. */
export function arcsCsv(site: ExportSite): string {
  const m = site.metrics
  const arcs: Arc[] = [...m.sun.arcs, ...m.earth.arcs].sort((a, b) => a.startH - b.startH)
  const header = [
    'body',
    'state',
    'start_utc',
    'end_utc',
    'duration_h',
    'tolerance_h',
    'grazing',
    'open_start',
    'open_end',
    'blocked_by_bearing_deg',
    'blocked_by_el_deg',
  ]
  const lines = arcs.map((a) =>
    row([
      a.body,
      a.up ? 'above' : 'below',
      utcAt(m, a.startH),
      utcAt(m, a.endH),
      r3(a.hours),
      a.grazing ? undefined : r3(a.toleranceH),
      a.grazing,
      Boolean(a.openStart),
      Boolean(a.openEnd),
      a.blockedByBearingDeg,
      a.blockedByElDeg,
    ]),
  )
  const compound = m.compound.map((c: CompoundEvent) =>
    row([
      'compound',
      'no sun and no earth',
      utcAt(m, c.startH),
      utcAt(m, c.endH),
      r3(c.hours),
      undefined,
      false,
      Boolean(c.openStart),
      Boolean(c.openEnd),
      undefined,
      undefined,
    ]),
  )
  return [...provenance(site), row(header), ...lines, ...compound].join('\n') + '\n'
}

/**
 * The arcs as SPICE interval lists, one section per state.
 *
 * A SPICE window is an in-memory cell, so there is no standard file for one;
 * the portable form is a list of UTC start/stop pairs that `str2et` + `wninsd`
 * turn back into a window. The header says exactly how.
 */
export function spiceWindows(site: ExportSite): string {
  const m = site.metrics
  const sections: { name: string; what: string; spans: { startH: number; endH: number; open: boolean }[] }[] = [
    {
      name: 'SUN_ABOVE_SKYLINE',
      what: 'Sun centre above the local skyline (lit)',
      spans: m.sun.arcs.filter((a) => a.up).map((a) => ({ ...a, open: Boolean(a.openStart || a.openEnd) })),
    },
    {
      name: 'EARTH_ABOVE_SKYLINE',
      what: 'Earth centre above the local skyline (direct-to-Earth geometry)',
      spans: m.earth.arcs.filter((a) => a.up).map((a) => ({ ...a, open: Boolean(a.openStart || a.openEnd) })),
    },
    {
      name: 'NO_SUN_AND_NO_EARTH',
      what: 'neither body above the skyline (sizes autonomy)',
      spans: m.compound.map((c) => ({ ...c, open: Boolean(c.openStart || c.openEnd) })),
    },
  ]
  const head = provenance(site, [
    '# One interval per line: START STOP, UTC ISO 8601. Intervals clipped by the window are marked "# open".',
    '# To load (spiceypy):',
    '#   cell = spiceypy.cell_double(2 * n)',
    '#   for a, b in pairs: spiceypy.wninsd(spiceypy.str2et(a), spiceypy.str2et(b), cell)',
  ])
  const body = sections.flatMap((sec) => [
    '',
    `BEGIN_WINDOW ${sec.name}  # ${sec.what}; ${sec.spans.length} interval(s)`,
    ...sec.spans.map((s) => `${utcAt(m, s.startH)} ${utcAt(m, s.endH)}${s.open ? '  # open' : ''}`),
    `END_WINDOW ${sec.name}`,
  ])
  return [...head, ...body].join('\n') + '\n'
}

export interface CompareRow {
  site: ExportSite
  rank?: number
  tied?: boolean
}

/** The four numbers for several sites, in the order they are ranked on screen. */
export function comparisonCsv(rows: CompareRow[], rankedBy: string): string {
  const header = [
    'rank',
    'tied',
    'site_id',
    'site',
    'sunlight_h',
    'sun_fraction',
    'earth_contact_h',
    'earth_fraction',
    'longest_dark_h',
    'longest_dark_open',
    'longest_dark_tolerance_h',
    'longest_blackout_h',
    'longest_blackout_open',
    'worst_compound_h',
    'survival_needed_h',
    'required_autonomy_h',
  ]
  const lines = rows.map(({ site, rank, tied }) => {
    const m = site.metrics
    const a = site.autonomy
    return row([
      rank,
      tied,
      site.id,
      site.name,
      r3(m.sun.upHours),
      r3(m.sun.fractionUp),
      r3(m.earth.upHours),
      r3(m.earth.fractionUp),
      r3(m.sun.longestDownH),
      Boolean(m.sun.longestDownOpen),
      m.sun.longestDownArc?.grazing ? undefined : r3(m.sun.longestDownToleranceH),
      r3(m.earth.longestDownH),
      Boolean(m.earth.longestDownOpen),
      r3(m.worstCompoundH),
      r3(a?.survivalNeededH),
      r3(a?.requiredAutonomyH),
    ])
  })
  return (
    [
      `# POLAR WINDOW comparison, ranked by ${rankedBy}. Tied sites share a rank: the data cannot order them.`,
      '# No composite score: the four numbers are reported side by side on purpose.',
      '# *_open = the window, not the geometry, bounds that stretch; the figure is a lower bound.',
      row(header),
      ...lines,
    ].join('\n') + '\n'
  )
}

/** Hand a text file to the browser. The only impure function in this module. */
export function download(filename: string, text: string, mime = 'text/plain'): void {
  const url = URL.createObjectURL(new Blob([text], { type: `${mime};charset=utf-8` }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 0)
}
