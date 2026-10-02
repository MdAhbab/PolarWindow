import { useId, useState, type ReactNode } from 'react'
import { useSettingsTab, type SettingsTab } from '../lib/settingsTab'
import { useNavigate } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { useMission } from '../lib/store'
import { useSession } from '../lib/session'
import { useGuide } from '../lib/guide'
import { useProjectSettings, useSettingsActions } from '../lib/api/queries'
import { DataSources, FlatRows, ParametersPanel, People, RiskScalePanel } from './lifecycle/ProjectPanels'
import type { ApiError, ModelStateDTO, SettingsDTO } from '../lib/api/client'
import { dateTimeWords, isoDateWords } from '../lib/format'
import { DATA_MODE, snapshotCapturedAt, useSnapshotActive } from '../lib/api/snapshot'
import { Skeleton } from './States'
import { Sheet } from './Sheet'
import { Button, Segmented, Tabs } from './ui'

const TABS: { id: SettingsTab; label: string }[] = [
  { id: 'project', label: 'Project' },
  { id: 'parameters', label: 'Parameters' },
  { id: 'risk', label: 'Risk scale' },
  { id: 'sources', label: 'Data sources' },
  { id: 'appearance', label: 'Appearance' },
  { id: 'offline', label: 'Offline copy' },
]

/**
 * Settings: one place for everything that is not the data, grouped by task.
 *
 * Project (who is signed in, the AI assistant, the service's state and its
 * clean-up), the team's parameters, the risk scale, where the live data comes
 * from, appearance (theme, motion, the single-key shortcuts WCAG 2.1.4
 * requires a switch for, the guide), and the offline copy. Each project
 * change applies to everyone using this server, so each can be undone or is
 * harmless.
 */
export function SettingsSheet() {
  const s = useMission(useShallow((m) => ({ open: m.settingsOpen, setOpen: m.setSettingsOpen })))
  const { tab, setTab } = useSettingsTab()
  const session = useSession((x) => x.session)
  const live = Boolean(session && !session.offline)
  const baseId = useId()

  return (
    <Sheet open={s.open} onClose={() => s.setOpen(false)} title="Settings" size="xl">
      <div className="flex min-h-full flex-col md:flex-row">
        <Tabs
          label="Settings groups"
          baseId={baseId}
          tabs={TABS}
          value={tab}
          onChange={setTab}
          className="shrink-0 gap-1 border-b border-line px-3 py-2 md:w-52 md:border-r md:border-b-0 md:px-3 md:py-4"
        />
        <div
          role="tabpanel"
          id={`${baseId}-panel`}
          aria-labelledby={`${baseId}-${tab}`}
          tabIndex={0}
          className="min-w-0 grow p-5 outline-none md:p-6"
        >
          <FlatRows.Provider value={true}>
            <div key={tab} className="flex flex-col gap-6">
              {tab === 'project' && <ProjectTab open={s.open} live={live} onSignedOut={() => s.setOpen(false)} />}
              {tab === 'parameters' &&
                (live ? (
                  <ParametersPanel enabled={s.open} />
                ) : (
                  <NeedsLive what="Parameters" />
                ))}
              {tab === 'risk' && <RiskScalePanel enabled={s.open} />}
              {tab === 'sources' && <DataSources enabled={s.open} live={live} />}
              {tab === 'appearance' && <AppearanceTab onGuide={() => s.setOpen(false)} />}
              {tab === 'offline' && <OfflineTab />}
            </div>
          </FlatRows.Provider>
        </div>
      </div>
    </Sheet>
  )
}

function NeedsLive({ what }: { what: string }) {
  return (
    <p className="text-body leading-6 text-ink-2">
      {what} are read from the live service. This copy runs from saved answers, so they cannot be shown or changed here.
    </p>
  )
}

