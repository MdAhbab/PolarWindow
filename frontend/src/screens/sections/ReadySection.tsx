import { useState } from 'react'
import { api } from '../../lib/api/client'
import type { MissionDetail } from '../../lib/api/adapters'
import type { LifecycleMetaDTO, PartDTO, ReadyDTO, ReadyItemDTO, RiskDTO } from '../../lib/api/lifecycle'
import {
  useLandingHistory,
  useLessons,
  useLifecycleWrite,
  useParts,
  useRiskScales,
  useSection,
  useSectionStatus,
} from '../../lib/api/lifecycleQueries'
import { useSession } from '../../lib/session'
import { hostWords, quantityText, quantityView } from '../../lib/lifecycle/quantity'
import { CountTile, NumberRow, QuantityTile } from '../../components/lifecycle/QuantityTile'
import { Answer, ChartPanel, HowSure, Rows, SectionLayout, SectionStates, SourcesRow, StatePanel } from '../../components/lifecycle/Section'
import {
  LandingHistoryTable,
  PartsTable,
  ReadinessList,
  ReadinessTable,
  RiskGrid,
  RiskTable,
  TREND_WORDS,
  landingCountsSentence,
  sortItems,
} from '../../components/lifecycle/Readiness'
import { Button, Disclosure, SectionLabel } from '../../components/ui'
import { Icon } from '../../components/Icon'
import { AddItemSheet, PartSheet, ReadyItemSheet, RiskSheet } from './ReadyForms'

const TERMS = ['itemsReady', 'blocked', 'nextMilestone', 'spares']

/** Whether this visitor can enter records: a live session (a name is asked for on the first save). */
export function useCanWrite(): boolean {
  const s = useSession((x) => x.session)
  return Boolean(s && !s.offline)
}

/**
 * Ready (design-lifecycle.md §4): what is ready, what is holding it up, and
 * the risks, parts and history behind it. Counts, never a percentage.
 */
export function ReadySection({ mission: m }: { mission: MissionDetail }) {
  const view = useSection<ReadyDTO>('ready', m.id, (signal) => api.ready(m.id, signal))
  const status = useSectionStatus(m.id, 'ready')
  return (
    <SectionLayout question="What is ready, and what is holding it up?">
      <SectionStates view={view} terms={TERMS} status={status}>
        {({ data, meta }) => <ReadyAnswer ready={data} meta={meta} missionId={m.id} needsInput={status?.state === 'needs_input'} />}
      </SectionStates>
    </SectionLayout>
  )
}

