import { useState } from 'react'
import { API_BASE, qs } from '../../lib/api/client'
import type { RelayRowDTO } from '../../lib/api/lifecycle'
import { Disclosure } from '../ui'
import { Field, TextInput } from './Forms'

const LINK =
  'inline-flex h-12 items-center rounded-control border border-line-strong px-4 text-body font-semibold text-ink no-underline hover:bg-inset'

/** A data rate as people write numbers ("2,000,000"), in bits per second; null when it is not a number above zero. */
export function parseRate(text: string): number | null {
  const t = text.replace(/[\s,]/g, '')
  if (!t) return null
  const n = Number(t)
  return Number.isFinite(n) && n > 0 ? n : null
}

/**
 * A relay's contacts can be listed in a plan only when its orbit is known well enough for
 * the answer to give what it adds as a range; the service refuses one that is not.
 */
export const listable = (r: RelayRowDTO) => r.adds_h.lo !== null && r.adds_h.hi !== null

/** The address of the plan for the dates the answer covers: ION needs a data rate; `relays` are listed as planned. */
export function planUrl(missionId: string, format: 'ion' | 'csv', start: number, end: number, opts: { rateBps?: number | null; relays?: string[] } = {}): string {
  return `${API_BASE}/missions/${encodeURIComponent(missionId)}/contact/plan${qs({
    format,
    start: new Date(start).toISOString(),
    end: new Date(end).toISOString(),
    rate_bps: format === 'ion' ? opts.rateBps : undefined,
    relay: opts.relays?.length ? opts.relays : undefined,
  })}`
}

const join = (names: string[]) => (names.length > 1 ? `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}` : names[0])

/**
 * The contact plan for the dates on screen, as an ION contact plan (which needs the data rate
 * the team plans for: the lander's is not published) or a spreadsheet. A planned relay's
 * contacts are listed only when asked, and marked planned, since they are for one guess of
 * where the relay will be.
 */
export function PlanDownload({ missionId, start, end, relays }: { missionId: string; start: number; end: number; relays: RelayRowDTO[] }) {
  const [rate, setRate] = useState('')
  const [withRelays, setWithRelays] = useState(false)
  const bps = parseRate(rate)
  const usable = relays.filter(listable)
  const unusable = relays.filter((r) => !listable(r))
  const asked = withRelays ? usable.map((r) => r.id) : undefined
  return (
    <Disclosure title="Download the contact plan" meta="ION, spreadsheet">
      {relays.length > 0 && (
        <div className="flex flex-col gap-1">
          {usable.length > 0 && (
            <label className="flex min-h-12 cursor-pointer items-start gap-3 py-2">
              <input type="checkbox" className="mt-1 h-5 w-5 shrink-0 accent-earth" checked={withRelays} onChange={(e) => setWithRelays(e.target.checked)} />
              <span className="text-body text-ink">
                Include the contacts of the planned relay{usable.length > 1 ? 's' : ''}: {join(usable.map((r) => r.name))}.{' '}
                <span className="text-ink-2">They are for one guess of where each will be, so they are marked planned and are not a schedule.</span>
              </span>
            </label>
          )}
          {unusable.length > 0 && (
            <p className="text-small text-ink-2">
              No contacts can be listed for {join(unusable.map((r) => r.name))}: {unusable.length > 1 ? 'their orbits are' : 'its orbit is'} not known well enough.
            </p>
          )}
        </div>
      )}
      <Field
        label="Data rate for the ION plan, bits per second"
        hint="The lander’s data rate is not published, so give the one you plan for, for example 2,000,000 for 2 megabits per second. The spreadsheet does not need one."
        error={rate.trim() && bps === null ? 'Give a number above zero.' : undefined}
      >
        {(p) => <TextInput {...p} inputMode="decimal" autoComplete="off" value={rate} onChange={(e) => setRate(e.target.value)} />}
      </Field>
      <ul className="flex flex-wrap gap-3">
        <li>
          {bps !== null ? (
            <a className={LINK} href={planUrl(missionId, 'ion', start, end, { rateBps: bps, relays: asked })} download>
              Contact plan for ION (DTN)
            </a>
          ) : (
            <button type="button" disabled className={`${LINK} cursor-not-allowed opacity-60 hover:bg-transparent`}>
              Contact plan for ION (DTN)
            </button>
          )}
        </li>
        <li>
          <a className={LINK} href={planUrl(missionId, 'csv', start, end, { relays: asked })} download>
            Spreadsheet (CSV)
          </a>
        </li>
      </ul>
    </Disclosure>
  )
}
