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
        <span aria-hidden="true" className="pw-display shrink-0 text-[26px] text-ink-2 sm:text-[30px]">
          {prefix}
        </span>
      )}
      <label htmlFor={id} className="sr-only">
        Site
      </label>
      {/* The name drawn at display size, with the real select laid over it: a
          select sized to its content measured the name too narrow and cut it
          off. The focus ring is drawn on the name while the select has it. */}
      <span className="relative -ml-2 inline-flex h-12 min-w-0 max-w-full items-center rounded-control pr-10 pl-2 hover:bg-inset has-[select:focus-visible]:bg-inset has-[select:focus-visible]:outline-2 has-[select:focus-visible]:outline-offset-2 has-[select:focus-visible]:outline-focus has-[select:focus-visible]:outline-solid">
        <span aria-hidden="true" className="pw-display truncate text-[26px] leading-[30px] text-ink sm:text-[30px] sm:leading-[34px]">
          {name}
        </span>
        <select
          id={id}
          value={siteId}
          onChange={(e) => setSite(e.target.value)}
          className="absolute inset-0 h-full w-full cursor-pointer appearance-none rounded-control text-body opacity-0"
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
        <Icon name="chevron" size={20} strokeWidth={2.2} className="pointer-events-none absolute right-3 text-ink-3" />
      </span>
    </div>
  )
}
