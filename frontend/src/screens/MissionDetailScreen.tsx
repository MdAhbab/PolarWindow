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
import { SURVIVAL_LIMIT_H } from '../lib/geometry/metrics'
import { DateSlider } from '../components/DateSlider'
import { KeyNumberRow } from '../components/KeyNumbers'
import { Ribbon } from '../components/Ribbon'
import { WindowPicker } from '../components/WindowPicker'
import { ExplainPanel } from '../components/Agents'
import { SummarySpeaker } from '../components/SummarySpeaker'
import { EmptyState, ProblemPanel, UncertaintyNote } from '../components/States'
import { Button, Disclosure, Panel, SectionLabel, Unconfirmed } from '../components/ui'

/**
 * S10's body, now the hub's Landing section (design-lifecycle.md §4): one
 * mission, fully sourced (§10.3), then the product's question: what do the
 * Sun and Earth do at this target over this mission's days?
 *
 * Layout: at ≥ 1280 the record is the left 5/12 and "Sun & Earth" the sticky
 * right 7/12. Below that the answer follows the record's status and dates
 * (then the four numbers, then the payloads), which is also the DOM order, so
 * reading order and focus order agree at every width. The mission's name and
 * the back link are the hub's header, above the six steps.
 */
export function LandingSection({ mission: m }: { mission: MissionDetail }) {
  const navigate = useNavigate()

  const asOf = (() => {
    const l = latestAccessed(m.sources)
    return l ? isoDateWords(l) : null
  })()
  const u = <Unconfirmed asOf={asOf} />

  return (
    <div className="grid grow gap-6 xl:grid-cols-12 xl:grid-rows-[auto_1fr] xl:items-start">
      {/* Status and dates. */}
      <div className="flex min-w-0 flex-col gap-4 xl:col-span-5 xl:col-start-1 xl:row-start-1">
        <Panel className="flex flex-col gap-3 p-5">
          <div className="text-title-lg font-semibold text-ink">
            <span aria-hidden="true">{STATUS_GLYPH[m.status]} </span>
            {STATUS_LABEL[m.status]}
          </div>
          {m.outcomeNote && <OutcomeNote note={m.outcomeNote} />}
          <MissionDates mission={m} />
        </Panel>
      </div>

      {/* The answer: sticky on the right at ≥ 1280. */}
      <section
        aria-labelledby="sun-earth-h"
        data-guide="sun-earth"
        className="flex min-w-0 flex-col gap-4 xl:sticky xl:top-4 xl:col-span-7 xl:col-start-6 xl:row-span-2 xl:row-start-1"
      >
        <SectionLabel id="sun-earth-h">Sun &amp; Earth at this target</SectionLabel>
        {m.siteId && m.site && hasSite(m.siteId) ? (
          <TargetPanel mission={m} siteId={m.siteId} />
        ) : (
          <Panel>
            <EmptyState
              title="Target not published, so Sun and Earth can't be computed for it yet"
              detail={
                m.targetName
                  ? `The published destination is “${m.targetName}”, which is not a single point with coordinates.`
                  : 'No destination with coordinates has been published for this mission.'
              }
              secondary={{ label: 'Back to missions', onClick: () => navigate('/missions') }}
            />
          </Panel>
        )}
      </section>

      {/* 4–7: target, payloads, sources: each one row, opened on request. */}
      <div className="flex min-w-0 flex-col gap-3 xl:col-span-5 xl:col-start-1 xl:row-start-2">
        <Disclosure title="Target" meta={m.target?.name ?? m.targetName ?? 'not published'}>
          {m.target ? (
            <dl className="grid grid-cols-1 gap-x-4 text-body sm:grid-cols-[max-content_1fr] sm:gap-y-2">
              <Row term="Coordinates">
                <span className="font-mono text-small">{coords(m.target.latDeg, m.target.lonDeg)}</span>
              </Row>
              <Row term="Kind">{coordinateKindWords(m.target.coordinateKind, m.targetName)}</Row>
              <Row term="Landing area">{m.ellipseRing ? 'published; drawn on the Map' : u}</Row>
              <Row term="Source">
                <SourceLink url={m.target.sourceUrl} sources={m.sources} what="the coordinates" />
              </Row>
            </dl>
          ) : (
            <p className="text-body text-ink-2">
              No coordinates are published{m.targetName ? ` for “${m.targetName}”` : ''}. {u}
            </p>
          )}
        </Disclosure>

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
      </div>
    </div>
  )
}

/** How it went: three lines, and the rest on request. */
function OutcomeNote({ note }: { note: string }) {
  const [more, setMore] = useState(false)
  const long = note.length > 200
  return (
    <div className="flex flex-col items-start gap-1">
      <p className={`text-body leading-6 text-ink-2 ${long && !more ? 'line-clamp-3' : ''}`}>{note}</p>
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

function SurfaceWindowLine({ mission: m }: { mission: MissionDetail }) {
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
    <div className="flex flex-col gap-1">
      <span className="text-small font-medium text-ink-3">Time on the surface</span>
      <p className="text-control leading-6 text-ink">{line}</p>
    </div>
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

  const seed = () => {
    setSite(siteId)
    useStore.setState({ compareIds: seedIds })
  }

  return (
    <div className="flex flex-col gap-4">
      <Panel className="flex flex-col gap-3 p-5">
        <div className="flex flex-col gap-0.5">
          <span className="text-title font-semibold text-ink">{site.name}</span>
          <span className="font-mono text-caption text-ink-3">
            {coords(site.latDeg, site.lonDeg)} ·{' '}
            {site.elevM !== null ? `height ${site.elevM.toLocaleString()} m` : 'height not known'}
          </span>
        </div>
        <SurfaceWindowLine mission={m} />
        <div data-guide="listen">
          <SummarySpeaker view={view} />
        </div>
      </Panel>

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

      {view.error ? (
        <ProblemPanel error={view.error} fallbackTitle="Cannot compute this target" onRetry={view.refetch} />
      ) : (
        <div className={view.isFetching && metrics ? 'opacity-70 transition-opacity' : ''}>
          <KeyNumberRow metrics={metrics} uncertain={!terrainModelled} />
        </div>
      )}

      {metrics && !view.error && (
        <Panel className="flex flex-col gap-3 p-5">
          <DateSlider compact />
          <div className="flex flex-col gap-1.5">
            <span className="text-tag font-semibold tracking-caps-md text-sun uppercase">Sunlight over these dates</span>
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
            <span className="text-tag font-semibold tracking-caps-md text-earth uppercase">Contact with Earth over these dates</span>
            <Ribbon
              arcs={metrics.earth.arcs}
              windowStartH={metrics.windowStartH}
              windowHours={metrics.windowHours}
              tone="earth"
              cursorH={cursorH}
            />
          </div>
        </Panel>
      )}

      <Disclosure guide="dates" title="Change the dates" meta={windowLine(msFromModelH(windowStartH), windowHours)}>
        <WindowPicker siteId={siteId} missionWindow={missionWindow} />
      </Disclosure>

      <div className="flex flex-col gap-2">
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

      <ExplainPanel siteId={siteId} start={w.start} end={w.end} />
    </div>
  )
}
