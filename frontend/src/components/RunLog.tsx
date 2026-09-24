import { Fragment, useEffect, useRef, useState } from 'react'
import { useShallow } from 'zustand/react/shallow'
import type { AgentRunDTO, ToolCallDTO } from '../lib/api/client'
import { useAgentRuns } from '../lib/api/queries'
import { useMission } from '../lib/store'
import { shortDate } from '../lib/format'
import { Sheet } from './Sheet'
import { ProblemPanel } from './States'
import { SectionLabel } from './ui'

/**
 * "How the AI got this" (§10.6): every agent run, newest first, with the tool
 * calls behind it. Guard rejections are listed inside the run they belong to,
 * because this drawer is where the guard is shown working rather than claimed.
 */
export function RunLogDrawer() {
  const { open, runId, closeRunLog } = useMission(
    useShallow((s) => ({ open: s.runLog.open, runId: s.runLog.runId, closeRunLog: s.closeRunLog })),
  )
  const runs = useAgentRuns(open)

  return (
    <Sheet open={open} onClose={closeRunLog} title="AI activity log" wide>
      <div className="flex flex-col gap-4 p-5">
        <p className="text-[13px] leading-5 text-ink-2">
          Each run of the site agents: which tools they called, with what, and whether any number in the
          answer failed the check against those tools’ results.
        </p>
        {runs.isPending ? (
          <p role="status" className="font-mono text-[12px] text-ink-3">
            Loading the run log…
          </p>
        ) : runs.error ? (
          <ProblemPanel error={runs.error} fallbackTitle="Cannot load the run log" onRetry={() => void runs.refetch()} />
        ) : !runs.data?.items.length ? (
          <div className="flex flex-col gap-2 border border-line bg-panel p-5">
            <div className="text-[17px] font-semibold text-ink">No AI runs yet.</div>
            <p className="text-[14px] leading-6 text-ink-2">Ask a question to see how the answer is built.</p>
          </div>
        ) : (
          <RunTable runs={runs.data.items} focusId={runId} />
        )}
      </div>
    </Sheet>
  )
}

function timeWords(iso: string): string {
  const ms = Date.parse(iso)
  if (Number.isNaN(ms)) return iso
  const d = new Date(ms)
  const hh = String(d.getUTCHours()).padStart(2, '0')
  const mm = String(d.getUTCMinutes()).padStart(2, '0')
  return `${shortDate(ms)}, ${hh}:${mm} UTC`
}

const STATUS_WORDS: Record<string, string> = {
  ok: 'answered',
  insufficient_data: 'not enough data',
  guard_rejected: 'answer replaced by the guard',
  timeout: 'timed out',
  degraded: 'no AI; measurements only',
  error: 'failed',
}