function AppearanceTab({ onGuide }: { onGuide: () => void }) {
  const s = useMission(
    useShallow((m) => ({
      theme: m.theme,
      setTheme: m.setTheme,
      motion: m.motion,
      setMotion: m.setMotion,
      shortcuts: m.shortcuts,
      setShortcuts: m.setShortcuts,
    })),
  )
  const goGuide = useGuide((g) => g.go)
  const navigate = useNavigate()
  return (
    <>
      <Setting label="Theme" note="Both pass contrast checks. Light is best for printing and projectors.">
        <Segmented
          label="Appearance"
          value={s.theme}
          onChange={s.setTheme}
          options={[
            { value: 'dark', label: 'Dark' },
            { value: 'light', label: 'Light' },
          ]}
        />
      </Setting>
      <Setting label="Motion" note="With motion reduced, nothing moves: pages change at once and every moving view has a still version.">
        <Segmented
          label="Motion"
          value={s.motion}
          onChange={s.setMotion}
          options={[
            { value: 'full', label: 'Full' },
            { value: 'reduced', label: 'Reduced' },
          ]}
        />
      </Setting>
      <Setting
        label="Keyboard shortcuts"
        note="Single keys: T shows a chart as a table, [ and ] move the time, Space plays. Turn them off if you use voice control or they get in the way."
      >
        <Segmented
          label="Keyboard shortcuts"
          value={s.shortcuts ? 'on' : 'off'}
          onChange={(v) => s.setShortcuts(v === 'on')}
          options={[
            { value: 'on', label: 'On' },
            { value: 'off', label: 'Off' },
          ]}
        />
      </Setting>
      <Setting label="Guide" note="A short tour along the bottom of the screen, one feature at a time. It can be skipped at any step.">
        <div>
          <Button
            onClick={() => {
              goGuide(0)
              onGuide()
              navigate('/missions')
            }}
          >
            Start the guide from the beginning
          </Button>
        </div>
      </Setting>
    </>
  )
}

/** What the offline copy is, whether it is in use now, and when it was taken. */
function OfflineTab() {
  const saved = useSnapshotActive()
  const captured = snapshotCapturedAt()
  const when = captured ? isoDateWords(captured) : null
  return (
    <>
      <div className="flex flex-col gap-2">
        <h3 className="text-title font-semibold text-ink">{saved ? 'In use now' : 'Not in use'}</h3>
        <p className="text-body leading-6 text-ink-2">
          {DATA_MODE === 'snapshot'
            ? `This copy runs only from saved answers${when ? `, taken ${when}` : ''}. Nothing reaches a server: live readings do not change, and nothing can be entered or saved.`
            : saved
              ? `The live service is not answering, so pages show its answers saved${when ? ` ${when}` : ''}. They go back to live answers on their own when it answers again.`
              : `Pages come from the live service. If it stops answering, they fall back to its saved answers${when ? ` from ${when}` : ''} and say so at the top of the page.`}
        </p>
      </div>
      <Setting
        label="What it holds"
        note="The answers are kept exactly as the service gave them, with their sources and ages. A page that was not saved says so instead of showing anything."
      >
        <p className="text-body leading-6 text-ink-2">
          The missions and landing sites, and every step of the missions the guide visits, as the service answered them
          when the copy was taken.
        </p>
      </Setting>
    </>
  )
}

function ProjectTab({ open, live, onSignedOut }: { open: boolean; live: boolean; onSignedOut: () => void }) {
  const session = useSession((x) => x.session)
  const signOut = useSession((x) => x.signOut)
  const navigate = useNavigate()
  // Asked for when the sheet opens, so the panel always shows the present state.
  const q = useProjectSettings(live && open)

  return (
    <>
      {session && (
        <div className="pw-card pw-card-quiet flex flex-wrap items-center justify-between gap-3 p-4">
          <p className="text-small leading-5 text-ink-2">
            Signed in as <span className="font-semibold text-ink">{session.user?.name ?? session.roleName}</span>
            {session.user?.team ? `, ${session.user.team}` : ''}
            {session.user ? `, ${session.roleName.toLowerCase()}` : ''}
            {session.offline ? ' (offline copy)' : ''}. The session ends {dateTimeWords(session.expiresAt)}.
          </p>
          <Button
            size="sm"
            onClick={() => {
              signOut()
              onSignedOut()
              navigate('/')
            }}
          >
            Sign out
          </Button>
        </div>
      )}
      {live && <People />}
      {!live ? (
        <p className="text-body leading-6 text-ink-2">
          This copy runs from saved answers, so the project controls need the live service.
        </p>
      ) : q.isPending ? (
        <div className="flex flex-col gap-3" aria-busy="true">
          <span className="sr-only" role="status">
            Loading the project settings
          </span>
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-12 w-48" />
          <Skeleton className="h-5 w-64" />
        </div>
      ) : q.error ? (
        <Problem error={q.error as ApiError} />
      ) : (
        <ProjectControls data={q.data} />
      )}
    </>
  )
}

