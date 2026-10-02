import { useId } from 'react'
import { useMission } from '../lib/store'
import { getSites, siteById } from '../lib/sites'
import { Select } from './Select'

/**
 * The page's title is the picker: the site's name, large, with a chevron. One
 * name on screen instead of a heading and a box repeating it. The heading is
 * kept for screen readers, and the list carries its own label.
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
        <span aria-hidden="true" className="pw-display shrink-0 text-[26px] text-ink-2 sm:text-[30px]">
          {prefix}
        </span>
      )}
      <label htmlFor={id} className="sr-only">
        Site
      </label>
      {/* The name at display size is the button; the list opens under it. */}
      <Select
        id={id}
        look="bare"
        value={siteId}
        onChange={setSite}
        options={[
          ...candidates.map((s) => ({ value: s.id, label: s.name, group: 'Candidate sites' })),
          ...targets.map((s) => ({ value: s.id, label: s.name, group: 'Mission landing spots' })),
        ]}
        chevron={20}
        className="-ml-2 h-12 gap-3 rounded-control pr-3 pl-2 hover:bg-inset aria-expanded:bg-inset"
        labelClassName="pw-display text-[26px] leading-[30px] text-ink sm:text-[30px] sm:leading-[34px]"
      />
    </div>
  )
}
