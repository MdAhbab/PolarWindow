import { useEffect, useId, useMemo, useRef, useState } from 'react'
import type { Mission } from '../lib/api/adapters'
import {
  STATUS_GLYPH,
  STATUS_LABEL,
  missionDate,
  missionDateWords,
  publishedTitle,
  publishedWords,
} from '../lib/missions'
import { Icon } from './Icon'
import { Button, SectionLabel, Unconfirmed } from './ui'

/**
 * The programme timeline (§10.2), in the Ribbon idiom: one lane per provider,
 * years across. A landing known to the day is a 2 px tick in ink; one known
 * only to the month, quarter or year is a bar across that whole period, in
 * the uncertain −45° hatch, so date uncertainty is drawn with the vocabulary
 * the app already uses for a margin. The status glyph after each mark is
 * text, and never the only signal: the table twin says it in words.
 */

/** Drawn at 1:1 so its type stays at the system's sizes; narrower screens scroll. */
const MIN_W = 860
const LABEL_W = 176
const PAD_R = 24
const ROW_H = 24
const AXIS_H = 28
const TOP = 22

function yearStart(y: number) {
  return Date.UTC(y, 0, 1)
}

interface Placed {
  m: Mission
  x0: number
  x1: number
  tick: boolean
  row: number
  /** The label sits left of the mark when it would run off the right edge. */
  labelLeft: boolean
}

/** The container's width, so the SVG's user unit is one CSS pixel. */
function useWidth<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null)
  const [w, setW] = useState(960)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const on = () => setW(Math.max(MIN_W, Math.floor(el.clientWidth)))
    on()
    const ro = new ResizeObserver(on)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, w]
}

