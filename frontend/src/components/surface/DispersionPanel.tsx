import { useId, useState } from 'react'
import { useDispersion } from '../../lib/api/surface'
import { LIVE_SERVICE } from '../../lib/api/home'
import type { DispersionRequestDTO, DispersionResponseDTO, IlluminationLayerDTO, ShareBlockDTO } from '../../lib/api/surface.types'
import { TextInput } from '../lifecycle/Forms'
import { ProblemPanel } from '../States'
import { Button, Disclosure } from '../ui'
import { DispersionMap } from './DispersionMap'
import { num, pct, quantityWords, shareWords } from './helpers'
import { ProvTag, QuantityCell, SavedCopyNote } from './parts'

type Key = 'semi_major_m' | 'semi_minor_m' | 'azimuth_deg' | 'footprint_diameter_m' | 'cg_height_m' | 'slope_limit_deg'

const FIELDS: { group: string; items: { key: Key; label: string; unit: string }[] }[] = [
  {
    group: 'Landing ellipse (3 sigma)',
    items: [
      { key: 'semi_major_m', label: 'Half-length (semi-major)', unit: 'm' },
      { key: 'semi_minor_m', label: 'Half-width (semi-minor)', unit: 'm' },
      { key: 'azimuth_deg', label: 'Long axis bearing from north', unit: '°' },
    ],
  },
  {
    group: 'Lander',
    items: [
      { key: 'footprint_diameter_m', label: 'Footpad circle diameter', unit: 'm' },
      { key: 'cg_height_m', label: 'Centre of gravity height', unit: 'm' },
      { key: 'slope_limit_deg', label: 'Slope limit', unit: '°' },
    ],
  },
]

/** The six typed figures as a request, or the reason it cannot be sent yet. Nothing is filled in silently. */
export function dispersionBody(v: Partial<Record<Key, string>>): { body: DispersionRequestDTO | null; missing: Key[]; bad: Key[] } {
  const missing: Key[] = []
  const bad: Key[] = []
  const n: Partial<Record<Key, number>> = {}
  for (const f of FIELDS.flatMap((g) => g.items)) {
    const raw = (v[f.key] ?? '').trim()
    if (raw === '') missing.push(f.key)
    else if (!Number.isFinite(Number(raw))) bad.push(f.key)
    else n[f.key] = Number(raw)
  }
  if (missing.length || bad.length) return { body: null, missing, bad }
  return {
    body: {
      ellipse: { semi_major_m: n.semi_major_m!, semi_minor_m: n.semi_minor_m!, azimuth_deg: n.azimuth_deg! },
      lander: { footprint_diameter_m: n.footprint_diameter_m!, cg_height_m: n.cg_height_m!, slope_limit_deg: n.slope_limit_deg! },
    },
    missing,
    bad,
  }
}

/**
 * Where a lander might come down inside its ellipse, and how steep the ground
 * is there (ADR-22). All six figures are the person's own: empty until typed.
 */
