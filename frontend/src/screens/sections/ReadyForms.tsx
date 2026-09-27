import { useState } from 'react'
import type React from 'react'
import { api } from '../../lib/api/client'
import type { ItemKind, PartDTO, PartStatus, ReadyItemDTO, ReadyState, RiskCategory, RiskDTO, RiskScaleDTO } from '../../lib/api/lifecycle'
import { useHistory, useLifecycleWrite } from '../../lib/api/lifecycleQueries'
import { Field, FormSheet, HistoryList, Select, TextArea, TextInput, isHttpUrl, todayIso } from '../../components/lifecycle/Forms'
import { CATEGORY_WORDS, KIND_WORDS, PART_WORDS, READY_ORDER, READY_WORDS, TREND_WORDS } from '../../components/lifecycle/Readiness'

/**
 * Move a readiness item to another state (ADR-17): every move needs a date
 * and an evidence link, and a block needs its reason. The server keeps the
 * state machine; an illegal move comes back with the moves that are allowed.
 */
export function ReadyItemSheet({ item, onClose }: { item: ReadyItemDTO | null; onClose: () => void }) {
  const open = Boolean(item)
  const history = useHistory('ready_item', item?.id ?? null)
  const write = useLifecycleWrite((b: Parameters<typeof api.moveReadyItem>[1]) => api.moveReadyItem(item!.id, b))
  const next = item ? nextState(item) : 'in_build'
  const [state, setState] = useState<ReadyState>(next)
  const [date, setDate] = useState(todayIso())
  const [evidence, setEvidence] = useState('')
  const [note, setNote] = useState('')
  const [reason, setReason] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [forItem, setForItem] = useState<string | null>(null)
  if (item && forItem !== item.id) {
    // A new item: start from its next step, with nothing typed.
    setForItem(item.id)
    setState(nextState(item))
    setEvidence(item.evidence_url ?? '')
    setNote('')
    setReason('')
    setErrors({})
    write.reset()
  }

  const save = async () => {
    const e: Record<string, string> = {}
    if (!date) e.date = 'Give the date of the change.'
    if (!isHttpUrl(evidence)) e.evidence = 'Link the evidence: a test report, a delivery note or a review record (a web address).'
    if (state === 'blocked' && !reason.trim()) e.reason = 'Say what is blocking it.'
    setErrors(e)
    if (Object.keys(e).length) return false
    try {
      await write.mutateAsync({
        state,
        date,
        evidence_url: evidence,
        note: note.trim() || null,
        ...(state === 'blocked' ? { blocked_reason: reason.trim() } : {}),
      })
      return true
    } catch {
      return false
    }
  }

  return (
    <FormSheet
      open={open}
      onClose={onClose}
      title={item ? `Change: ${item.name}` : 'Change an item'}
      intro={
        item ? (
          <>
            Now: {item.state_known ? READY_WORDS[item.state] : 'not entered yet'}
            {item.state_known && item.blocked_reason ? `, ${item.blocked_reason}` : ''}. The list offers only the moves allowed from
            here.
          </>
        ) : null
      }
      onSave={save}
      saving={write.isPending}
      error={write.error}
      history={<HistoryList entries={history.data} pending={history.isPending} error={history.error} />}
    >
      <Field label="New state">
        {(p) => (
          <Select
            {...p}
            value={state}
            onChange={(e) => setState(e.target.value as ReadyState)}
            options={movesFrom(item).map((s) => ({ value: s, label: READY_WORDS[s] }))}
          />
        )}
      </Field>
      {state === 'blocked' && (
        <Field label="What is blocking it" error={errors.reason}>
          {(p) => <TextInput {...p} value={reason} onChange={(e) => setReason(e.target.value)} />}
        </Field>
      )}
      <Field label="Date of the change" error={errors.date}>
        {(p) => <TextInput {...p} type="date" value={date} onChange={(e) => setDate(e.target.value)} />}
      </Field>
      <Field label="Evidence link" hint="A test report, delivery note or review record." error={errors.evidence}>
        {(p) => <TextInput {...p} type="url" inputMode="url" placeholder="https://" value={evidence} onChange={(e) => setEvidence(e.target.value)} />}
      </Field>
      <Field label="Note (optional)">
        {(p) => <TextArea {...p} value={note} onChange={(e) => setNote(e.target.value)} />}
      </Field>
    </FormSheet>
  )
}

