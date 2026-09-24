import { useId } from 'react'
import { useMission } from '../lib/store'
import { getSites } from '../lib/sites'

/**
 * The site this page is about, and a way to change it without going back to
 * the map. A native select: every keyboard, screen reader and phone already
 * knows how to use one. Candidate sites first, then missions' landing spots.
 */
export function SitePicker({ className = '' }: { className?: string }) {
  const id = useId()
  const siteId = useMission((s) => s.siteId)
  const setSite = useMission((s) => s.setSite)
  const sites = getSites()
  const candidates = sites.filter((s) => s.kind === 'candidate')
  const targets = sites.filter((s) => s.kind === 'mission_target')
  return (
    <div className={`flex w-full min-w-0 flex-col gap-1 sm:w-auto ${className}`}>
      <label htmlFor={id} className="text-small font-medium text-ink-3">
        Site
      </label>
      <select
        id={id}
        value={siteId}
        onChange={(e) => setSite(e.target.value)}
        className="h-12 w-full max-w-full rounded-control border border-line-strong bg-canvas px-3 text-control text-ink hover:border-ink-3"
      >
        <optgroup label="Candidate sites">
          {candidates.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </optgroup>
        {targets.length > 0 && (
          <optgroup label="Mission landing spots">
            {targets.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </optgroup>
        )}
      </select>
    </div>
  )
}
