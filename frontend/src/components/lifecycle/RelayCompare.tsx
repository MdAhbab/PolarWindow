import { useState } from 'react'
import { ApiError } from '../../lib/api/client'
import type { RelayChoiceDTO } from '../../lib/api/lifecycle'
import { useRelayChoices } from '../../lib/api/lifecycleQueries'
import { Button, Disclosure } from '../ui'
import { RELAY_STATUS } from './ContactChart'

/** The most relays that can be added at a time (the service's limit; the words below say "three"). */
export const MAX_COMPARED = 3

/** The relays the catalogue offers that are not already counted for this mission. */
export function relaysToAdd(all: RelayChoiceDTO[], own: string[]): RelayChoiceDTO[] {
  return all.filter((r) => !own.includes(r.id))
}

/** The same relays in the same order, whichever way they were picked. */
export const sameRelays = (a: string[], b: string[]) => a.length === b.length && [...a].sort().join('\n') === [...b].sort().join('\n')

/**
 * What a relay that is planned, but is not part of this mission's plan, would add here
 * (design-lifecycle.md §4): tick the relays and ask for the numbers again. The answer then
 * counts them as a range "if it flies as planned", marks each as added to compare, and the
 * contact plan can list their contacts. The choice is `applied` (what the answer on screen
 * was asked with); ticking changes only the choice, so nothing is worked out until asked.
 */
export function RelayCompare({ own, applied, onApply }: { own: string[]; applied: string[]; onApply: (ids: string[]) => void }) {
  const list = useRelayChoices(true)
  const [draft, setDraft] = useState<string[]>(applied)
  const choices = relaysToAdd(list.data?.relays ?? [], own)
  // Nothing to offer: every relay is already counted, and none was added.
  if (list.data && !choices.length && !applied.length) return null
  const name = (id: string) => list.data?.relays.find((r) => r.id === id)?.name ?? id
  const changed = !sameRelays(draft, applied)
  const toggle = (id: string) => setDraft((d) => (d.includes(id) ? d.filter((x) => x !== id) : d.length < MAX_COMPARED ? [...d, id] : d))
  return (
    <Disclosure title="Compare a relay" meta={applied.length ? applied.map(name).join(', ') : 'none added'} defaultOpen={applied.length > 0}>
      <p className="text-body text-ink-2">
        Add a relay that is planned but is not part of this mission’s plan, to see what it would add for this lander. Its orbit is published only in part, so what it adds is a range,
        and only if it flies as planned. Up to three at a time.
      </p>
      {list.isPending ? (
        <p className="text-small text-ink-3">Loading the relays…</p>
      ) : list.isError ? (
        <p className="text-body text-ink-2">The list of relays could not be loaded: {list.error instanceof ApiError ? list.error.detail : 'the service did not answer.'}</p>
      ) : (
        <>
          <fieldset className="flex min-w-0 flex-col divide-y divide-line border-y border-line">
            <legend className="sr-only">Relays to add to the numbers</legend>
            {choices.map((r) => {
              const on = draft.includes(r.id)
              const state = RELAY_STATUS[r.status]
              return (
                <label key={r.id} className="flex min-h-12 cursor-pointer items-start gap-3 py-3">
                  <input
                    type="checkbox"
                    className="mt-1 h-5 w-5 shrink-0 accent-earth"
                    checked={on}
                    disabled={!on && draft.length >= MAX_COMPARED}
                    onChange={() => toggle(r.id)}
                  />
                  <span className="flex min-w-0 flex-col gap-0.5">
                    <span className="text-body font-semibold text-ink">
                      {r.name}
                      {r.operator && <span className="font-normal text-ink-3"> · {r.operator}</span>}
                    </span>
                    <span className="text-small text-ink">
                      <span aria-hidden="true">{state.glyph} </span>
                      {state.words}.{r.launch_note ? ` ${r.launch_note}` : ''}
                    </span>
                    {!r.orbit_known && (
                      <span className="text-small text-ink-2">Its orbit is not published, so no time through it can be worked out. It is added all the same, and the answer says so.</span>
                    )}
                  </span>
                </label>
              )
            })}
          </fieldset>
          <div>
            <Button variant="primary" disabled={!changed} onClick={() => onApply(draft)}>
              {draft.length || !changed ? 'Work out the numbers with these' : 'Work out the numbers without them'}
            </Button>
          </div>
        </>
      )}
    </Disclosure>
  )
}