function ReadyAnswer({
  ready,
  meta,
  missionId,
  needsInput,
}: {
  ready: ReadyDTO
  meta: LifecycleMetaDTO
  missionId: string
  needsInput: boolean
}) {
  const canWrite = useCanWrite()
  const [changing, setChanging] = useState<ReadyItemDTO | null>(null)
  const [adding, setAdding] = useState(false)
  const total = ready.items.length
  const blocked = sortItems(ready.items).filter((i) => i.state === 'blocked')
  const next = ready.milestones
    .filter((x) => !x.done && x.date.value !== null)
    .sort((a, b) => (a.date.value as number) - (b.date.value as number))[0]

  const sheets = (
    <>
      <ReadyItemSheet item={changing} onClose={() => setChanging(null)} />
      <AddItemSheet open={adding} onClose={() => setAdding(false)} missionId={missionId} />
    </>
  )
  const addButton = canWrite && (
    <Button onClick={() => setAdding(true)}>
      <Icon name="plus" size={16} />
      Add an item
    </Button>
  )

  if (!total) {
    return (
      <>
        <StatePanel
          icon={needsInput ? 'pencil' : 'ring'}
          title="No readiness items entered yet"
          detail="Readiness is entered by the project team: the lander, each payload and rover, the launch vehicle and range, ground-station bookings, relay agreements, the operations team and the licences, each moved on with a date and evidence."
          stillWorks="Every other step, and the landing history and lessons below, work without it."
          action={addButton}
        />
        <Rows>
          <HistoryRows ready={ready} missionId={missionId} canWrite={canWrite} />
          <SourcesRow meta={meta} />
        </Rows>
        {sheets}
      </>
    )
  }

  return (
    <>
      <Answer meta={meta}>
        {ready.counts.ready} of {total} items are ready
        {blocked.length ? (
          <>
            ; {blocked.length} blocked: {blocked.slice(0, 2).map((b) => b.name).join(' and ')}
            {blocked.length > 2 ? ` and ${blocked.length - 2} more` : ''}.
          </>
        ) : (
          '; none is blocked.'
        )}
      </Answer>
      <NumberRow>
        <CountTile term="itemsReady" value={ready.counts.ready} of={total} />
        <CountTile
          term="blocked"
          value={blocked.length}
          icon={blocked.length ? 'alert' : undefined}
          note={blocked[0] ? `${blocked[0].name}${blocked[0].blocked_reason ? `: ${blocked[0].blocked_reason}` : ''}` : 'Nothing is blocked'}
        />
        {next ? (
          <QuantityTile term="nextMilestone" q={next.date} note={next.name} />
        ) : (
          <CountTile term="nextMilestone" value={0} note="No milestone to come is entered" />
        )}
        <CountTile
          term="spares"
          value={ready.parts.spares}
          note={`${ready.parts.lost} lost, ${ready.parts.damaged} damaged, ${ready.parts.failed} failed, of ${ready.parts.total} parts`}
        />
      </NumberRow>
      <ChartPanel
        title="Every item, blocked first"
        guide="ready-list"
        chart={<ReadinessList items={ready.items} onChange={canWrite ? setChanging : undefined} />}
        table={<ReadinessTable items={ready.items} />}
      />
      {addButton && <div>{addButton}</div>}
      <Rows>
        <RiskRow risks={ready.risks} missionId={missionId} canWrite={canWrite} />
        <PartsRow ready={ready} missionId={missionId} canWrite={canWrite} />
        <Disclosure title="Milestones" meta={`${ready.milestones.filter((x) => !x.done).length} to come`}>
          {ready.milestones.length ? (
            <ul className="flex flex-col divide-y divide-line border-y border-line">
              {[...ready.milestones]
                .sort((a, b) => (a.date.value ?? 0) - (b.date.value ?? 0))
                .map((x) => (
                  <li key={x.id} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2.5">
                    <span className="text-body text-ink">
                      {x.done && <Icon name="check" size={14} strokeWidth={2.4} className="mr-1.5 inline" />}
                      {x.name}
                    </span>
                    <span className="text-small text-ink-2">
                      {quantityText(x.date)}
                      {x.done ? ', done' : ''}
                      {quantityView(x.date).provenance === 'entered' && x.date.source ? ` · entered by ${x.date.source}` : ''}
                    </span>
                  </li>
                ))}
            </ul>
          ) : (
            <p className="text-body text-ink-2">No milestones entered yet.</p>
          )}
        </Disclosure>
        <HistoryRows ready={ready} missionId={missionId} canWrite={canWrite} />
        <HowSure meta={meta} />
        <SourcesRow meta={meta} />
      </Rows>
      {sheets}
    </>
  )
}

function RiskRow({ risks, missionId, canWrite }: { risks: RiskDTO[]; missionId: string; canWrite: boolean }) {
  const [open, setOpen] = useState(false)
  const scales = useRiskScales(open)
  const scale = scales.data?.scales.find((s) => s.id === (risks[0]?.scale_id ?? scales.data?.default_id)) ?? scales.data?.scales[0]
  const [editing, setEditing] = useState<RiskDTO | null>(null)
  const [adding, setAdding] = useState(false)
  const rising = risks.filter((r) => r.trend === 'rising').length
  return (
    <Disclosure
      title="Risks"
      meta={`${risks.length}${rising ? `, ${rising} ${TREND_WORDS.rising.words.toLowerCase()}` : ''}`}
      onOpen={() => setOpen(true)}
    >
      {risks.length ? (
        <>
          <RiskGrid risks={risks} scale={scale} />
          <RiskTable risks={risks} onChange={canWrite ? setEditing : undefined} />
        </>
      ) : (
        <p className="text-body text-ink-2">No risks entered yet.</p>
      )}
      {canWrite && (
        <div>
          <Button onClick={() => setAdding(true)}>
            <Icon name="plus" size={16} />
            Add a risk
          </Button>
        </div>
      )}
      <RiskSheet
        open={adding || Boolean(editing)}
        risk={editing}
        onClose={() => {
          setAdding(false)
          setEditing(null)
        }}
        missionId={missionId}
        scale={scale}
      />
    </Disclosure>
  )
}