export function ProgrammeTimeline({
  missions,
  highlight,
  onHover,
  showTable,
  onToggleTable,
  nowMs,
}: {
  missions: Mission[]
  highlight: Set<string>
  onHover: (id: string | null) => void
  showTable: boolean
  onToggleTable: () => void
  /** The client clock, for the one labelled "Today" rule. */
  nowMs: number
}) {
  const regionId = useId()
  const [boxRef, W] = useWidth<HTMLDivElement>()
  const undated = missions.filter((m) => !missionDate(m))

  const { dated, lanes, x, years, height } = useMemo(() => {
    const dated = missions.filter((m) => missionDate(m))
    const spans = dated.map((m) => missionDate(m)!.date)
    const minYear = Math.min(2024, ...spans.map((d) => new Date(d.startMs).getUTCFullYear()))
    // "2024 → last dated mission + 1 y": the axis ends a year after the end of
    // the latest span, so a year-precision bar never runs off the edge.
    const lastEnd = spans.length ? Math.max(...spans.map((d) => d.endMs)) : yearStart(2027)
    const maxYear = new Date(lastEnd - 1).getUTCFullYear() + 1
    const t0 = yearStart(minYear)
    const t1 = yearStart(maxYear + 1)
    const xf = (ms: number) => LABEL_W + ((ms - t0) / (t1 - t0)) * (W - LABEL_W - PAD_R)

    const byProvider = new Map<string, Mission[]>()
    for (const m of dated) {
      const k = m.provider ?? ''
      byProvider.set(k, [...(byProvider.get(k) ?? []), m])
    }
    const providerOrder = [...byProvider.keys()].sort((a, b) => {
      if (!a) return 1
      if (!b) return -1
      const fa = Math.min(...byProvider.get(a)!.map((m) => missionDate(m)!.date.startMs))
      const fb = Math.min(...byProvider.get(b)!.map((m) => missionDate(m)!.date.startMs))
      return fa - fb || a.localeCompare(b)
    })

    let y = TOP
    const laneList = providerOrder.map((provider) => {
      const ms = [...byProvider.get(provider)!].sort(
        (a, b) => missionDate(a)!.date.startMs - missionDate(b)!.date.startMs,
      )
      // Greedy row packing so marks and their labels never overlap in a lane.
      const rowEnds: number[] = []
      const placed: Placed[] = ms.map((m) => {
        const d = missionDate(m)!.date
        const tick = d.precision === 'day' || d.precision === 'minute'
        const x0 = xf(d.startMs)
        const x1 = tick ? x0 + 2 : Math.max(x0 + 2, xf(d.endMs))
        const labelW = (m.name.length + 2) * 6.8
        const labelLeft = x1 + 6 + labelW > W - 4
        const from = labelLeft ? x0 - 6 - labelW : x0
        const to = labelLeft ? x1 : x1 + 6 + labelW
        let row = rowEnds.findIndex((end) => end < from - 4)
        if (row === -1) {
          row = rowEnds.length
          rowEnds.push(to)
        } else rowEnds[row] = to
        return { m, x0, x1, tick, row, labelLeft }
      })
      const lane = { provider, placed, y, rows: Math.max(1, rowEnds.length) }
      y += lane.rows * ROW_H + 10
      return lane
    })
    const ys: number[] = []
    for (let yr = minYear; yr <= maxYear + 1; yr++) ys.push(yr)
    return { dated, lanes: laneList, x: xf, years: ys, height: y + AXIS_H }
  }, [missions, W])

  const today = x(nowMs)
  const inRange = today >= LABEL_W && today <= W - PAD_R

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SectionLabel>Programme timeline</SectionLabel>
        <Button size="sm" onClick={onToggleTable} expanded={showTable} controls={`${regionId}-table`}>
          <Icon name="table" size={16} strokeWidth={1.7} />
          {showTable ? 'Hide the timeline table' : 'Read the timeline as a table'}
        </Button>
      </div>

      <div
        ref={boxRef}
        role="region"
        aria-label="Programme timeline, scrolls sideways"
        tabIndex={0}
        className="relative overflow-x-auto border border-line bg-panel"
      >
        <svg
          width={W}
          height={height}
          viewBox={`0 0 ${W} ${height}`}
          className="block"
          role="img"
          aria-label={`Programme timeline from ${years[0]} to ${years[years.length - 1]}: ${dated.length} dated mission${
            dated.length === 1 ? '' : 's'
          } in ${lanes.length} provider lane${lanes.length === 1 ? '' : 's'}. A tick is a date known to the day; a hatched bar is a date known only to the month, quarter or year. The table twin lists every mission.`}
        >
          {years.map((yr) => {
            const xx = x(yearStart(yr))
            return (
              <g key={yr}>
                <path d={`M${xx} ${TOP - 8} V${height - AXIS_H + 4}`} stroke="var(--color-line)" strokeWidth="1" />
                {yr < years[years.length - 1] && (
                  <text
                    x={xx + 4}
                    y={height - 8}
                    fontFamily="var(--font-mono)"
                    fontSize="11"
                    fill="var(--color-ink-3)"
                  >
                    {yr}
                  </text>
                )}
              </g>
            )
          })}

          {lanes.map((lane) => (
            <g key={lane.provider || 'unconfirmed'}>
              <text
                x={8}
                y={lane.y + ROW_H / 2 + 4}
                fontFamily="var(--font-sans)"
                fontSize="12"
                fontWeight="600"
                fill={lane.provider ? 'var(--color-ink-2)' : 'var(--color-uncertain)'}
              >
                {lane.provider || 'Provider unconfirmed'}
              </text>
              <path
                d={`M${LABEL_W} ${lane.y + lane.rows * ROW_H + 4} H${W - PAD_R}`}
                stroke="var(--color-line)"
                strokeWidth="1"
              />
              {lane.placed.map((p) => {
                const on = highlight.has(p.m.id)
                const cy = lane.y + p.row * ROW_H + ROW_H / 2
                return (
                  <g
                    key={p.m.id}
                    onMouseEnter={() => onHover(p.m.id)}
                    onMouseLeave={() => onHover(null)}
                    className="cursor-default"
                  >
                    <title>{`${p.m.name}: ${missionDateWords(p.m)}, ${STATUS_LABEL[p.m.status]}`}</title>
                    {p.tick ? (
                      <rect x={p.x0} y={cy - 9} width={on ? 3 : 2} height="18" fill="var(--color-ink)" />
                    ) : (
                      <rect
                        x={p.x0}
                        y={cy - 7}
                        width={p.x1 - p.x0}
                        height="14"
                        fill="url(#pw-uncertain)"
                        stroke={on ? 'var(--color-ink)' : 'var(--color-line-strong)'}
                        strokeWidth={on ? 2 : 1}
                      />
                    )}
                    <text
                      x={p.labelLeft ? p.x0 - 5 : p.x1 + 5}
                      y={cy + 4}
                      textAnchor={p.labelLeft ? 'end' : 'start'}
                      fontFamily="var(--font-sans)"
                      fontSize="12"
                      fontWeight={on ? 700 : 500}
                      fill={on ? 'var(--color-ink)' : 'var(--color-ink-2)'}
                    >
                      {STATUS_GLYPH[p.m.status]} {p.m.name}
                    </text>
                  </g>
                )
              })}
            </g>
          ))}

          {inRange && (
            <g>
              <path d={`M${today} ${TOP - 12} V${height - AXIS_H + 4}`} stroke="var(--color-line-strong)" strokeWidth="2" />
              <text
                x={today + 4}
                y={TOP - 4}
                fontFamily="var(--font-sans)"
                fontSize="11"
                fontWeight="600"
                fill="var(--color-ink)"
              >
                Today
              </text>
            </g>
          )}
        </svg>
      </div>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-caption text-ink-2">
        <span className="flex items-center gap-2">
          <span className="h-3.5 w-0.5 bg-ink" aria-hidden="true" /> date known to the day
        </span>
        <span className="flex items-center gap-2">
          <span className="hatch-uncertain h-3 w-6 border border-line-strong" aria-hidden="true" /> known only to
          the month, quarter or year
        </span>
        <span>✓ completed · ◐ partly successful · ✕ failed or lost · ○ planned · → in transit</span>
      </div>

      {undated.length > 0 && (
        <p className="text-small leading-5 text-ink-2">
          Not on the timeline, because no landing or launch date is published:{' '}
          {undated.map((m) => m.name).join(', ')}.
        </p>
      )}

      {showTable && (
        <div id={`${regionId}-table`} className="relative overflow-x-auto border border-line">
          <table className="w-full min-w-[640px] border-collapse text-left">
            <caption className="sr-only">
              Every mission shown: provider, date as published with its precision, and status.
            </caption>
            <thead>
              <tr className="bg-inset">
                {['Mission', 'Provider', 'Date (as published)', 'Status'].map((h) => (
                  <th
                    key={h}
                    scope="col"
                    className="px-4 py-3 text-tag font-semibold tracking-caps-md text-ink-3 uppercase"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {missions.map((m) => {
                const d = missionDate(m)
                return (
                  <tr key={m.id} className="border-t border-line">
                    <th scope="row" className="px-4 py-2.5 text-small font-semibold text-ink">
                      {m.name}
                    </th>
                    <td className="px-4 py-2.5 text-small text-ink-2">{m.provider ?? <Unconfirmed />}</td>
                    <td className="px-4 py-2.5 text-small text-ink-2">
                      {d ? (
                        <span title={publishedTitle(d.date)}>
                          {`${d.which === 'launch' ? 'Launch: ' : ''}${publishedWords(d.date)}`}
                        </span>
                      ) : (
                        <Unconfirmed />
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-small text-ink-2">
                      <span aria-hidden="true">{STATUS_GLYPH[m.status]} </span>
                      {STATUS_LABEL[m.status]}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