/** The moves the server allows from here; every other state if it did not say. */
function movesFrom(item: ReadyItemDTO | null): ReadyState[] {
  if (item?.allowed_next?.length) return item.allowed_next
  return [...READY_ORDER, 'blocked' as const].filter((s) => s !== item?.state)
}

/** The form opens on the next step forward, when that is allowed; else the first allowed move. */
function nextState(item: ReadyItemDTO): ReadyState {
  const moves = movesFrom(item)
  const at = item.state_known && item.state !== 'blocked' ? READY_ORDER.indexOf(item.state) : -1
  return moves.find((s) => s !== 'blocked' && READY_ORDER.indexOf(s as never) === at + 1) ?? moves[0] ?? 'in_build'
}

export function AddItemSheet({ open, onClose, missionId }: { open: boolean; onClose: () => void; missionId: string }) {
  const write = useLifecycleWrite((b: Parameters<typeof api.addReadyItem>[1]) => api.addReadyItem(missionId, b))
  const [kind, setKind] = useState<ItemKind>('payload')
  const [name, setName] = useState('')
  const [org, setOrg] = useState('')
  const [err, setErr] = useState<string | undefined>()
  return (
    <FormSheet
      open={open}
      onClose={onClose}
      title="Add a readiness item"
      intro="It starts as “Not started”. Move it on from the list as it happens, with a date and evidence each time."
      saving={write.isPending}
      error={write.error}
      saveLabel="Add it"
      onSave={async () => {
        if (!name.trim()) {
          setErr('Give the item a name.')
          return false
        }
        setErr(undefined)
        try {
          await write.mutateAsync({ kind, name: name.trim(), organisation: org.trim() || null })
          setName('')
          setOrg('')
          return true
        } catch {
          return false
        }
      }}
    >
      <Field label="Kind">
        {(p) => (
          <Select
            {...p}
            value={kind}
            onChange={(e) => setKind(e.target.value as ItemKind)}
            options={(Object.keys(KIND_WORDS) as ItemKind[]).map((k) => ({ value: k, label: KIND_WORDS[k] }))}
          />
        )}
      </Field>
      <Field label="Name" error={err}>
        {(p) => <TextInput {...p} value={name} onChange={(e) => setName(e.target.value)} />}
      </Field>
      <Field label="Organisation (optional)">
        {(p) => <TextInput {...p} value={org} onChange={(e) => setOrg(e.target.value)} />}
      </Field>
    </FormSheet>
  )
}

const CATS: RiskCategory[] = ['safety', 'technical', 'cost', 'schedule']

/**
 * A risk: its cause and consequence in words, then likelihood and
 * consequence for each category that applies, on the scale in use. They are
 * stored side by side and never combined.
 */