function ProjectControls({ data }: { data: SettingsDTO }) {
  const act = useSettingsActions()
  const setSettingsOpen = useMission((m) => m.setSettingsOpen)
  const openRunLog = useMission((m) => m.openRunLog)
  const { ai, system } = data
  const c = system.counts
  const working = (ok: boolean, yes = 'Working', no = 'Not working') => (ok ? yes : no)
  const lastError =
    act.saveAi.error ?? act.resetAi.error ?? act.retryModels.error ?? act.clearCache.error ?? act.clearRunLog.error

  const save = (enabled: boolean, models: string[], light: string[]) =>
    act.saveAi.mutate({ enabled, models, models_light: light })
  const ids = (m: ModelStateDTO[]) => m.map((x) => x.model)

  return (
    <div className="flex flex-col gap-6">
      <Setting
        label="AI assistant"
        note={
          ai.configured
            ? 'When it is off, every AI panel answers with a summary built only from the measurements.'
            : 'No AI key is set on the server, so the AI panels answer from the measurements whatever this says.'
        }
      >
        <Segmented
          label="AI assistant"
          value={ai.enabled ? 'on' : 'off'}
          onChange={(v) => save(v === 'on', ids(ai.models), ids(ai.models_light))}
          options={[
            { value: 'on', label: 'On' },
            { value: 'off', label: 'Off' },
          ]}
        />
      </Setting>

      <Setting label="AI activity log" note={`${c.agent_runs} runs: every question, the steps taken and the numbers checked.`}>
        <div>
          <Button
            size="sm"
            onClick={() => {
              setSettingsOpen(false)
              openRunLog(null)
            }}
          >
            Open the log
          </Button>
        </div>
      </Setting>

      <details className="group flex flex-col gap-3">
        <summary className="inline-flex h-12 cursor-pointer items-center text-control font-semibold text-ink">
          Model order
        </summary>
        <div className="flex flex-col gap-5">
          <ModelOrder
            title="Models, tried in this order"
            note="If a model has used up its quota or is unavailable, the next one answers. Move a model to change the order."
            models={ai.models}
            onMove={(order) => save(ai.enabled, order, ids(ai.models_light))}
            busy={act.saveAi.isPending}
          />
          <ModelOrder
            title="Models for short descriptions"
            note="“What is it like at this site?” writes one paragraph, so the lightest models go first."
            models={ai.models_light}
            onMove={(order) => save(ai.enabled, ids(ai.models), order)}
            busy={act.saveAi.isPending}
          />
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => act.retryModels.mutate()} disabled={act.retryModels.isPending}>
              Try skipped models now
            </Button>
            <Button size="sm" onClick={() => act.resetAi.mutate()} disabled={!ai.customised || act.resetAi.isPending}>
              Reset the AI settings
            </Button>
          </div>
        </div>
      </details>

      <details className="group flex flex-col gap-3">
        <summary className="inline-flex h-12 cursor-pointer items-center text-control font-semibold text-ink">
          System status
        </summary>
        <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1.5 text-small leading-5">
          <Row term="Moon terrain map" value={working(system.moon_data, 'Loaded', 'Missing')} />
          <Row term="Sun and Earth positions" value={working(system.sun_earth_data, 'Loaded', 'Missing')} />
          <Row term="Database" value={working(system.database)} />
          <Row
            term="Saved results (cache)"
            value={c.cached_results === null ? 'Not in use' : `${c.cached_results} saved`}
          />
          <Row term="Missions" value={String(c.missions)} />
          <Row term="Candidate sites" value={String(c.candidate_sites)} />
          <Row term="Mission landing spots" value={String(c.mission_targets)} />
        </dl>
      </details>

      <Setting label="Clean up" note="These apply to everyone using this server.">
        <div className="flex flex-col gap-4">
          <ConfirmAction
            label="Clear saved results"
            explain={`Removes ${c.cached_results ?? 0} saved results. Each one is worked out again the next time it is needed, so pages load more slowly for a while.`}
            confirm="Clear them"
            disabled={!c.cached_results}
            busy={act.clearCache.isPending}
            onConfirm={() => act.clearCache.mutate()}
            done={act.clearCache.data?.message}
          />
          <ConfirmAction
            label="Clear the AI activity log"
            explain={`Deletes all ${c.agent_runs} AI runs from the log for everyone. This can’t be undone.`}
            confirm="Delete them"
            disabled={!c.agent_runs}
            busy={act.clearRunLog.isPending}
            onConfirm={() => act.clearRunLog.mutate()}
            done={act.clearRunLog.data?.message}
          />
        </div>
      </Setting>

      {lastError && <Problem error={lastError as ApiError} />}
    </div>
  )
}

