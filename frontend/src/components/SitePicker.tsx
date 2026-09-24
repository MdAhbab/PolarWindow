import { useId } from 'react'
import { useMission } from '../lib/store'
import { getSites, siteById } from '../lib/sites'
import { Icon } from './Icon'

/**
 * The page's title is the picker: the site's name, large, with a chevron. One
 * name on screen instead of a heading and a box repeating it. The heading is
 * kept for screen readers, and the select carries its own label.
 */
export function SiteTitle({ prefix = '' }: { prefix?: string }) {
  const id = useId()
  const siteId = useMission((s) => s.siteId)
  const setSite = useMission((s) => s.setSite)
  const sites = getSites()
  const candidates = sites.filter((s) => s.kind === 'candidate')
  const targets = sites.filter((s) => s.kind === 'mission_target')
  const name = siteById(siteId).name
  return (
    <div className="flex min-w-0 items-baseline gap-2">
      <h1 className="sr-only">
        {prefix}
        {name}
      </h1>
      {prefix && (
        <span aria-hidden="true" className="shrink-0 text-heading font-semibold tracking-title text-ink-2">
          {prefix}
        </span>
      )}
      <label htmlFor={id} className="sr-only">
        Site
      </label>
      <span className="relative inline-flex min-w-0 max-w-full items-center">
        <select
          id={id}
          value={siteId}
          onChange={(e) => setSite(e.target.value)}
          className="h-11 max-w-full min-w-0 cursor-pointer appearance-none truncate rounded-control bg-transparent pr-8 text-heading font-semibold tracking-title text-ink [field-sizing:content] hover:bg-inset focus-visible:bg-inset"
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
        <Icon name="chevron" size={18} strokeWidth={2.2} className="pointer-events-none absolute right-2 text-ink-3" />
      </span>
    </div>
  )
}