export function RiskSheet({
  open,
  risk,
  onClose,
  missionId,
  scale,
}: {
  open: boolean
  risk: RiskDTO | null
  onClose: () => void
  missionId: string
  scale: RiskScaleDTO | undefined
}) {
  const history = useHistory('risk', risk?.id ?? null)
  const write = useLifecycleWrite((b: Omit<RiskDTO, 'id'>) => (risk ? api.changeRisk(risk.id, b) : api.addRisk(missionId, b)))
  const blank = { title: '', cause: '', consequence_text: '', owner: '', mitigation: '', trend: 'steady' as RiskDTO['trend'] }
  const [f, setF] = useState(blank)
  const [ratings, setRatings] = useState<Record<RiskCategory, { l: number; c: number } | null>>({
    safety: null,
    technical: null,
    cost: null,
    schedule: null,
  })
  const [err, setErr] = useState<string | undefined>()
  const [forKey, setForKey] = useState<string | null>(null)
  const key = open ? (risk?.id ?? 'new') : null
  if (key !== forKey) {
    setForKey(key)
    setF(
      risk
        ? { title: risk.title, cause: risk.cause, consequence_text: risk.consequence_text, owner: risk.owner ?? '', mitigation: risk.mitigation ?? '', trend: risk.trend }
        : blank,
    )
    const r: Record<RiskCategory, { l: number; c: number } | null> = { safety: null, technical: null, cost: null, schedule: null }
    for (const x of risk?.ratings ?? []) r[x.category] = { l: x.likelihood, c: x.consequence }
    setRatings(r)
    setErr(undefined)
    write.reset()
  }
  const levels = (words: { level: number; words: string }[] | undefined) =>
    [{ value: '', label: 'Does not apply' }, ...[1, 2, 3, 4, 5].map((n) => ({ value: String(n), label: `${n}${words?.find((w) => w.level === n) ? `: ${words.find((w) => w.level === n)!.words}` : ''}` }))]

  return (
    <FormSheet
      open={open}
      onClose={onClose}
      title={risk ? `Change: ${risk.title}` : 'Add a risk'}
      intro={`Rated on ${scale?.name ?? 'the programme’s scale'}. Likelihood and consequence are kept apart for each category and never combined into a score.`}
      saving={write.isPending}
      error={write.error}
      onSave={async () => {
        const rated = CATS.filter((c) => ratings[c])
        if (!f.title.trim() || !rated.length) {
          setErr(!f.title.trim() ? 'Give the risk a title.' : 'Rate at least one category.')
          return false
        }
        setErr(undefined)
        try {
          await write.mutateAsync({
            title: f.title.trim(),
            cause: f.cause.trim(),
            consequence_text: f.consequence_text.trim(),
            scale_id: scale?.id ?? risk?.scale_id ?? 'default',
            ratings: rated.map((c) => ({ category: c, likelihood: ratings[c]!.l, consequence: ratings[c]!.c })),
            trend: f.trend,
            owner: f.owner.trim() || null,
            mitigation: f.mitigation.trim() || null,
            links: risk?.links ?? { readiness_items: [], parts: [], lessons: [] },
          })
          return true
        } catch {
          return false
        }
      }}
      history={risk ? <HistoryList entries={history.data} pending={history.isPending} error={history.error} /> : undefined}
    >
      <Field label="Title" error={err}>
        {(p) => <TextInput {...p} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} />}
      </Field>
      <Field label="Cause" hint="What could happen.">
        {(p) => <TextInput {...p} value={f.cause} onChange={(e) => setF({ ...f, cause: e.target.value })} />}
      </Field>
      <Field label="Consequence" hint="What it would do to the mission.">
        {(p) => <TextInput {...p} value={f.consequence_text} onChange={(e) => setF({ ...f, consequence_text: e.target.value })} />}
      </Field>
      {CATS.map((c) => {
        const r = ratings[c]
        const cons = scale?.consequence.find((x) => x.category === c)?.levels
        return (
          <fieldset key={c} className="flex flex-col gap-3 border-t border-line pt-3">
            <legend className="text-small font-semibold text-ink">{CATEGORY_WORDS[c]}</legend>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Field label="Likelihood">
                {(p) => (
                  <Select
                    {...p}
                    value={r ? String(r.l) : ''}
                    onChange={(e) =>
                      setRatings({ ...ratings, [c]: e.target.value ? { l: Number(e.target.value), c: r?.c ?? 1 } : null })
                    }
                    options={levels(scale?.likelihood)}
                  />
                )}
              </Field>
              <Field label="Consequence">
                {(p) => (
                  <Select
                    {...p}
                    value={r ? String(r.c) : ''}
                    onChange={(e) =>
                      setRatings({ ...ratings, [c]: e.target.value ? { c: Number(e.target.value), l: r?.l ?? 1 } : null })
                    }
                    options={levels(cons)}
                  />
                )}
              </Field>
            </div>
          </fieldset>
        )
      })}
      <Field label="Trend">
        {(p) => (
          <Select
            {...p}
            value={f.trend}
            onChange={(e) => setF({ ...f, trend: e.target.value as RiskDTO['trend'] })}
            options={(Object.keys(TREND_WORDS) as RiskDTO['trend'][]).map((t) => ({ value: t, label: TREND_WORDS[t].words }))}
          />
        )}
      </Field>
      <Field label="Owner (optional)">
        {(p) => <TextInput {...p} value={f.owner} onChange={(e) => setF({ ...f, owner: e.target.value })} />}
      </Field>
      <Field label="Mitigation (optional)">
        {(p) => <TextArea {...p} value={f.mitigation} onChange={(e) => setF({ ...f, mitigation: e.target.value })} />}
      </Field>
    </FormSheet>
  )
}