export function DispersionPanel({ siteId, siteName }: { siteId: string; siteName: string }) {
  const [values, setValues] = useState<Partial<Record<Key, string>>>({})
  const [asked, setAsked] = useState<DispersionRequestDTO | null>(null)
  const q = useDispersion(siteId, asked)
  const id = useId()
  const { body, missing, bad } = dispersionBody(values)
  const stale = asked !== null && JSON.stringify(asked) !== JSON.stringify(body)

  if (!LIVE_SERVICE) return <SavedCopyNote what="the landing ellipse" />

  return (
    <div className="flex min-w-0 flex-col gap-5">
      <p className="text-small leading-5 text-ink-2">
        Type all six figures for your lander and its landing ellipse. None is filled in for you; each is used as entered, with no margin.
      </p>
      <div className="grid gap-5 md:grid-cols-2">
        {FIELDS.map((g) => (
          <fieldset key={g.group} className="flex min-w-0 flex-col gap-3 border-t border-line pt-3">
            <legend className="pw-eyebrow float-left mb-1 w-full">{g.group}</legend>
            <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3 md:grid-cols-2 lg:grid-cols-3">
              {g.items.map((f) => {
                const fid = `${id}-${f.key}`
                const typed = (values[f.key] ?? '').trim() !== ''
                const isBad = bad.includes(f.key)
                return (
                  <div key={f.key} className="flex min-w-0 flex-col gap-1">
                    <label htmlFor={fid} className="flex min-h-9 items-end justify-between gap-2 text-caption leading-4 text-ink-2">
                      <span>{f.label}</span>
                      <span className="shrink-0 font-mono text-ink-3">{f.unit}</span>
                    </label>
                    <TextInput
                      id={fid}
                      inputMode="decimal"
                      autoComplete="off"
                      value={values[f.key] ?? ''}
                      placeholder="needed"
                      aria-invalid={isBad || undefined}
                      aria-describedby={`${fid}-p`}
                      onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
                      className="h-11 px-3 font-mono tabular-nums"
                    />
                    <span id={`${fid}-p`} className="flex min-h-4 items-center gap-2 text-caption leading-4">
                      {typed && !isBad && <ProvTag p="entered" />}
                      {isBad && <span className="font-semibold text-alert">Type a number</span>}
                    </span>
                  </div>
                )
              })}
            </div>
          </fieldset>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Button variant="primary" arrow disabled={!body || q.isFetching} onClick={() => setAsked(body)}>
          {q.isFetching ? 'Working it out…' : 'Work it out'}
        </Button>
        <p className="text-caption leading-caption text-ink-3">
          {missing.length > 0
            ? `${missing.length} of 6 figures still to type.`
            : bad.length > 0
              ? 'Correct the figures marked first.'
              : `Around ${siteName}. Slope does not depend on the dates.`}
        </p>
      </div>
      {q.isError && <ProblemPanel error={q.error} fallbackTitle="The landing ellipse could not be worked out" />}
      {q.data && <DispersionResult data={q.data} stale={stale} />}
    </div>
  )
}

function ShareRow({ title, block, limitWords }: { title: string; block: ShareBlockDTO; limitWords: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-1 border-t border-line pt-3">
      <dt className="text-caption leading-caption text-ink-2">
        {title} <span className="text-ink-3">({limitWords}, slope over {block.baseline_m} m)</span>
      </dt>
      <dd className="font-mono text-body text-ink tabular-nums">{shareWords(block.share)}</dd>
      <dd className="text-caption leading-caption text-ink-2">
        If slopes are one sigma higher: <span className="font-mono tabular-nums">{shareWords(block.if_slopes_one_sigma_higher)}</span>
      </dd>
      <dd>
        <ProvTag p="computed" />
      </dd>
    </div>
  )
}

function IllumRow({ layer }: { layer: IlluminationLayerDTO }) {
  const p50 = layer.p50.value
  const lo = layer.p10.value
  const hi = layer.p90.value
  const asPct = layer.unit.includes('fraction') || layer.p50.unit === '1'
  const f = (v: number | null) => (v === null ? '—' : asPct ? `${pct(v)} %` : num(v))
  return (
    <div className="flex min-w-0 flex-col gap-1 border-t border-line pt-3">
      <dt className="text-caption leading-caption text-ink-2 first-letter:uppercase">{layer.name}</dt>
      <dd className="flex flex-wrap items-baseline gap-x-2">
        <span className="font-mono text-figure-sm tracking-figure-sm text-ink tabular-nums">{f(p50)}</span>
        <span className="text-small text-ink-2">{asPct ? 'of the time, median point' : layer.unit}</span>
      </dd>
      <dd className="font-mono text-caption leading-caption text-ink-2 tabular-nums">
        {f(lo)} to {f(hi)} across the ellipse (10th to 90th percentile)
      </dd>
      {layer.p50.no_margin_reason && <dd className="text-caption leading-caption text-ink-3">{layer.p50.no_margin_reason}.</dd>}
      <dd>
        <ProvTag p={layer.p50.provenance} />
      </dd>
    </div>
  )
}

/** What came back: the map, the slope spread and its baseline, the shares, the long-term light and what is not modelled. */
export function DispersionResult({ data, stale = false }: { data: DispersionResponseDTO; stale?: boolean }) {
  const sl = data.slope
  const ss = data.slope_source
  const il = data.illumination
  const sh = data.shares
  const tip = quantityWords(data.tip_over.angle, 1)
  return (
    <section aria-label="Landing ellipse, worked out" className={`flex min-w-0 flex-col gap-6 ${stale ? 'opacity-60' : ''}`}>
      {stale && (
        <p role="status" className="text-small leading-5 font-semibold text-ink">
          The figures have changed since this was worked out. Press Work it out again to update it.
        </p>
      )}
      <div className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <DispersionMap h={data.heatmap} limitDeg={sh.above_slope_limit.limit_deg} />
        <div className="flex min-w-0 flex-col gap-4">
          <div className="flex flex-col gap-1">
            <h3 className="pw-eyebrow">Slope across the ellipse</h3>
            <p className="text-small leading-5 text-ink-2">
              <strong className="font-semibold text-ink">Baseline: over {sl.baseline_m} m.</strong> {ss.baseline_note ?? ''} {sl.n_with_slope} of{' '}
              {sl.n_points} points have a slope.
            </p>
          </div>
          <dl className="grid grid-cols-1 gap-x-4 gap-y-3 min-[420px]:grid-cols-3">
            <QuantityCell label="10th percentile" q={sl.p10} digits={1} />
            <QuantityCell label="Median" q={sl.p50} digits={1} />
            <QuantityCell label="90th percentile" q={sl.p90} digits={1} />
          </dl>
          {sl.margin_note && <p className="text-caption leading-caption text-ink-3">{sl.margin_note}</p>}
          <dl className="flex flex-col gap-3">
            <ShareRow title="Over the slope limit" block={sh.above_slope_limit} limitWords={`${num(sh.above_slope_limit.limit_deg, 1)}°, entered`} />
            <ShareRow
              title="Over the tip-over angle"
              block={sh.above_tip_over}
              limitWords={`${tip.value}°, computed from the footpad circle and centre of gravity`}
            />
          </dl>
          <p className="text-caption leading-caption text-ink-3">
            {sh.basis} Tip-over angle {tip.value}°: {tip.margin}
            {data.tip_over.formula ? ` (${data.tip_over.formula})` : ''}.
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-2 border-t border-line pt-3">
        <h3 className="pw-eyebrow">Terrain the slope came from</h3>
        <p className="text-small leading-5 text-ink-2">
          {ss.fell_back && <strong className="font-semibold text-ink">Fallback: </strong>}
          {ss.label}
          {ss.fell_back && ss.fallback_reason ? `, because ${ss.fallback_reason}` : ''}.{' '}
          {ss.method ? `${ss.method}, ` : ''}
          {typeof ss.spacing_m === 'number' ? `posts every ${num(ss.spacing_m, 0)} m` : ''}
          {typeof ss.vertical_error_m === 'number' ? `, vertical error ${num(ss.vertical_error_m, 2)} m (${ss.vertical_error_note ?? 'stated by the product'})` : ''}.{' '}
          {ss.source?.url && (
            <a href={ss.source.url} target="_blank" rel="noreferrer" className="text-earth underline underline-offset-2">
              {ss.source.citation ?? ss.source.name}
            </a>
          )}
        </p>
      </div>

      <div className="flex flex-col gap-2 border-t border-line pt-3">
        <h3 className="pw-eyebrow">Sunlight, Earth and shadow: a long-term average</h3>
        <p className="text-small leading-5 text-ink-2">
          {il.basis}
          {il.epoch ? ` ${il.epoch}.` : ''}{' '}
          {il.source?.url && (
            <a href={il.source.url} target="_blank" rel="noreferrer" className="text-earth underline underline-offset-2">
              {il.source.citation ?? il.source.name}
            </a>
          )}
        </p>
        {il.available ? (
          <dl className="grid grid-cols-1 gap-x-5 gap-y-3 min-[420px]:grid-cols-2 lg:grid-cols-3">
            {il.sun && <IllumRow layer={il.sun} />}
            {il.earth && <IllumRow layer={il.earth} />}
            {il.permanent_shadow && (
              <div className="flex min-w-0 flex-col gap-1 border-t border-line pt-3">
                <dt className="text-caption leading-caption text-ink-2">Points in permanent shadow</dt>
                <dd className="font-mono text-body text-ink tabular-nums">{shareWords(il.permanent_shadow.share)}</dd>
                <dd>
                  <ProvTag p="computed" />
                  <span className="ml-2 text-caption text-ink-3">from the published shadow map</span>
                </dd>
              </div>
            )}
          </dl>
        ) : (
          <p className="text-small leading-5 text-ink-2">Not available here{il.reason ? `: ${il.reason}` : ''}.</p>
        )}
      </div>

      <div className="flex flex-col gap-2">
        <Disclosure title="What this does not model" meta={`${data.not_modelled.length} things`}>
          <ul className="flex list-disc flex-col gap-1.5 pl-5 text-small leading-5 text-ink-2">
            {data.not_modelled.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </Disclosure>
        <Disclosure title="Sources" meta={`${data.sources.length}`}>
          <ul className="flex flex-col gap-2 text-small leading-5 text-ink-2">
            {data.sources.map((s) => (
              <li key={s.name}>
                {s.url ? (
                  <a href={s.url} target="_blank" rel="noreferrer" className="text-earth underline underline-offset-2">
                    {s.name}
                  </a>
                ) : (
                  s.name
                )}
                {s.citation ? `, ${s.citation}` : ''}
              </li>
            ))}
          </ul>
        </Disclosure>
      </div>
    </section>
  )
}