function RunTable({ runs, focusId }: { runs: AgentRunDTO[]; focusId: string | null }) {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(focusId ? [focusId] : []))
  const focusRow = useRef<HTMLTableRowElement>(null)

  useEffect(() => {
    if (!focusId) return
    setExpanded((s) => new Set(s).add(focusId))
    focusRow.current?.scrollIntoView({ block: 'nearest' })
  }, [focusId])

  const toggle = (id: string) =>
    setExpanded((s) => {
      const n = new Set(s)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })

  return (
    <div className="relative overflow-x-auto border border-line">
      <table className="w-full min-w-[360px] border-collapse text-left">
        <caption className="sr-only">
          Agent runs, newest first: agent, model and time; status; latency, tokens in and out, and
          attempts. Expand a run to see its tool calls.
        </caption>
        <thead>
          <tr className="bg-inset">
            {['Run', 'Status', 'Cost'].map((h) => (
              <th
                key={h}
                scope="col"
                className="px-3 py-2 text-[11px] font-semibold tracking-[0.1em] text-ink-3 uppercase"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => {
            const isOpen = expanded.has(r.id)
            const focused = r.id === focusId
            return (
              <Fragment key={r.id}>
                <tr
                  ref={focused ? focusRow : undefined}
                  className={`border-t border-line align-top ${focused ? 'bg-inset' : ''}`}
                >
                  <td className="px-3 py-2">
                    <button
                      type="button"
                      aria-expanded={isOpen}
                      aria-controls={`run-${r.id}`}
                      onClick={() => toggle(r.id)}
                      className="-mx-2 flex min-h-11 items-start gap-2 px-2 py-1 text-left text-[13px] font-semibold text-ink hover:bg-inset"
                    >
                      <span aria-hidden="true" className={`text-ink-3 ${isOpen ? 'rotate-90' : ''}`}>
                        ›
                      </span>
                      <span className="flex flex-col">
                        <span>{r.agent}</span>
                        <span className="font-mono text-[11px] font-normal whitespace-nowrap text-ink-3">{r.model}</span>
                        <span className="text-[11px] font-normal text-ink-3">{timeWords(r.created_at)}</span>
                      </span>
                    </button>
                  </td>
                  <td className="px-3 py-2 text-[13px] text-ink-2">{STATUS_WORDS[r.status] ?? r.status}</td>
                  <td className="px-3 py-2 font-mono text-[12px] leading-5 whitespace-nowrap text-ink-2 tnum">
                    {r.latency_ms} ms
                    <br />
                    {r.prompt_tokens} / {r.completion_tokens} tokens
                    <br />
                    {r.attempts} {r.attempts === 1 ? 'attempt' : 'attempts'}
                  </td>
                </tr>
                {isOpen && (
                  <tr id={`run-${r.id}`} className="border-t border-line bg-canvas">
                    <td colSpan={3} className="px-3 py-3">
                      <RunDetail run={r} />
                    </td>
                  </tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

interface GuardFailure {
  kind?: string
  detail?: string
  value?: number | null
}

function guardLine(g: GuardFailure): string {
  if ((g.kind === 'ungrounded_number' || g.kind === 'ungrounded_no_tools') && typeof g.value === 'number') {
    return `Rejected: ${g.value} not found in tool results`
  }
  return `Rejected: ${g.detail ?? g.kind ?? 'a check failed'}`
}

function RunDetail({ run }: { run: AgentRunDTO }) {
  const guards = (run.guard_failures ?? []) as GuardFailure[]
  return (
    <div className="flex flex-col gap-3">
      {guards.length > 0 && (
        <ul className="flex flex-col gap-1">
          {guards.map((g, i) => (
            <li key={i} className="text-[13px] leading-5 font-semibold text-ink">
              {guardLine(g)}
              {g.detail && g.kind === 'ungrounded_number' && (
                <span className="block text-[12px] font-normal text-ink-2">{g.detail}</span>
              )}
            </li>
          ))}
        </ul>
      )}
      <SectionLabel as="h3">Tool calls</SectionLabel>
      {run.tool_calls.length === 0 ? (
        <p className="text-[13px] text-ink-2">No tools were called in this run.</p>
      ) : (
        <table className="w-full border-collapse text-left">
          <caption className="sr-only">Tool calls in this run, in order.</caption>
          <thead>
            <tr>
              {['#', 'Tool', 'Arguments', 'Latency', 'Error'].map((h) => (
                <th key={h} scope="col" className="py-1.5 pr-3 text-[11px] font-semibold tracking-[0.1em] text-ink-3 uppercase">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {run.tool_calls.map((c) => (
              <ToolRow key={c.seq} call={c} />
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function ToolRow({ call }: { call: ToolCallDTO }) {
  const [all, setAll] = useState(false)
  const args = JSON.stringify(call.args, null, 1).replace(/\n\s*/g, ' ')
  const long = args.length > 120
  return (
    <tr className="border-t border-line align-top">
      <td className="py-1.5 pr-3 font-mono text-[12px] text-ink-3 tnum">{call.seq}</td>
      <td className="py-1.5 pr-3 font-mono text-[12px] text-ink">{call.tool}</td>
      <td className="max-w-[220px] py-1.5 pr-3">
        <span className={`font-mono text-[12px] break-all text-ink-2 ${all ? '' : 'line-clamp-3'}`}>{args}</span>
        {long && (
          <button
            type="button"
            onClick={() => setAll((v) => !v)}
            aria-expanded={all}
            className="min-h-11 text-[12px] font-semibold text-ink underline underline-offset-2"
          >
            {all ? 'Show less' : 'Show all'}
          </button>
        )}
      </td>
      <td className="py-1.5 pr-3 font-mono text-[12px] whitespace-nowrap text-ink-2 tnum">{call.latency_ms} ms</td>
      <td className="py-1.5 text-[12px] text-ink-2">{call.error ?? 'none'}</td>
    </tr>
  )
}
