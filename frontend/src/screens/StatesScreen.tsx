import { useState } from 'react'
import { useFocusedMetrics, useFocusedView } from '../lib/mission'
import { SURVIVAL_LIMIT_H } from '../lib/geometry/metrics'
import { EmptyState, ErrorPanel, LoadingPanel, UncertaintyNote } from '../components/States'
import { KeyNumberTile } from '../components/KeyNumbers'
import { Panel, SectionLabel, Button } from '../components/ui'
import { ArcTable } from '../components/ArcTable'
import { TERM } from '../lib/format'

/**
 * S8 — the four states that decide whether anyone trusts this, live rather
 * than drawn. The error state really does blank the Earth numbers; the
 * uncertain state really does read the computed tolerance.
 */
export function StatesScreen() {
  const [earthEphemerisDown, setEarthEphemerisDown] = useState(false)
  const metrics = useFocusedMetrics()
  const meta = useFocusedView().meta
  const worst = metrics?.sun.longestDownArc

  return (
    <div className="mx-auto flex w-full max-w-[1440px] grow flex-col gap-7 p-4 lg:p-8">
      <header className="flex flex-wrap items-end justify-between gap-6 border-b border-line pb-5">
        <div className="flex flex-col gap-2">
          <SectionLabel>Empty, loading, error, uncertain</SectionLabel>
          <h1 className="text-display-sm font-semibold tracking-heading">Measured, not asserted</h1>
        </div>
        <p className="max-w-[420px] text-right text-body leading-6 text-ink-2">
          No state is allowed to be a shrug. Each one says what it knows, what it does not, and what you can
          do next.
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel className="flex flex-col">
          <Head kind="Empty" note="filters exclude everything" />
          <div className="grow bg-canvas">
            <EmptyState
              title="No site clears every filter"
              detail={
                <>
                  6 sites checked. The binding one is <strong className="text-ink">dark gap under 120 h</strong> —
                  four sites fail it on latitude alone.
                </>
              }
              primary={{ label: 'Relax to 400 h → 6 sites', onClick: () => {} }}
              secondary={{ label: 'Clear all filters', onClick: () => {} }}
            />
          </div>
          <Rule>
            An empty result names the filter that caused it and offers the smallest change that fixes it.
            “No results” on its own is a dead end.
          </Rule>
        </Panel>

        <Panel className="flex flex-col">
          <Head kind="Loading" note="measuring the skyline in 360 directions" />
          <div className="grow bg-canvas p-5">
            <LoadingPanel />
            <div className="mt-4">
              <Button onClick={() => setEarthEphemerisDown(false)}>Run it again to watch the bar</Button>
            </div>
          </div>
          <Rule>
            No spinner. The bar tracks the real ray-cast, the partial answer is on screen, and the note says
            which direction it can still move.
          </Rule>
        </Panel>

        <Panel className={`flex flex-col ${earthEphemerisDown ? 'border-alert' : ''}`}>
          <Head kind="Error" note="an input is missing, not “something went wrong”" tone="text-alert" />
          <div className="grow bg-canvas p-5">
            <ErrorPanel
              title="Earth positions are unavailable"
              detail={
                <>
                  The ephemeris source for Earth did not load. Sun geometry and terrain are unaffected, so
                  every number that does not depend on Earth is still live.
                </>
              }
              stillWorks="Sunlight, the dark gap, the map, the horizon profile, and compare on the Sun metrics. Time in contact with Earth, and the longest time without it, go blank — not zero."
            />
            <div className="mt-4 flex gap-3">
              <Button
                variant={earthEphemerisDown ? 'primary' : 'secondary'}
                onClick={() => setEarthEphemerisDown(!earthEphemerisDown)}
              >
                {earthEphemerisDown ? 'Restore the Earth ephemeris' : 'Simulate the failure app-wide'}
              </Button>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-4">
              <KeyNumberTile
                label={TERM.earthHours.public}
                value={metrics?.earth.upHours ?? 0}
                tone="earth"
                size="sm"
                state={earthEphemerisDown ? 'blank' : 'ready'}
                fraction={(metrics?.earth.fractionUp ?? 0)}
                footnote={earthEphemerisDown ? 'blank, not zero' : undefined}
              />
              <KeyNumberTile
                label={TERM.sunHours.public}
                value={metrics?.sun.upHours ?? 0}
                tone="sun"
                size="sm"
                state={metrics ? 'ready' : 'computing'}
                fraction={metrics?.sun.fractionUp ?? 0}
                footnote="unaffected"
              />
            </div>
          </div>
          <Rule>
            A missing input blanks exactly the numbers that depend on it. A blank is not a zero, and the
            screen says which is which.
          </Rule>
        </Panel>

        <Panel className="flex flex-col border-dashed border-uncertain">
          <Head kind="Uncertain" note="the state that matters most" tone="text-ink-2" />
          <div className="grow bg-canvas p-5">
            <div className="flex flex-col gap-4">
              <KeyNumberTile
                label="Longest dark gap"
                value={metrics?.sun.longestDownH ?? 0}
                tone="neutral"
                size="lg"
                state={metrics ? (worst?.grazing ? 'uncertain' : 'ready') : 'computing'}
                toleranceH={metrics?.sun.longestDownToleranceH}
                open={Boolean(metrics?.sun.longestDownOpen)}
                fraction={(metrics?.sun.longestDownH ?? 0) / SURVIVAL_LIMIT_H}
                footnote={
                  worst?.grazing
                    ? 'grazing crossing — the timing is not knowable at this resolution'
                    : 'both edges of the gap move, so it carries both edges’ errors combined'
                }
              />
              <UncertaintyNote>
                These are the live values for the selected site. The elevation model’s vertical error is up to{' '}
                {meta ? `±${meta.uncertainty.demVerticalErrorM} m` : 'a few metres'}; at the blocking range that
                becomes an angle, and the angle
                becomes a time through the rate at which the Sun crosses the skyline. Where that rate is too
                small to time, the arc says <em className="not-italic text-ink">grazing</em> rather than
                inventing a precision.
              </UncertaintyNote>
            </div>
          </div>
          <Rule>
            The margin is never behind a tooltip. A tool that admits what it does not know is the one a
            planner will use twice.
          </Rule>
        </Panel>
      </div>

      {metrics && (
        <Panel className="p-5">
          <ArcTable metrics={metrics} />
        </Panel>
      )}
    </div>
  )
}

function Head({ kind, note, tone = 'text-ink-3' }: { kind: string; note: string; tone?: string }) {
  return (
    <div className="flex items-baseline gap-2.5 border-b border-line px-5 py-3.5">
      <span className={`text-caption font-semibold tracking-caps uppercase ${tone}`}>{kind}</span>
      <span className="text-small text-ink-3">{note}</span>
    </div>
  )
}

function Rule({ children }: { children: React.ReactNode }) {
  return (
    <p className="border-t border-line px-5 py-3.5 text-small leading-5 text-ink-2">
      <strong className="font-semibold text-ink">Rule:</strong> {children}
    </p>
  )
}
