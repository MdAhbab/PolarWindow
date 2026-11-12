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
    <div data-pw-arrive="pw-site-name" className="flex min-w-0 items-baseline gap-2">
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
        // A relative shift, not a negative margin: a margin shrinks the title's room by 8 px
        // and cut long names ("Connecting Rid…") even on a wide screen.
        className="relative -left-2 h-12 gap-3 rounded-control pr-3 pl-2 hover:bg-inset aria-expanded:bg-inset"
        // The name from the Map's chosen-site card grows into this title (rule 5), and it
        // holds its place between the site's own pages.
        labelClassName="pw-display text-[26px] leading-[30px] text-ink [view-transition-name:pw-site-name] sm:text-[30px] sm:leading-[34px]"
      />
    </div>
  )
}
