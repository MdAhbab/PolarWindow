import { useId, useState } from 'react'
import { useMissions, useSites } from '../../lib/api/queries'
import { Icon } from '../Icon'
import { candidateSiteCount, catalogueMissionCount } from './countFilter'

/** The glossary's hint for CLPS (docs/design-glossary.md). */
const CLPS_HINT = 'NASA buys deliveries to the Moon from private companies under Commercial Lunar Payload Services.'

/**
 * The two counts, from the API's own lists (the catalogue's missions and the
 * candidate sites; projects people have added are not counted, see countFilter.ts);
 * nothing when they don't load. The first label's meaning opens on a press, or
 * while it has keyboard focus.
 */
export function Counts() {
  const missions = useMissions({})
  const sites = useSites({ kind: 'all' })
  const hintId = useId()
  const [open, setOpen] = useState(false)
  const [focused, setFocused] = useState(false)
  const m = missions.data ? catalogueMissionCount(missions.data.items) : undefined
  const c = sites.data ? candidateSiteCount(sites.data.items) : undefined
  if (m === undefined || !c) return null
  return (
    <div className="flex flex-col gap-1">
      <dl className="flex flex-wrap gap-x-10 gap-y-3">
        <div className="flex flex-col-reverse">
          <dt className="text-small font-medium text-ink-2">
            <button
              type="button"
              aria-expanded={open}
              aria-controls={hintId}
              onClick={() => setOpen((o) => !o)}
              onFocus={(e) => setFocused(e.currentTarget.matches(':focus-visible'))}
              onBlur={() => setFocused(false)}
              className="-my-2 inline-flex min-h-11 cursor-pointer items-center gap-1.5 py-2 text-left hover:text-ink"
            >
              CLPS missions
              <Icon name="info" size={14} strokeWidth={2} className="shrink-0 opacity-70" />
              <span className="sr-only">{open ? ', hide what this means' : ', what this means'}</span>
            </button>
          </dt>
          <dd className="pw-figure text-[34px] leading-[38px]">{m}</dd>
        </div>
        <div className="flex flex-col-reverse">
          <dt className="-my-2 flex min-h-11 items-center py-2 text-small font-medium text-ink-2">candidate landing sites</dt>
          <dd className="pw-figure text-[34px] leading-[38px]">{c}</dd>
        </div>
      </dl>
      <p id={hintId} hidden={!(open || focused)} className="max-w-md text-small leading-5 text-ink-2">
        {CLPS_HINT}
      </p>
    </div>
  )
}
