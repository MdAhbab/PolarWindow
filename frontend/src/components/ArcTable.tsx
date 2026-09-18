import type { Arc, SiteMetrics } from '../lib/types'
import { bearing, clockUTC, degrees, plusMinus } from '../lib/format'
import { SectionLabel } from './ui'

/**
 * The table twin.
 *
 * The ring, the ribbon and the timeline are three drawings of one arc list.
 * This is that list rendered from the same array, so the screen-reader path
 * and the CSV export are the same path and neither can drift from the picture.
 */
export function ArcTable({ metrics, body }: { metrics: SiteMetrics; body?: 'sun' | 'earth' }) {
  const rows: Arc[] = body
    ? metrics[body].arcs
    : [...metrics.sun.arcs, ...metrics.earth.arcs].sort((a, b) => a.startH - b.startH)

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between gap-4">
        <SectionLabel>Every chart is also a table</SectionLabel>
        <span className="text-[12px] text-ink-3">{rows.length} arcs</span>
      </div>
      <div className="overflow-x-auto border border-line">
        <table className="w-full min-w-[720px] border-collapse text-left">
          <caption className="sr-only">
            Arc list for this site: each stretch above or below the local skyline, with its start, end,
            length, timing uncertainty and, where relevant, the terrain doing the blocking.
          </caption>
          <thead>
            <tr className="bg-inset">
              {['Body', 'State', 'Start', 'End', 'Hours', '±', 'Blocked by'].map((h) => (
                <th
                  key={h}
                  scope="col"
                  className={`px-4 py-3 text-[11px] font-semibold tracking-[0.1em] text-ink-3 uppercase ${
                    h === 'Hours' || h === '±' ? 'text-right' : ''
                  }`}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((a, i) => (
              <tr key={i} className="border-t border-line">
                <td className="px-4 py-2.5 text-[13px]">
                  <span className={a.body === 'sun' ? 'text-sun' : 'text-earth'}>
                    {a.body === 'sun' ? 'Sun' : 'Earth'}
                  </span>
                </td>
                <td className="px-4 py-2.5 font-mono text-[13px] text-ink-2">{a.up ? 'above' : 'below'}</td>
                <td className="px-4 py-2.5 font-mono text-[13px] text-ink-2">{clockUTC(a.startH)}</td>
                <td className="px-4 py-2.5 font-mono text-[13px] text-ink-2">{clockUTC(a.endH)}</td>
                <td className="px-4 py-2.5 text-right font-mono text-[13px] text-ink tnum">{a.hours.toFixed(1)}</td>
                <td className="px-4 py-2.5 text-right font-mono text-[13px] text-uncertain tnum">
                  {a.grazing ? 'grazing' : plusMinus(a.toleranceH, 2)}
                </td>
                <td className="px-4 py-2.5 text-[13px] text-ink-2">
                  {a.up
                    ? '—'
                    : a.blockedByElDeg !== undefined && a.blockedByElDeg > 0.05
                      ? `terrain at ${bearing(a.blockedByBearingDeg ?? 0)}, ${degrees(a.blockedByElDeg, 2)}`
                      : 'below the horizon'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[12px] leading-5 text-ink-3">
        “Grazing” is not a rounding failure. It means the body crosses the skyline so shallowly that the
        crossing time is not knowable at this elevation model’s accuracy — a real finding, and one the
        picture alone would hide.
      </p>
    </div>
  )
}
