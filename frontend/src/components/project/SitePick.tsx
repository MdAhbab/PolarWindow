import { useId, useMemo, useState } from 'react'
import type { ProjectOptionsDTO } from '../../lib/api/experience.types'
import { PolarMap, type MissionPin } from '../PolarMap'
import { SearchField, Segmented } from '../ui'
import { Icon } from '../Icon'
import { FieldShell, TextField, TWO_COLUMNS } from './fields'
import type { Errors, ProjectFormState, Provenance } from './formModel'

const KIND_WORDS = { candidate: 'Candidate site', mission_target: 'Mission target' } as const

/**
 * Where it lands: a surveyed site (a searchable list and the polar map; its
 * skyline is already built) or a name and coordinates (built after saving).
 */
export function SitePick({
  form,
  options,
  errors,
  provenance,
  onChange,
}: {
  form: ProjectFormState
  options: ProjectOptionsDTO | undefined
  errors: Errors
  provenance: Provenance
  onChange: (patch: Partial<ProjectFormState>) => void
}) {
  const [query, setQuery] = useState('')
  const searchId = useId()
  const listLabel = useId()
  const sites = options?.sites ?? []
  const q = query.trim().toLowerCase()
  const shown = useMemo(
    () => (q ? sites.filter((s) => `${s.label} ${s.hint ?? ''}`.toLowerCase().includes(q)) : sites),
    [sites, q],
  )

  const lat = Number(form.lat)
  const lon = Number(form.lon)
  const typedOk = form.lat.trim() !== '' && form.lon.trim() !== '' && Number.isFinite(lat) && Number.isFinite(lon) && lat >= -90 && lat <= 90
  const pins: MissionPin[] = useMemo(() => {
    const out: MissionPin[] = sites.map((s) => ({
      key: s.value,
      latDeg: s.lat_deg,
      lonDeg: s.lon_deg,
      dashed: s.kind === 'candidate',
      label: `${s.label}, ${KIND_WORDS[s.kind].toLowerCase()}. Choose it`,
      highlighted: form.targetMode === 'site' && form.siteId === s.value,
      pressed: form.targetMode === 'site' && form.siteId === s.value,
    }))
    if (form.targetMode === 'coords' && typedOk) {
      out.push({
        key: '__typed',
        latDeg: lat,
        lonDeg: lon,
        dashed: true,
        label: 'The coordinates you typed',
        highlighted: true,
      })
    }
    return out
  }, [sites, form.targetMode, form.siteId, form.targetName, typedOk, lat, lon])

  const src = provenance.target
  return (
    <div className="flex flex-col gap-5">
      <Segmented
        label="How to give the landing spot"
        value={form.targetMode}
        onChange={(v) => onChange({ targetMode: v })}
        options={[
          { value: 'site', label: 'Choose a surveyed site' },
          { value: 'coords', label: 'Type coordinates' },
        ]}
      />
      {form.targetMode === 'site' ? (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,320px)]">
          <div className="flex min-w-0 flex-col gap-3">
            <SearchField id={searchId} value={query} onChange={setQuery} placeholder="Search by name or place" />
            <FieldShell label="Surveyed sites" source={src} error={errors.siteId} hint="Their skyline is already built, so the steps that need it answer at once.">
              {() => (
                <div
                  role="radiogroup"
                  aria-labelledby={listLabel}
                  className="max-h-72 overflow-y-auto rounded-control border border-field bg-panel"
                >
                  <span id={listLabel} className="sr-only">
                    Surveyed sites
                  </span>
                  {options === undefined ? (
                    <p className="p-4 text-small text-ink-2">Loading the sites…</p>
                  ) : shown.length === 0 ? (
                    <p className="p-4 text-small text-ink-2">No surveyed site matches “{query}”.</p>
                  ) : (
                    shown.map((s) => {
                      const on = form.siteId === s.value
                      return (
                        <label
                          key={s.value}
                          className={`flex min-h-12 cursor-pointer items-center gap-3 border-b border-line px-3.5 py-2 last:border-b-0 has-[:focus-visible]:outline-2 has-[:focus-visible]:-outline-offset-2 has-[:focus-visible]:outline-focus ${
                            on ? 'bg-inset' : 'hover:bg-inset'
                          }`}
                        >
                          <input
                            type="radio"
                            name="site"
                            className="sr-only"
                            checked={on}
                            onChange={() => onChange({ siteId: s.value })}
                          />
                          <span
                            aria-hidden="true"
                            className={`flex size-5 shrink-0 items-center justify-center rounded-pill border ${on ? 'border-ink bg-ink text-canvas' : 'border-line-strong'}`}
                          >
                            {on && <Icon name="check" size={12} strokeWidth={3} />}
                          </span>
                          <span className="flex min-w-0 flex-col">
                            <span className="text-body font-semibold text-ink">{s.label}</span>
                            <span className="text-caption text-ink-3">
                              {KIND_WORDS[s.kind]}
                              {s.hint ? ` · ${s.hint}` : ''}
                            </span>
                          </span>
                        </label>
                      )
                    })
                  )}
                </div>
              )}
            </FieldShell>
            {form.siteId === '' && (
              <p className="text-caption leading-caption text-ink-3">
                No site chosen: the landing spot stays unknown, and the steps that need one will offer a scenario.
              </p>
            )}
          </div>
          <div className="flex justify-center">
            <PolarMap
              sun={null}
              selectedSiteId=""
              size={320}
              sites={[]}
              siteMarks="dots"
              missionPins={pins}
              onMissionPin={(keys) => {
                const k = keys.find((x) => x !== '__typed')
                if (k) onChange({ siteId: k })
              }}
            />
          </div>
        </div>
      ) : (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,320px)]">
          <div className="flex min-w-0 flex-col gap-5">
            <div className={TWO_COLUMNS}>
              <TextField
                label="Name of the spot"
                value={form.targetName}
                onChange={(v) => onChange({ targetName: v })}
                error={errors.targetName}
                source={src}
                hint="Optional. A crater, a ridge, or your own label."
              />
              <span className="hidden sm:block" />
              <TextField
                label="Latitude, degrees"
                value={form.lat}
                onChange={(v) => onChange({ lat: v })}
                error={errors.lat}
                inputMode="decimal"
                placeholder="-89.5"
                hint="South is negative."
              />
              <TextField
                label="Longitude, degrees east"
                value={form.lon}
                onChange={(v) => onChange({ lon: v })}
                error={errors.lon}
                inputMode="decimal"
                placeholder="222.4"
                hint="0 to 360. A value from −180 to 180 is turned into this range."
              />
            </div>
            <p className="max-w-xl text-small leading-5 text-ink-2">
              A new coordinate has no skyline yet. After you save, it is built in the background, and Surface and
              Contact say so until it is done.
            </p>
          </div>
          <div className="flex justify-center">
            <PolarMap
              sun={null}
              selectedSiteId=""
              size={320}
              sites={[]}
              siteMarks="dots"
              missionPins={pins.filter((p) => p.key === '__typed')}
            />
          </div>
        </div>
      )}
    </div>
  )
}