function ModelOrder({
  title,
  note,
  models,
  onMove,
  busy,
}: {
  title: string
  note: string
  models: ModelStateDTO[]
  onMove: (order: string[]) => void
  busy: boolean
}) {
  const move = (i: number, by: -1 | 1) => {
    const order = models.map((m) => m.model)
    const [m] = order.splice(i, 1)
    order.splice(i + by, 0, m)
    onMove(order)
  }
  return (
    <div className="flex flex-col gap-2">
      <h4 className="text-control font-semibold text-ink">{title}</h4>
      <p className="text-caption leading-caption text-ink-3">{note}</p>
      <ol className="flex flex-col divide-y divide-line border-y border-line">
        {models.map((m, i) => (
          <li key={m.model} className="flex items-center gap-2 py-1">
            <span className="w-5 shrink-0 text-right font-mono text-caption text-ink-3">{i + 1}</span>
            <span className="flex min-w-0 grow flex-col">
              <span className="truncate font-mono text-small text-ink">{m.model}</span>
              <span className="text-caption leading-caption text-ink-3">
                {m.ready
                  ? 'Ready'
                  : `Skipped until ${m.skipped_until ? dateTimeWords(Date.parse(m.skipped_until)) : 'later'}${m.why ? `: ${m.why}` : ''}`}
              </span>
            </span>
            <button
              type="button"
              disabled={busy || i === 0}
              onClick={() => move(i, -1)}
              aria-label={`Move ${m.model} up`}
              className="pw-press inline-flex size-12 shrink-0 items-center justify-center rounded-pill text-ink-2 hover:bg-inset hover:text-ink disabled:text-line-strong"
            >
              ↑
            </button>
            <button
              type="button"
              disabled={busy || i === models.length - 1}
              onClick={() => move(i, 1)}
              aria-label={`Move ${m.model} down`}
              className="pw-press inline-flex size-12 shrink-0 items-center justify-center rounded-pill text-ink-2 hover:bg-inset hover:text-ink disabled:text-line-strong"
            >
              ↓
            </button>
          </li>
        ))}
      </ol>
    </div>
  )
}

/** A destructive action behind a second, explicit step. */
function ConfirmAction({
  label,
  explain,
  confirm,
  disabled,
  busy,
  onConfirm,
  done,
}: {
  label: string
  explain: string
  confirm: string
  disabled: boolean
  busy: boolean
  onConfirm: () => void
  done?: string
}) {
  const [asking, setAsking] = useState(false)
  return (
    <div className="flex flex-col gap-2">
      {!asking ? (
        <div>
          <Button size="sm" disabled={disabled || busy} onClick={() => setAsking(true)}>
            {label}
          </Button>
        </div>
      ) : (
        <div role="group" aria-label={label} className="flex flex-col gap-2 border-l-[3px] border-line-strong pl-3">
          <p className="text-small leading-5 text-ink">{explain}</p>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="primary"
              onClick={() => {
                setAsking(false)
                onConfirm()
              }}
            >
              {confirm}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setAsking(false)}>
              Keep them
            </Button>
          </div>
        </div>
      )}
      <p aria-live="polite" className="text-caption leading-caption text-ink-2">
        {done ?? ''}
      </p>
    </div>
  )
}

function Problem({ error }: { error: ApiError }) {
  return (
    <div role="alert" className="flex flex-col gap-1 border-l-[3px] border-line-strong pl-3">
      <p className="text-small font-semibold text-ink">{error.title}</p>
      <p className="text-caption leading-caption text-ink-2">{error.detail}</p>
      {error.stillWorks && <p className="text-caption leading-caption text-ink-3">{error.stillWorks}</p>}
    </div>
  )
}

function Row({ term, value }: { term: string; value: string }) {
  return (
    <>
      <dt className="text-ink-2">{term}</dt>
      <dd className="text-right font-semibold text-ink tabular-nums">{value}</dd>
    </>
  )
}

function Setting({ label, note, children }: { label: string; note: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <h4 className="text-control font-semibold text-ink">{label}</h4>
      {children}
      <p className="text-caption leading-caption text-ink-3">{note}</p>
    </div>
  )
}
