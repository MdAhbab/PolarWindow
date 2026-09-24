import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { useMission, windowFromInstants } from '../lib/store'
import { useCalendar } from '../lib/api/queries'
import type { CalendarBucket } from '../lib/api/adapters'
import { modelHFromMs, monthWords, msFromModelH, windowLine } from '../lib/format'
import { Button, Segmented } from './ui'

/**
 * The window picker and month strip (§10.4), shared by Site and Mission detail.
 *
 * It drives `setWindow` and nothing else: every number that moves when the
 * window moves comes from a query whose key the window is part of. Superseded
 * requests are cancelled through their `signal` and the previous numbers stay
 * on screen until the next arrive (`keepPreviousData`), so a burst of changes
 * leaves one request in flight per site, not a queue.
 */

const MONTH_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

const monthStart = (ms: number) => {
  const d = new Date(ms)
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1)
}
const addMonths = (ms: number, n: number) => {
  const d = new Date(ms)
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + n, 1)
}
const isoZ = (ms: number) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, 'Z')
const dayInput = (ms: number) => new Date(ms).toISOString().slice(0, 10)

type Duration = 'mission' | '14' | '30' | '90' | '365'

export function WindowPicker({
  siteId,
  missionWindow,
}: {
  siteId: string
  /** The mission's surface window, when it has one: enables the "Mission" duration. */
  missionWindow?: { startMs: number; endMs: number } | null
}) {
  const { windowStartH, windowHours, setWindow } = useMission(
    useShallow((s) => ({
      windowStartH: s.windowStartH,
      windowHours: s.windowHours,
      setWindow: s.setWindow,
    })),
  )
  const id = useId()
  const startMs = msFromModelH(windowStartH)

  const durations: { value: Duration; label: string }[] = [
    ...(missionWindow ? [{ value: 'mission' as const, label: 'Mission' }] : []),
    { value: '14', label: '14 d' },
    { value: '30', label: '30 d' },
    { value: '90', label: '90 d' },
    { value: '365', label: '1 y' },
  ]

  const current: Duration | '' = (() => {
    if (
      missionWindow &&
      Math.abs(startMs - missionWindow.startMs) < 60_000 &&
      Math.abs(windowHours - (missionWindow.endMs - missionWindow.startMs) / 3_600_000) < 0.02
    )
      return 'mission'
    for (const d of ['14', '30', '90', '365'] as const) {
      if (Math.abs(windowHours - Number(d) * 24) < 0.01) return d
    }
    return ''
  })()

  const setSpan = (fromMs: number, toMs: number) => {
    const w = windowFromInstants(fromMs, toMs)
    setWindow(w.startH, w.hours)
  }

  const onDuration = (d: Duration | '') => {
    if (d === '') return
    if (d === 'mission' && missionWindow) setSpan(missionWindow.startMs, missionWindow.endMs)
    else setWindow(windowStartH, Number(d) * 24)
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
        <div className="flex flex-col gap-2">
          <label htmlFor={`${id}-start`} className="text-[13px] font-medium text-ink">
            Start (UTC)
          </label>
          <div className="flex h-12 items-center rounded-control border border-line-strong bg-panel px-3.5 focus-within:border-focus">
            <input
              id={`${id}-start`}
              type="date"
              value={dayInput(startMs)}
              min="2020-01-01"
              max="2040-12-31"
              onChange={(e) => {
                const ms = Date.parse(`${e.target.value}T00:00:00Z`)
                if (!Number.isNaN(ms)) setWindow(modelHFromMs(ms), windowHours)
              }}
              className="bg-transparent text-[14px] text-ink outline-none"
            />
          </div>
        </div>
        <div className="flex min-w-0 max-w-full flex-col gap-2">
          <span id={`${id}-dur`} className="text-[13px] font-medium text-ink">
            Duration
          </span>
          <Segmented<Duration | ''>
            label="Duration"
            options={durations}
            value={current}
            onChange={onDuration}
          />
        </div>
      </div>

      <p aria-live="polite" className="text-[14px] text-ink">
        <span className="sr-only">Window set to </span>
        {windowLine(startMs, windowHours)}
      </p>

      <MonthStrip siteId={siteId} startMs={startMs} onPick={setSpan} />
    </div>
  )
}

