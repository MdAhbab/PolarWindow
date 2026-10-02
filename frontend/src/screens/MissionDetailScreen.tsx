import { useMemo, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { useMission as useStore, windowFromInstants } from '../lib/store'
import { useWindowParams } from '../lib/mission'
import { useSiteView } from '../lib/api/queries'
import { latestAccessed, type MissionDetail, type MissionSource, type PublishedDate } from '../lib/api/adapters'
import { getSites, hasSite, siteById } from '../lib/sites'
import {
  INSTRUMENT_LABEL,
  STATUS_GLYPH,
  STATUS_LABEL,
  coordinateKindWords,
  nearestCandidates,
  publishedTitle,
  publishedWords,
  publisherFor,
} from '../lib/missions'
import { coords, dateTimeWords, isoDateWords, msFromModelH, windowLine } from '../lib/format'
import { surfaceSentence } from '../lib/siteSentence'
import { ArcTable } from '../components/ArcTable'
import { Sources } from '../components/Sources'
import { ANSWER_TEXT, ChartPanel, Rows, SectionLayout, StatePanel, UNDER_QUESTION } from '../components/lifecycle/Section'
import { SECTIONS } from '../components/lifecycle/JourneyBar'
import { useMotionClass } from '../hooks/useMotion'
import { SURVIVAL_LIMIT_H } from '../lib/geometry/metrics'
import { DateSlider } from '../components/DateSlider'
import { KeyNumberRow } from '../components/KeyNumbers'
import { Ribbon } from '../components/Ribbon'
import { WindowPicker } from '../components/WindowPicker'
import { ExplainPanel } from '../components/Agents'
import { SummarySpeaker } from '../components/SummarySpeaker'
import { ProblemPanel, Skeleton, UncertaintyNote } from '../components/States'
import { Button, Disclosure, Panel, RowGroup, SectionLabel, Unconfirmed } from '../components/ui'
import { PolarMap, POLAR_MAP_EDGE_LAT, type MissionPin } from '../components/PolarMap'
import { MoonDiscs } from '../components/MoonDiscs'

/**
 * A mission's record (§10.3), fully sourced: how it went, its dates, and its
 * target, payloads and sources on request. It sits on the mission's home
 * page, beside the six steps.
 */
export function MissionRecord({ mission: m }: { mission: MissionDetail }) {
  const asOf = (() => {
    const l = latestAccessed(m.sources)
    return l ? isoDateWords(l) : null
  })()

  return (
    <div className="grid min-w-0 items-start gap-6 xl:grid-cols-12 xl:gap-8">
      <div className="flex min-w-0 flex-col gap-6 xl:col-span-7">
        {/* The biggest card: how it went is what the page is opened for. */}
      <Panel className="flex min-w-0 flex-col gap-5 p-5 sm:p-7">
        <div className="flex flex-col gap-3">
          <h2 className="pw-eyebrow">The mission’s record</h2>
          <div className="flex items-center gap-3 text-heading leading-8 font-semibold tracking-heading text-ink sm:text-heading-lg sm:leading-9">
            <span aria-hidden="true" className="text-ink-2">
              {STATUS_GLYPH[m.status]}
            </span>
            {STATUS_LABEL[m.status]}
          </div>
        </div>
        {m.outcomeNote && <OutcomeNote note={m.outcomeNote} />}
        <MissionDates mission={m} />
      </Panel>

        <RowGroup title="About this mission">
          <Payloads mission={m} asOf={asOf} />

          <Disclosure title="Sources" meta={`${m.sources.length}${asOf ? `, last read ${asOf}` : ''}`}>
            <ul className="flex flex-col gap-3">
              {m.sources.map((s) => (
                <li key={s.url} className="flex flex-col gap-0.5 text-body leading-5">
                  <a href={s.url} target="_blank" rel="noreferrer">
                    {s.title}
                  </a>
                  <span className="text-caption text-ink-3">
                    {s.publisher} · accessed {isoDateWords(s.accessed)}
                  </span>
                </li>
              ))}
            </ul>
            {m.notes.length > 0 && (
              <>
                <SectionLabel as="h3" className="mt-2">
                  Notes on the sources
                </SectionLabel>
                <ul className="flex list-disc flex-col gap-1.5 pl-5 text-small leading-5 text-ink-2">
                  {m.notes.map((n, i) => (
                    <li key={i}>{n}</li>
                  ))}
                </ul>
              </>
            )}
            <p className="font-mono text-caption text-ink-3">Record version {m.dataVersion}</p>
          </Disclosure>
        </RowGroup>
      </div>

      <div className="min-w-0 xl:col-span-5">
        <TargetCard mission={m} asOf={asOf} />
      </div>
    </div>
  )
}

/**
 * Where it lands, as a picture and as facts: the pole from above with the
 * mission's mark when the target is within 80°S, the two faces of the Moon
 * otherwise, then the coordinates, what kind of point they are, and their
 * source. The picture has its own description; the facts are the record.
 */
function TargetCard({ mission: m, asOf }: { mission: MissionDetail; asOf: string | null }) {
  const t = m.target
  const u = <Unconfirmed asOf={asOf} />
  const polar = t !== null && t.latDeg <= POLAR_MAP_EDGE_LAT
  const pin: MissionPin[] = t
    ? [
        {
          key: m.id,
          latDeg: t.latDeg,
          lonDeg: t.lonDeg,
          dashed: t.coordinateKind !== 'actual_landing',
          label: `${m.name}: ${t.name}, ${coordinateKindWords(t.coordinateKind, m.targetName)}`,
          highlighted: true,
        },
      ]
    : []
  return (
    <Panel as="section" className="flex min-w-0 flex-col gap-4 p-5 sm:p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 className="pw-eyebrow">Target</h3>
        <span className="text-small text-ink-2">{t?.name ?? m.targetName ?? 'not published'}</span>
      </div>
      {t &&
        (polar ? (
          <div className="mx-auto w-full max-w-[420px]">
            <PolarMap sun={null} selectedSiteId={m.siteId ?? ''} size={420} missionPins={pin} siteMarks="dots" />
          </div>
        ) : (
          <MoonDiscs missions={[m]} highlight={new Set([m.id])} earthNeverRisesOnFarSide={false} />
        ))}
      {t ? (
        <dl className="grid grid-cols-1 gap-x-4 border-t border-line pt-4 text-body sm:grid-cols-[max-content_1fr] sm:gap-y-2">
          <Row term="Coordinates">
            <span className="font-mono text-small">{coords(t.latDeg, t.lonDeg)}</span>
          </Row>
          <Row term="Kind">{coordinateKindWords(t.coordinateKind, m.targetName)}</Row>
          <Row term="Landing area">{m.ellipseRing ? 'published; drawn on the Map' : u}</Row>
          <Row term="Source">
            <SourceLink url={t.sourceUrl} sources={m.sources} what="the coordinates" />
          </Row>
        </dl>
      ) : (
        <p className="text-body text-ink-2">
          No coordinates are published{m.targetName ? ` for “${m.targetName}”` : ''}. {u}
        </p>
      )}
    </Panel>
  )
}

/**
 * Step 4, Surface: what the Sun and Earth do at this target over the
 * mission's days on the surface. The same shape as the other five steps.
 */
export function SurfaceSection({ mission: m }: { mission: MissionDetail }) {
  const navigate = useNavigate()
  return (
    <SectionLayout question={SURFACE_QUESTION}>
      <section aria-label="Sun and Earth at this target" data-guide="sun-earth" className="flex min-w-0 flex-col gap-6">
        {m.siteId && m.site && hasSite(m.siteId) ? (
          <TargetPanel mission={m} siteId={m.siteId} />
        ) : (
          <StatePanel
            icon="ring"
            title="Target not published"
            detail={
              m.targetName
                ? `The published destination is “${m.targetName}”, which is not a single point with coordinates, so the Sun and Earth cannot be worked out for it yet.`
                : 'No destination with coordinates has been published for this mission, so the Sun and Earth cannot be worked out for it yet.'
            }
            stillWorks="The other steps, and the mission’s record, are unaffected."
            action={<Button onClick={() => navigate('/missions')}>Back to missions</Button>}
          />
        )}
      </section>
    </SectionLayout>
  )
}

const SURFACE_QUESTION = SECTIONS.find((s) => s.id === 'landing')!.question

/** How it went: three lines, and the rest on request. */
function OutcomeNote({ note }: { note: string }) {
  const [more, setMore] = useState(false)
  const long = note.length > 200
  return (
    <div className="flex flex-col items-start gap-1.5">
      <p className={`max-w-[62ch] text-lede leading-7 text-ink-2 ${long && !more ? 'line-clamp-4' : ''}`}>{note}</p>
      {long && (
        <button
          type="button"
          aria-expanded={more}
          onClick={() => setMore((v) => !v)}
          className="min-h-8 text-small font-semibold text-ink hover:underline"
        >
          {more ? 'Show less' : 'Show more'}
        </button>
      )}
    </div>
  )
}

/**
 * The dates that are published, and one line naming the ones that are not,
 * instead of a table of "Unconfirmed".
 */
function MissionDates({ mission: m }: { mission: MissionDetail }) {
  const known: [string, ReactNode][] = []
  const missing: string[] = []
  const add = (term: string, value: ReactNode | null) => (value === null ? missing.push(term.toLowerCase()) : known.push([term, value]))
  add('Launch', m.launch ? <DateText date={m.launch} /> : null)
  add('Landing', m.landing ? <DateText date={m.landing} /> : null)
  add('End of mission', m.endOfMission ? <DateText date={m.endOfMission} /> : null)
  add('Planned time on the surface', m.plannedSurfaceDays !== null ? `${m.plannedSurfaceDays} days` : null)
  return (
    <div className="flex flex-col gap-2 border-t border-line pt-3">
      {known.length > 0 && (
        <dl className="grid grid-cols-1 gap-x-4 text-body sm:grid-cols-[max-content_1fr] sm:gap-y-1.5">
          {known.map(([term, value]) => (
            <Row key={term} term={term}>
              {value}
            </Row>
          ))}
        </dl>
      )}
      {missing.length > 0 && (
        <p className="text-small text-ink-3">
          Not published: {missing.join(', ')}.
        </p>
      )}
    </div>
  )
}

/** A published date in words; the source's own phrase is its tooltip. */
function DateText({ date }: { date: PublishedDate }) {
  return <span title={publishedTitle(date)}>{publishedWords(date)}</span>
}

/** A term and its value: side by side from 640 px, stacked below it so a date is not squeezed into a column. */
function Row({ term, children }: { term: string; children: ReactNode }) {
  return (
    <>
      <dt className="mt-2 text-ink-3 first:mt-0 sm:mt-0">{term}</dt>
      <dd className="min-w-0 text-ink">{children}</dd>
    </>
  )
}

/** A source link whose text is the publisher, never "link". */
function SourceLink({ url, sources, what }: { url: string; sources: MissionSource[]; what: string }) {
  const publisher = publisherFor(url, sources)
  return (
    <a href={url} target="_blank" rel="noreferrer" aria-label={`${publisher}, source for ${what}`}>
      {publisher}
    </a>
  )
}

function Payloads({ mission: m, asOf }: { mission: MissionDetail; asOf: string | null }) {
  const incomplete = m.unconfirmedFields.includes('payloads')
  const name = (p: MissionDetail['payloads'][number]) => (p.acronym ? `${p.name} (${p.acronym})` : p.name)
  return (
    <Disclosure
      title="What it carries"
      meta={`${m.payloads.length} payload${m.payloads.length === 1 ? '' : 's'}${incomplete ? ', list incomplete' : ''}`}
    >
      {incomplete && (
        <p className="text-small leading-5 text-uncertain">
          Known to be incomplete: NASA counts more payloads than it names. Only the named ones are listed.
        </p>
      )}
      {m.payloads.length === 0 ? (
        <p className="text-body text-ink-2">
          No payload is named in the sources. <Unconfirmed asOf={asOf} />
        </p>
      ) : (
        <>
          {/* ≥ 768: a real table. */}
          <div className="relative hidden overflow-x-auto md:block">
            <table className="w-full border-collapse text-left">
              <caption className="sr-only">
                The mission’s payloads: what each measures, what it is for, and where that is published.
              </caption>
              <thead>
                <tr className="bg-inset">
                  {['Payload', 'Organisation', 'Measures', 'Purpose', 'Source'].map((h) => (
                    <th
                      key={h}
                      scope="col"
                      className="px-2 py-2 text-tag font-semibold tracking-caps-sm text-ink-3 uppercase"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {m.payloads.map((p) => (
                  <tr key={p.id} className="border-t border-line align-top">
                    <th scope="row" className="px-2 py-2.5 text-small font-semibold text-ink">
                      {name(p)}
                      {p.unconfirmed && (
                        <span className="block font-normal">
                          <Unconfirmed asOf={asOf} />
                        </span>
                      )}
                    </th>
                    <td className="px-2 py-2.5 text-small text-ink-2">{p.organisation ?? <Unconfirmed asOf={asOf} />}</td>
                    <td className="px-2 py-2.5 text-small text-ink-2">
                      {p.instrumentTypes.map((t) => INSTRUMENT_LABEL[t]).join(', ')}
                    </td>
                    <td className="px-2 py-2.5 text-small leading-5 text-ink-2">{p.purpose}</td>
                    <td className="px-2 py-2.5 text-small wrap-anywhere">
                      <SourceLink url={p.sourceUrl} sources={m.sources} what={p.acronym ?? p.name} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {/* < 768: one definition list per payload, keeping its source link. */}
          <ul className="flex flex-col gap-3 md:hidden">
            {m.payloads.map((p) => (
              <li key={p.id} className="border-t border-line pt-3">
                <h3 className="text-body font-semibold text-ink">{name(p)}</h3>
                {p.unconfirmed && <Unconfirmed asOf={asOf} />}
                <dl className="mt-1.5 grid grid-cols-1 gap-x-3 text-small sm:grid-cols-[max-content_1fr] sm:gap-y-1">
                  <Row term="Organisation">{p.organisation ?? <Unconfirmed asOf={asOf} />}</Row>
                  <Row term="Measures">{p.instrumentTypes.map((t) => INSTRUMENT_LABEL[t]).join(', ')}</Row>
                  <Row term="Purpose">{p.purpose}</Row>
                  <Row term="Source">
                    <SourceLink url={p.sourceUrl} sources={m.sources} what={p.acronym ?? p.name} />
                  </Row>
                </dl>
              </li>
            ))}
          </ul>
        </>
      )}
    </Disclosure>
  )
}

/** The window a mission opens on: its surface window, else the span its landing date covers. */
export function initialWindow(m: MissionDetail): { startH: number; hours: number } | null {
  const sw = m.surfaceWindow
  if (sw.startIso && sw.endIso) return windowFromInstants(Date.parse(sw.startIso), Date.parse(sw.endIso))
  if (m.landing && m.landing.precision !== 'day' && m.landing.precision !== 'minute') {
    return windowFromInstants(m.landing.startMs, m.landing.startMs + 30 * 86_400_000)
  }
  return null
}

function SurfaceWindowLine({ mission: m, site }: { mission: MissionDetail; site: string }) {
  const sw = m.surfaceWindow
  const s = sw.startIso ? Date.parse(sw.startIso) : null
  const e = sw.endIso ? Date.parse(sw.endIso) : null
  const range = s !== null && e !== null ? `${dateTimeWords(s)} – ${dateTimeWords(e)}` : null
  let line: string
  switch (sw.basis) {
    case 'published':
      line = `${range}, as flown`
      break
    case 'planned':
      line = `${range}, planned`
      break
    case 'assumed':
      line = `One lunar day from landing (duration not published)${range ? `: ${range}` : ''}`
      break
    case 'none':
      line =
        m.landing && m.landing.precision !== 'day' && m.landing.precision !== 'minute'
          ? `Landing known only to the ${m.landing.precision}; choose a date below`
          : `${sw.note} Choose a date below.`
  }
  return (
    <p className="text-caption leading-caption text-ink-3">
      At {site}. Time on the surface: {line}.
    </p>
  )
}

function TargetPanel({ mission: m, siteId }: { mission: MissionDetail; siteId: string }) {
  const navigate = useNavigate()
  const w = useWindowParams()
  const view = useSiteView(siteId, w, false)
  const { cursorH, setSite, windowStartH, windowHours } = useStore(
    useShallow((s) => ({ cursorH: s.cursorH, setSite: s.setSite, windowStartH: s.windowStartH, windowHours: s.windowHours })),
  )
  const site = siteById(siteId)
  const metrics = view.data?.metrics
  const meta = view.data?.meta
  const terrainModelled = meta?.uncertainty.terrainModelled ?? site.terrainModelled
  const featureCentre = m.target?.coordinateKind === 'feature_centre'
  const nearest = useMemo(() => nearestCandidates(site.latDeg, site.lonDeg, getSites(), 3, siteId), [site, siteId])
  const seedIds = [siteId, ...nearest.map((s) => s.id)]
  const missionWindow =
    m.surfaceWindow.startIso && m.surfaceWindow.endIso
      ? { startMs: Date.parse(m.surfaceWindow.startIso), endMs: Date.parse(m.surfaceWindow.endIso) }
      : null
  const arrive = useMotionClass('pw-arrive')

  const seed = () => {
    setSite(siteId)
    useStore.setState({ compareIds: seedIds })
  }

  return (
    <>
      {metrics ? (
        <div className={`${UNDER_QUESTION} flex flex-col gap-3 ${arrive}`}>
          <p data-guide="section-answer" className={ANSWER_TEXT}>
            {surfaceSentence(metrics)}
          </p>
          <SurfaceWindowLine mission={m} site={site.name} />
          <div data-guide="listen" className="pt-1">
            <SummarySpeaker view={view} />
          </div>
        </div>
      ) : view.error ? null : (
        <div className={`${UNDER_QUESTION} flex flex-col gap-2.5`} aria-hidden="true">
          <Skeleton className="h-8 w-full max-w-4xl lg:h-10" />
          <Skeleton className="h-8 w-1/2 max-w-xl lg:h-10" />
          <Skeleton className="mt-1.5 h-4 w-64" />
        </div>
      )}

      {(featureCentre || !terrainModelled || (terrainModelled && meta?.uncertainty.partialCoverage)) && (
        <div className="-mt-2 flex flex-col gap-2">
          {featureCentre && (
            <UncertaintyNote>
              For the centre of {m.targetName ?? 'the named feature'}; the landing point isn’t published.
            </UncertaintyNote>
          )}
          {!terrainModelled && (
            <UncertaintyNote>
              No terrain data outside 80°S, so this is worked out as if the ground were flat. Real hills could block more.
            </UncertaintyNote>
          )}
          {terrainModelled && meta?.uncertainty.partialCoverage && (
            <UncertaintyNote>
              Terrain data covers only {Math.round(meta.uncertainty.coverage * 100)}% of the directions around this spot,
              so these numbers are likely too hopeful.
            </UncertaintyNote>
          )}
        </div>
      )}

      {view.error ? (
        <ProblemPanel error={view.error} fallbackTitle="Cannot compute this target" onRetry={view.refetch} />
      ) : (
        <div className={view.isFetching && metrics ? 'opacity-70 transition-opacity' : ''}>
          <KeyNumberRow metrics={metrics} uncertain={!terrainModelled} />
        </div>
      )}

      {metrics && !view.error && (
        <ChartPanel
          title="Sunlight and contact with Earth over these dates"
          chart={
            <div className="flex flex-col gap-4">
              <DateSlider compact />
              <div className="flex flex-col gap-1.5">
                <span className="text-small font-semibold text-sun">Sunlight</span>
                <Ribbon
                  arcs={metrics.sun.arcs}
                  windowStartH={metrics.windowStartH}
                  windowHours={metrics.windowHours}
                  tone="sun"
                  cursorH={cursorH}
                  alertOverH={SURVIVAL_LIMIT_H}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <span className="text-small font-semibold text-earth">Contact with Earth</span>
                <Ribbon
                  arcs={metrics.earth.arcs}
                  windowStartH={metrics.windowStartH}
                  windowHours={metrics.windowHours}
                  tone="earth"
                  cursorH={cursorH}
                />
              </div>
            </div>
          }
          table={<ArcTable metrics={metrics} />}
        />
      )}

      <Rows
        about={
          <>
            <Disclosure title="How this was worked out">
              <p className="text-body leading-6 text-ink-2">
                The skyline around {site.name} ({coords(site.latDeg, site.lonDeg)},{' '}
                {site.elevM !== null ? `height ${site.elevM.toLocaleString()} m` : 'height not known'}) was measured
                once from the terrain map. The Sun and Earth are traced across the sky for these dates and counted up
                while above it; each time an edge is crossed carries a ± from the map’s height error.
              </p>
            </Disclosure>
            <Disclosure title="Sources" meta="terrain map, Sun and Earth positions">
              <Sources meta={meta} bare />
            </Disclosure>
          </>
        }
      >
        <Disclosure guide="dates" title="Change the dates" meta={windowLine(msFromModelH(windowStartH), windowHours)}>
          <WindowPicker siteId={siteId} missionWindow={missionWindow} />
        </Disclosure>
        <ExplainPanel siteId={siteId} start={w.start} end={w.end} />
      </Rows>

      <div className="flex flex-col gap-3">
        <h3 className="pw-eyebrow">Go further with this spot</h3>
        <div className="flex flex-wrap gap-3">
          <Button
            onClick={() => {
              setSite(siteId)
              navigate('/site')
            }}
          >
            Open the site page
          </Button>
          <Button
            onClick={() => {
              seed()
              navigate(`/compare?from=${encodeURIComponent(m.id)}&sites=${seedIds.map(encodeURIComponent).join(',')}`)
            }}
            describedBy="nearest-note"
          >
            Compare with nearby sites
          </Button>
          <Button
            variant="ghost"
            onClick={() => {
              seed()
              navigate('/report')
            }}
          >
            Printable report
          </Button>
        </div>
        <p id="nearest-note" className="text-caption text-ink-3">
          Compare adds the three nearest candidate sites: {nearest.map((s) => s.name).join(', ')}.
        </p>
      </div>
    </>
  )
}