/** Add a part, or change one's status (a part lost, damaged, back in test). */
export function PartSheet({
  open,
  part,
  onClose,
  missionId,
  items,
}: {
  open: boolean
  part: PartDTO | null
  onClose: () => void
  missionId: string
  items: ReadyItemDTO[]
}) {
  const history = useHistory('part', part?.id ?? null)
  type Body = Omit<PartDTO, 'id' | 'changed_at' | 'changed_by'>
  const write = useLifecycleWrite((b: Body) => (part ? api.changePart(part.id, b) : api.addPart(missionId, b)))
  const blank: Body = { name: '', part_number: null, serial: null, parent_item_id: items[0]?.id ?? null, status: 'installed', location: null }
  const [f, setF] = useState<Body>(blank)
  const [err, setErr] = useState<string | undefined>()
  const [forKey, setForKey] = useState<string | null>(null)
  const key = open ? (part?.id ?? 'new') : null
  if (key !== forKey) {
    setForKey(key)
    setF(part ? { name: part.name, part_number: part.part_number, serial: part.serial, parent_item_id: part.parent_item_id, status: part.status, location: part.location } : blank)
    setErr(undefined)
    write.reset()
  }
  const text = (k: 'part_number' | 'serial' | 'location') => ({
    value: f[k] ?? '',
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value || null }),
  })
  return (
    <FormSheet
      open={open}
      onClose={onClose}
      title={part ? `Change: ${part.name}` : 'Add a part'}
      saving={write.isPending}
      error={write.error}
      onSave={async () => {
        if (!f.name.trim()) {
          setErr('Give the part a name.')
          return false
        }
        setErr(undefined)
        try {
          await write.mutateAsync({ ...f, name: f.name.trim() })
          return true
        } catch {
          return false
        }
      }}
      history={part ? <HistoryList entries={history.data} pending={history.isPending} error={history.error} /> : undefined}
    >
      <Field label="Name" error={err}>
        {(p) => <TextInput {...p} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />}
      </Field>
      <Field label="Status">
        {(p) => (
          <Select
            {...p}
            value={f.status}
            onChange={(e) => setF({ ...f, status: e.target.value as PartStatus })}
            options={(Object.keys(PART_WORDS) as PartStatus[]).map((s) => ({ value: s, label: PART_WORDS[s].words }))}
          />
        )}
      </Field>
      <Field label="Part of">
        {(p) => (
          <Select
            {...p}
            value={f.parent_item_id ?? ''}
            onChange={(e) => setF({ ...f, parent_item_id: e.target.value || null })}
            options={[{ value: '', label: 'Not attached' }, ...items.map((i) => ({ value: i.id, label: i.name }))]}
          />
        )}
      </Field>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Part number (optional)">{(p) => <TextInput {...p} {...text('part_number')} />}</Field>
        <Field label="Serial (optional)">{(p) => <TextInput {...p} {...text('serial')} />}</Field>
      </div>
      <Field label="Where it is (optional)">{(p) => <TextInput {...p} {...text('location')} />}</Field>
    </FormSheet>
  )
}