function PartsRow({ ready, missionId, canWrite }: { ready: ReadyDTO; missionId: string; canWrite: boolean }) {
  const [open, setOpen] = useState(false)
  const parts = useParts(missionId, open)
  const [editing, setEditing] = useState<PartDTO | null>(null)
  const [adding, setAdding] = useState(false)
  const p = ready.parts
  return (
    <Disclosure title="Parts" meta={`${p.total}; ${p.spares} spares, ${p.lost} lost`} onOpen={() => setOpen(true)}>
      {parts.isPending ? (
        <p className="text-small text-ink-3">Loading the parts…</p>
      ) : parts.error ? (
        <p className="text-small text-ink-2">The parts list could not be loaded: {(parts.error as Error).message}</p>
      ) : parts.data?.parts.length ? (
        <PartsTable parts={parts.data.parts} items={ready.items} onChange={canWrite ? setEditing : undefined} />
      ) : (
        <p className="text-body text-ink-2">No parts entered yet.</p>
      )}
      {canWrite && (
        <div>
          <Button onClick={() => setAdding(true)}>
            <Icon name="plus" size={16} />
            Add a part
          </Button>
        </div>
      )}
      <PartSheet
        open={adding || Boolean(editing)}
        part={editing}
        onClose={() => {
          setAdding(false)
          setEditing(null)
        }}
        missionId={missionId}
        items={ready.items}
      />
    </Disclosure>
  )
}

/** Landing history (counts, never a probability) and the lessons a team can adopt. */
function HistoryRows({ ready, missionId, canWrite }: { ready: ReadyDTO; missionId: string; canWrite: boolean }) {
  const [open, setOpen] = useState(false)
  const history = useLandingHistory(open)
  const lessons = useLessons(missionId, open)
  const adopt = useLifecycleWrite((lessonId: string) => api.adoptLesson(missionId, lessonId))
  return (
    <Disclosure
      title="Landing history and lessons"
      meta={`${ready.lessons_adopted} of ${ready.lessons_available} lessons adopted`}
      onOpen={() => setOpen(true)}
    >
      {history.data ? (
        <>
          <p className="text-body leading-6 text-ink">{landingCountsSentence(history.data)}</p>
          <LandingHistoryTable history={history.data} />
        </>
      ) : history.error ? (
        <p className="text-small text-ink-2">The landing history could not be loaded.</p>
      ) : (
        <p className="text-small text-ink-3">Loading the landing history…</p>
      )}
      <SectionLabel as="h3" className="mt-2">
        Lessons from past landings
      </SectionLabel>
      {lessons.data?.length ? (
        <ul className="flex flex-col divide-y divide-line border-y border-line">
          {lessons.data.map((l) => (
            <li key={l.id} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
              <span className="flex min-w-0 flex-col gap-0.5">
                <span className="text-body text-ink">{l.checklist_item ?? l.text}</span>
                <span className="text-caption text-ink-3">
                  {l.from_mission}, {l.year}
                  {l.source_url && (
                    <>
                      {' · '}
                      <a href={l.source_url} target="_blank" rel="noreferrer">
                        {hostWords(l.source_url)}
                      </a>
                    </>
                  )}
                </span>
              </span>
              {l.adopted ? (
                <span className="flex items-center gap-1.5 text-small text-ink-2">
                  <Icon name="check" size={14} strokeWidth={2.4} />
                  Adopted
                </span>
              ) : (
                canWrite && (
                  <Button size="sm" onClick={() => adopt.mutate(l.id)} disabled={adopt.isPending}>
                    Adopt as a checklist item
                  </Button>
                )
              )}
            </li>
          ))}
        </ul>
      ) : lessons.isPending ? (
        <p className="text-small text-ink-3">Loading the lessons…</p>
      ) : (
        <p className="text-small text-ink-2">No lessons are available.</p>
      )}
    </Disclosure>
  )
}