function MonthStrip({
  siteId,
  startMs,
  onPick,
}: {
  siteId: string
  startMs: number
  onPick: (fromMs: number, toMs: number) => void
}) {
  // The strip stays put when a cell in it is picked; it re-anchors only when
  // the window starts outside the twelve months it shows, so the cell that was
  // just clicked does not jump out from under the pointer.
  const [anchor, setAnchor] = useState(() => monthStart(startMs))
  useEffect(() => {
    if (startMs < anchor || startMs >= addMonths(anchor, 12)) setAnchor(monthStart(startMs))
  }, [startMs, anchor])

  const span = useMemo(() => ({ start: isoZ(anchor), end: isoZ(addMonths(anchor, 12)) }), [anchor])
  const cal = useCalendar(siteId, span, 'month')
  const fresh = cal.data && cal.data.startIso.slice(0, 10) === span.start.slice(0, 10) && cal.data.siteId === siteId

  const cells: { startMs: number; endMs: number; bucket?: CalendarBucket }[] = useMemo(
    () =>
      Array.from({ length: 12 }, (_, i) => {
        const s = addMonths(anchor, i)
        const e = addMonths(anchor, i + 1)
        const bucket = fresh ? cal.data?.items.find((b) => Math.abs(b.startMs - s) < 3_600_000) : undefined
        return { startMs: s, endMs: e, bucket }
      }),
    [anchor, cal.data, fresh],
  )

  const selected = cells.findIndex((c) => startMs >= c.startMs && startMs < c.endMs)
  const [focusIdx, setFocusIdx] = useState(selected >= 0 ? selected : 0)
  const refs = useRef<(HTMLDivElement | null)[]>([])

  useEffect(() => {
    if (selected >= 0) setFocusIdx(selected)
  }, [selected])

  const move = (i: number) => {
    const n = Math.max(0, Math.min(11, i))
    setFocusIdx(n)
    refs.current[n]?.focus()
  }

  const onKey = (e: KeyboardEvent<HTMLDivElement>, i: number) => {
    switch (e.key) {
      case 'ArrowRight':
      case 'ArrowDown':
        e.preventDefault()
        move(i + 1)
        break
      case 'ArrowLeft':
      case 'ArrowUp':
        e.preventDefault()
        move(i - 1)
        break
      case 'Home':
        e.preventDefault()
        move(0)
        break
      case 'End':
        e.preventDefault()
        move(11)
        break
      case 'Enter':
      case ' ':
        e.preventDefault()
        onPick(cells[i].startMs, cells[i].endMs)
        break
    }
  }

  const labelId = useId()

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span id={labelId} className="text-[13px] font-medium text-ink">
          Months from {monthWords(anchor)}: pick one to use it as the window
        </span>
        <span className="flex items-center gap-3 text-[12px] text-ink-3" aria-hidden="true">
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-1.5 bg-sun-fill" /> sunlight
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-1.5 bg-earth-fill" /> Earth
          </span>
          <span className="flex items-center gap-1.5">
            <span className="hatch-uncertain h-1.5 w-4" /> night runs past the month
          </span>
        </span>
      </div>

      <div className="relative overflow-x-auto">
        <div
          role="listbox"
          aria-labelledby={labelId}
          aria-orientation="horizontal"
          className="grid min-w-[576px] grid-cols-12 gap-1"
        >
          {cells.map((c, i) => {
            const b = c.bucket
            const d = new Date(c.startMs)
            const showYear = i === 0 || d.getUTCMonth() === 0
            const name = b
              ? `${monthWords(c.startMs)}: sunlight ${Math.round(b.sunFraction * 100)} percent, Earth ${Math.round(
                  b.earthFraction * 100,
                )} percent${b.longestDarkOpen ? ', its longest night runs past the month' : ''}`
              : `${monthWords(c.startMs)}: ${cal.error ? 'not available' : 'loading'}`
            return (
              <div
                key={c.startMs}
                ref={(el) => {
                  refs.current[i] = el
                }}
                role="option"
                aria-selected={i === selected}
                aria-label={name}
                tabIndex={i === focusIdx ? 0 : -1}
                onClick={() => onPick(c.startMs, c.endMs)}
                onKeyDown={(e) => onKey(e, i)}
                onFocus={() => setFocusIdx(i)}
                className={`flex min-h-11 cursor-pointer flex-col gap-1 border p-1.5 ${
                  i === selected ? 'border-ink bg-inset' : 'border-line hover:bg-inset'
                } ${cal.isPlaceholderData || !fresh ? 'opacity-60' : ''}`}
              >
                <div className="relative flex h-10 items-end justify-center gap-1 bg-dark-fill">
                  {b && (
                    <>
                      <span className="w-1.5 bg-sun-fill" style={{ height: `${b.sunFraction * 100}%` }} />
                      <span className="w-1.5 bg-earth-fill" style={{ height: `${b.earthFraction * 100}%` }} />
                    </>
                  )}
                  {b?.longestDarkOpen && (
                    <span className="hatch-uncertain absolute inset-x-0 bottom-0 h-1.5" aria-hidden="true" />
                  )}
                </div>
                <span className="text-center text-[11px] leading-4 font-semibold text-ink-2">
                  {MONTH_SHORT[d.getUTCMonth()]}
                  {showYear && <span className="block font-normal text-ink-3">{d.getUTCFullYear()}</span>}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      {cal.error && !cal.data ? (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-[13px] text-ink-2">
            {(cal.error as { title?: string }).title ?? 'The month strip could not load'}.{' '}
            {(cal.error as { stillWorks?: string }).stillWorks ?? ''}
          </p>
          <Button size="sm" onClick={() => void cal.refetch()}>
            Retry
          </Button>
        </div>
      ) : cal.isPending ? (
        <p role="status" className="text-[12px] text-ink-3">
          Reading twelve months of Sun and Earth for this site…
        </p>
      ) : null}
    </div>
  )
}
