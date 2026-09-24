import { useEffect, useMemo, useRef, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { useMission as useStore, windowFromInstants } from '../lib/store'
import { useMission as useMissionQuery } from '../lib/api/queries'
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
import { coords, dateTimeWords, isoDateWords } from '../lib/format'
import { SURVIVAL_LIMIT_H } from '../lib/geometry/metrics'
import { DateSlider } from '../components/DateSlider'
import { KeyNumberRow } from '../components/KeyNumbers'
import { Ribbon } from '../components/Ribbon'
import { WindowPicker } from '../components/WindowPicker'
import { ExplainPanel } from '../components/Agents'
import { SummarySpeaker } from '../components/SummarySpeaker'
import { EmptyState, LoadingPanel, ProblemPanel, UncertaintyNote } from '../components/States'
import { Button, Panel, SectionLabel, Unconfirmed } from '../components/ui'
import { ApiError } from '../lib/api/client'

/**
 * S10 — one mission, fully sourced (§10.3), then the product's question: what
 * do the Sun and Earth do at this target over this mission's days?
 *
 * Layout: at ≥ 1280 the record is the left 5/12 and "Sun & Earth" the sticky
 * right 7/12. Below that the answer follows the record's header block (status
 * and dates first, then the four numbers, then the payloads), which is also
 * the DOM order, so reading order and focus order agree at every width.
 */
export function MissionDetailScreen() {
  const { id } = useParams()
  const navigate = useNavigate()
  const q = useMissionQuery(id)
  const setWindow = useStore((s) => s.setWindow)
  const applied = useRef<string | null>(null)
  const m = q.data

  // A mission sets the window to its surface window (system-design §10.6),
  // once per mission, so a date the user then picks is not overwritten.
  useEffect(() => {
    if (!m || applied.current === m.id) return
    applied.current = m.id
    const w = initialWindow(m)
    if (w) setWindow(w.startH, w.hours)
  }, [m, setWindow])

  useEffect(() => {
    if (m) document.title = `${m.name} — POLAR WINDOW`
  }, [m])

  if (q.isPending) {
    return (
      <div className="grid gap-6 p-4 lg:p-6 xl:grid-cols-12">
        <div className="flex flex-col gap-3 xl:col-span-5" aria-hidden="true">
          {/* Static skeleton lines: motion is reserved for data. */}
          <div className="h-8 w-2/3 bg-inset" />
          <div className="h-4 w-1/2 bg-inset" />
          <div className="h-24 w-full bg-inset" />
          <div className="h-32 w-full bg-inset" />
        </div>
        <div className="xl:col-span-7">
          <LoadingPanel
            done={0}
            total={1}
            title="Loading the mission record"
            unit="records"
            note="The record, its payloads and its sources, then the Sun and Earth at its target."
          />
        </div>
      </div>
    )
  }

  if (q.error || !m) {
    const notFound = q.error instanceof ApiError && q.error.status === 404
    return (
      <div className="mx-auto w-full max-w-2xl p-4 lg:p-8">
        <ProblemPanel
          error={q.error}
          fallbackTitle="That mission isn't in the list"
          onRetry={notFound ? undefined : () => void q.refetch()}
          action={{ label: 'Back to missions', onClick: () => navigate('/missions') }}
        />
      </div>
    )
  }

  const asOf = (() => {
    const l = latestAccessed(m.sources)
    return l ? isoDateWords(l) : null
  })()
  const u = <Unconfirmed asOf={asOf} />
  const vehicle = m.vehicleName

  return (
    <div className="grid grow gap-6 p-4 lg:p-6 xl:grid-cols-12 xl:grid-rows-[auto_1fr] xl:items-start">
      {/* 1–3: header, status, dates. */}
      <div className="flex min-w-0 flex-col gap-4 xl:col-span-5 xl:col-start-1 xl:row-start-1">
        <Link to="/missions" className="inline-flex h-11 items-center text-[14px] font-semibold">
          ← All CLPS missions
        </Link>
        <header className="flex flex-col gap-1.5">
          <h1 className="text-[28px] leading-9 font-semibold tracking-[-0.01em]">
            {m.name}
            {vehicle && <span className="font-normal text-ink-2"> · {vehicle}</span>}
          </h1>
          <p className="text-[14px] leading-6 text-ink-2">
            {m.provider ?? (
              <>
                Provider {u}
              </>
            )}{' '}
            · {m.lander ?? (
              <>
                lander {u}
              </>
            )}{' '}
            · task order {m.taskOrder ?? u}
            {!vehicle && (
              <>
                {' '}
                · vehicle name {u}
              </>
            )}
          </p>
        </header>

        <Panel as="section" className="flex flex-col gap-2 p-5">
          <SectionLabel>Status</SectionLabel>
          <div className="text-[18px] font-semibold text-ink">
            <span aria-hidden="true">{STATUS_GLYPH[m.status]} </span>
            {STATUS_LABEL[m.status]}
          </div>
          {m.outcomeNote && <p className="text-[14px] leading-6 text-ink-2">{m.outcomeNote}</p>}
        </Panel>

        <Panel as="section" className="flex flex-col gap-3 p-5">
          <SectionLabel>Dates</SectionLabel>
          <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-2 text-[14px]">
            <Row term="Launch">{m.launch ? <DateText date={m.launch} /> : u}</Row>
            <Row term="Landing">{m.landing ? <DateText date={m.landing} /> : u}</Row>
            <Row term="End of mission">{m.endOfMission ? <DateText date={m.endOfMission} /> : u}</Row>
            <Row term="Planned time on the surface">
              {m.plannedSurfaceDays !== null ? `${m.plannedSurfaceDays} days` : u}
            </Row>
          </dl>
        </Panel>
      </div>

      {/* The answer: sticky on the right at ≥ 1280. */}
      <section
        aria-labelledby="sun-earth-h"
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

      {/* 4–7: target, payloads, sources, version. */}
      <div className="flex min-w-0 flex-col gap-4 xl:col-span-5 xl:col-start-1 xl:row-start-2">
        <Panel as="section" className="flex flex-col gap-3 p-5">
          <SectionLabel>Target</SectionLabel>
          {m.target ? (
            <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-2 text-[14px]">
              <Row term="Name">{m.target.name}</Row>
              <Row term="Coordinates">
                <span className="font-mono text-[13px]">{coords(m.target.latDeg, m.target.lonDeg)}</span>
              </Row>
              <Row term="Kind">{coordinateKindWords(m.target.coordinateKind, m.targetName)}</Row>
              <Row term="Landing ellipse">{m.ellipseRing ? 'published; drawn on the Map' : u}</Row>
              <Row term="Source">
                <SourceLink url={m.target.sourceUrl} sources={m.sources} what="the coordinates" />
              </Row>
            </dl>
          ) : (
            <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-2 text-[14px]">
              <Row term="Destination">{m.targetName ?? u}</Row>
              <Row term="Coordinates">
                {u}
              </Row>
            </dl>
          )}
        </Panel>

        <Payloads mission={m} asOf={asOf} />

        <Panel as="section" className="flex flex-col gap-3 p-5">
          <SectionLabel>Sources</SectionLabel>
          <ul className="flex flex-col gap-3">
            {m.sources.map((s) => (
              <li key={s.url} className="flex flex-col gap-0.5 text-[14px] leading-5">
                <a href={s.url} target="_blank" rel="noreferrer">
                  {s.title}
                </a>
                <span className="text-[12px] text-ink-3">
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
              <ul className="flex list-disc flex-col gap-1.5 pl-5 text-[13px] leading-5 text-ink-2">
                {m.notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </>
          )}
        </Panel>

        <p className="font-mono text-[12px] text-ink-3">
          Record version {m.dataVersion}
          {asOf ? ` · sources last read ${asOf}` : ''}
        </p>
      </div>
    </div>
  )
}

/** A published date in words; the source's own phrase is its tooltip. */
function DateText({ date }: { date: PublishedDate }) {
  return <span title={publishedTitle(date)}>{publishedWords(date)}</span>
}

function Row({ term, children }: { term: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-ink-3">{term}</dt>
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
    <Panel as="section" className="flex flex-col gap-3 p-5">
      <SectionLabel>Payload manifest</SectionLabel>
      {incomplete && (
        <p className="text-[13px] leading-5 text-uncertain">
          Known to be incomplete: NASA counts more payloads than it names. Only the named ones are listed.
        </p>
      )}
      {m.payloads.length === 0 ? (
        <p className="text-[14px] text-ink-2">
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
                      className="px-2 py-2 text-[11px] font-semibold tracking-[0.08em] text-ink-3 uppercase"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {m.payloads.map((p) => (
                  <tr key={p.id} className="border-t border-line align-top">
                    <th scope="row" className="px-2 py-2.5 text-[13px] font-semibold text-ink">
                      {name(p)}
                      {p.unconfirmed && (
                        <span className="block font-normal">
                          <Unconfirmed asOf={asOf} />
                        </span>
                      )}
                    </th>
                    <td className="px-2 py-2.5 text-[13px] text-ink-2">{p.organisation ?? <Unconfirmed asOf={asOf} />}</td>
                    <td className="px-2 py-2.5 text-[13px] text-ink-2">
                      {p.instrumentTypes.map((t) => INSTRUMENT_LABEL[t]).join(', ')}
                    </td>
                    <td className="px-2 py-2.5 text-[13px] leading-5 text-ink-2">{p.purpose}</td>
                    <td className="px-2 py-2.5 text-[13px] wrap-anywhere">
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
                <h3 className="text-[14px] font-semibold text-ink">{name(p)}</h3>
                {p.unconfirmed && <Unconfirmed asOf={asOf} />}
                <dl className="mt-1.5 grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-[13px]">
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
    </Panel>
  )
}

/** The window a mission opens on: its surface window, else the span its landing date covers. */
function initialWindow(m: MissionDetail): { startH: number; hours: number } | null {
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
      <span className="text-[13px] font-medium text-ink-3">Surface window</span>
      <p className="text-[15px] leading-6 text-ink">{line}</p>
    </div>
  )
}

function TargetPanel({ mission: m, siteId }: { mission: MissionDetail; siteId: string }) {
  const navigate = useNavigate()
  const w = useWindowParams()
  const view = useSiteView(siteId, w, false)
  const { face, cursorH, setSite } = useStore(
    useShallow((s) => ({ face: s.face, cursorH: s.cursorH, setSite: s.setSite })),
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
          <span className="text-[17px] font-semibold text-ink">{site.name}</span>
          <span className="font-mono text-[12px] text-ink-3">
            {coords(site.latDeg, site.lonDeg)} ·{' '}
            {site.elevM !== null ? `elev ${site.elevM.toLocaleString()} m` : 'height not modelled'}
          </span>
        </div>
        <SurfaceWindowLine mission={m} />
        <SummarySpeaker view={view} />
      </Panel>

      {(!terrainModelled || featureCentre || meta?.uncertainty.partialCoverage) && (
        <UncertaintyNote>
          {!terrainModelled && (
            <span className="block">
              Terrain is not modelled outside 80°S. Sun and Earth are computed against a smooth Moon, so real
              hills could block more.
            </span>
          )}
          {featureCentre && (
            <span className="mt-1 block">
              Numbers are for the centre of {m.targetName ?? 'the named feature'}; the landing point is not
              published.
            </span>
          )}
          {terrainModelled && meta?.uncertainty.partialCoverage && (
            <span className="mt-1 block">
              Terrain covers only {Math.round(meta.uncertainty.coverage * 100)}% of the sampled bearings here;
              the rest assume a smooth Moon, so these numbers are likely optimistic.
            </span>
          )}
        </UncertaintyNote>
      )}

      {view.error ? (
        <ProblemPanel error={view.error} fallbackTitle="Cannot compute this target" onRetry={view.refetch} />
      ) : (
        <div className={view.isFetching && metrics ? 'opacity-70 transition-opacity' : ''}>
          <KeyNumberRow metrics={metrics} face={face} uncertain={!terrainModelled} />
        </div>
      )}

      {metrics && !view.error && (
        <Panel className="flex flex-col gap-3 p-5">
          <DateSlider compact />
          <div className="flex flex-col gap-1.5">
            <span className="text-[11px] font-semibold tracking-[0.1em] text-sun uppercase">Sun over the window</span>
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
            <span className="text-[11px] font-semibold tracking-[0.1em] text-earth uppercase">Earth contact</span>
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

      <Panel className="flex flex-col gap-3 p-5">
        <SectionLabel as="h3">Change the dates</SectionLabel>
        <WindowPicker siteId={siteId} missionWindow={missionWindow} />
      </Panel>

      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap gap-3">
          <Button
            onClick={() => {
              setSite(siteId)
              navigate('/clocks')
            }}
          >
            Open in Site view
          </Button>
          <Button
            onClick={() => {
              seed()
              navigate(`/compare?from=${encodeURIComponent(m.id)}&sites=${seedIds.map(encodeURIComponent).join(',')}`)
            }}
            describedBy="nearest-note"
          >
            Compare with nearby candidates
          </Button>
          <Button
            onClick={() => {
              seed()
              navigate('/report')
            }}
          >
            Hand-over report
          </Button>
        </div>
        <p id="nearest-note" className="text-[12px] text-ink-3">
          Compare uses this target and the three candidate sites nearest by distance:{' '}
          {nearest.map((s) => `${s.code} ${s.name}`).join(', ')}.
        </p>
      </div>

      <ExplainPanel siteId={siteId} start={w.start} end={w.end} />
    </div>
  )
}
