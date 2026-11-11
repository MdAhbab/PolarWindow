import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMission } from '../lib/api/queries'
import { PROJECTS_OFFLINE, ProjectApiError, useDeleteProject, useIntake, useProjectOptions, useSaveProject, useStoredRadio } from '../lib/api/projects'
import type { IntakeDTO } from '../lib/api/experience.types'
import { Button, Panel, pillClass } from '../components/ui'
import { PageHeader } from '../components/Page'
import { EmptyState, ProblemPanel, Skeleton } from '../components/States'
import { WriteProblem, useNamedWriter } from '../components/lifecycle/Forms'
import { toast } from '../components/Toast'
import { FileDrop, IntakeSummary, ReadingProgress, fileProblem, type ReadStage } from '../components/project/FileDrop'
import { ProjectForm } from '../components/project/ProjectForm'
import {
  GROUPS,
  GROUP_KEYS,
  emptyForm,
  formFromMission,
  keyForServerPath,
  mergeIntake,
  toRequest,
  validate,
  type Errors,
  type GroupKey,
  type ProjectFormState,
  type Provenance,
} from '../components/project/formModel'

/**
 * Add a mission by hand or from a file (docs/experience-plan.md, "Projects").
 * One form, two ways in. Nothing is saved until Save, and a field the file did
 * not give stays empty.
 */
export function ProjectNewScreen() {
  return <ProjectPage />
}

export function ProjectEditScreen() {
  const { id } = useParams()
  return <ProjectPage id={id} />
}

interface Doc {
  form: ProjectFormState
  prov: Provenance
}

function ProjectPage({ id }: { id?: string }) {
  if (PROJECTS_OFFLINE) {
    return (
      <div className="pw-page flex flex-col gap-6 pt-6 pb-10 lg:pt-10">
        <PageHeader crumbs={[{ label: 'Missions', to: '/missions' }, { label: 'New project' }]} title="New project" />
        <Panel>
          <EmptyState
            title="Adding a project needs the live service"
            detail="This copy runs from saved answers, so it can show the missions but cannot take a new one. Open the dashboard with the service running to add a project."
          />
        </Panel>
      </div>
    )
  }
  return id ? <EditLoader id={id} /> : <ProjectEditor />
}

function EditLoader({ id }: { id: string }) {
  const mission = useMission(id)
  const radio = useStoredRadio(id)
  if (mission.isPending || (radio.isPending && !radio.error)) {
    return (
      <div className="pw-page flex flex-col gap-4 pt-10" aria-busy="true">
        <Skeleton className="h-10 w-72 rounded-control" />
        <Skeleton className="h-64 w-full rounded-card" />
      </div>
    )
  }
  if (!mission.error && mission.data?.origin === 'project' && radio.error) {
    // Saving without the stored radio figures would erase them, so the form waits for them.
    return (
      <div className="pw-page pt-10">
        <ProblemPanel error={radio.error} fallbackTitle="Cannot load this project’s radio figures" onRetry={() => void radio.refetch()} />
      </div>
    )
  }
  if (mission.error || !mission.data) {
    return (
      <div className="pw-page pt-10">
        <ProblemPanel error={mission.error} fallbackTitle="Cannot load this project" onRetry={() => void mission.refetch()} />
      </div>
    )
  }
  if (mission.data.origin !== 'project') {
    return (
      <div className="pw-page pt-10">
        <Panel>
          <EmptyState
            title="This is a catalogue record"
            detail="Catalogue missions are compiled from published sources and cannot be edited here. You can add your own project instead."
          />
          <div className="flex justify-center pb-8">
            <Link to={`/missions/${id}`} className={pillClass('secondary')}>
              Back to the mission
            </Link>
          </div>
        </Panel>
      </div>
    )
  }
  return <ProjectEditor id={id} initial={formFromMission(mission.data, radio.data)} name={mission.data.name} />
}

const stageOf = (p: ReturnType<typeof useIntake>['progress']): ReadStage => (p?.stage === 'sending' ? 'sending' : 'reading')

function ProjectEditor({ id, initial, name }: { id?: string; initial?: ProjectFormState; name?: string }) {
  const navigate = useNavigate()
  const options = useProjectOptions()
  const save = useSaveProject()
  const del = useDeleteProject()
  const intake = useIntake()
  const writer = useNamedWriter()

  const start = useMemo(() => initial ?? emptyForm(), [initial])
  const [doc, setDocState] = useState<Doc>({ form: start, prov: {} })
  const docRef = useRef(doc)
  const setDoc = useCallback((d: Doc) => {
    docRef.current = d
    setDocState(d)
  }, [])
  const baseline = useRef(JSON.stringify(toRequest(start)))
  const [readings, setReadings] = useState<IntakeDTO[]>([])
  const [conflict, setConflict] = useState<{ intake: IntakeDTO; groups: GroupKey[] } | null>(null)
  const [fileProblems, setFileProblems] = useState<string[]>([])
  const [reading, setReading] = useState<{ name: string; filling: boolean } | null>(null)
  const [held, setHeld] = useState<File[]>([])
  const [showErrors, setShowErrors] = useState(false)
  const [serverErrors, setServerErrors] = useState<Errors>({})
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [leaveTo, setLeaveTo] = useState<string | null>(null)

  const { form, prov } = doc
  const dirty = JSON.stringify(toRequest(form)) !== baseline.current
  const found = useMemo(() => validate(form), [form])
  const errors: Errors = showErrors ? { ...found, ...serverErrors } : serverErrors

  // Leaving with unsaved work: the browser's own question for a closed tab, ours for a link in the page.
  useEffect(() => {
    if (!dirty) return
    const before = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      e.returnValue = ''
    }
    const click = (e: MouseEvent) => {
      const a = (e.target as Element | null)?.closest?.('a[href]') as HTMLAnchorElement | null
      if (!a || a.target === '_blank' || e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey) return
      const url = new URL(a.href, window.location.href)
      if (url.origin !== window.location.origin) return
      e.preventDefault()
      e.stopPropagation()
      setLeaveTo(url.pathname + url.search + url.hash)
    }
    window.addEventListener('beforeunload', before)
    document.addEventListener('click', click, true)
    return () => {
      window.removeEventListener('beforeunload', before)
      document.removeEventListener('click', click, true)
    }
  }, [dirty])

  const change = (patch: Partial<ProjectFormState>) => {
    const cur = docRef.current
    const keys = Object.keys(patch)
    const nextProv = { ...cur.prov }
    for (const g of GROUP_KEYS) if (GROUPS[g].fields.some((f) => keys.includes(f))) delete nextProv[g]
    setDoc({ form: { ...cur.form, ...patch }, prov: nextProv })
    if (Object.keys(serverErrors).length) {
      const drop = { ...serverErrors }
      for (const k of keys) delete drop[k]
      setServerErrors(drop)
    }
  }

  const readFiles = async (files: File[]) => {
    const problems: string[] = []
    const ok: File[] = []
    for (const f of files) {
      const p = fileProblem(f, options.data)
      if (p) problems.push(p)
      else ok.push(f)
    }
    setFileProblems(problems)
    if (!ok.length) return
    if (!(await writer.ensure())) {
      setHeld((h) => [...h, ...ok])
      return
    }
    setHeld([])
    for (const f of ok) {
      setReading({ name: f.name, filling: false })
      try {
        const r = await intake.mutateAsync(f)
        setReading({ name: f.name, filling: true })
        const m = mergeIntake(docRef.current.form, docRef.current.prov, r)
        setDoc({ form: m.form, prov: m.provenance })
        setReadings((x) => [...x, r])
        if (m.conflicts.length) setConflict({ intake: r, groups: m.conflicts })
      } catch (e) {
        const t = (e as { title?: string; detail?: string }) ?? {}
        setFileProblems((x) => [...x, `${f.name}: ${t.title ?? 'it could not be read'}. ${t.detail ?? ''}`.trim()])
      }
    }
    setReading(null)
  }

  const acceptConflict = () => {
    if (!conflict) return
    const m = mergeIntake(docRef.current.form, docRef.current.prov, conflict.intake, true)
    setDoc({ form: m.form, prov: m.provenance })
    setConflict(null)
  }

  const submit = async () => {
    setShowErrors(true)
    const bad = validate(docRef.current.form)
    if (Object.keys(bad).length) {
      requestAnimationFrame(() => document.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus())
      return
    }
    if (!(await writer.ensure())) return
    setServerErrors({})
    try {
      const saved = await save.mutateAsync({ id, body: toRequest(docRef.current.form) })
      baseline.current = JSON.stringify(toRequest(docRef.current.form))
      setLeaveTo(null)
      toast(id ? 'Project saved.' : 'Project added.')
      if (saved.site_job) toast('Its skyline is being built. The activity tray shows the progress.')
      // After the guard has lifted for this render.
      setTimeout(() => navigate(`/missions/${saved.mission.id}`), 0)
    } catch (e) {
      if (e instanceof ProjectApiError) {
        const next: Errors = {}
        for (const [path, msg] of Object.entries(e.fields)) next[keyForServerPath(path)] = msg
        setServerErrors(next)
        if (Object.keys(next).length) requestAnimationFrame(() => document.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus())
      }
    }
  }

  const remove = async () => {
    if (!id || !(await writer.ensure())) return
    try {
      await del.mutateAsync(id)
      baseline.current = JSON.stringify(toRequest(docRef.current.form))
      toast('Project deleted.')
      setTimeout(() => navigate('/missions'), 0)
    } catch {
      /* shown below */
    }
  }

  const cancel = () => (dirty ? setLeaveTo(id ? `/missions/${id}` : '/missions') : navigate(id ? `/missions/${id}` : '/missions'))
  const modelOff = options.data && !options.data.model_reading
  const shownError = save.error && Object.keys(serverErrors).length === 0 ? save.error : null
  const errorCount = Object.keys(errors).length

  return (
    <div className="pw-page flex flex-col gap-6 pt-6 pb-4 lg:pt-10">
      <PageHeader
        crumbs={[{ label: 'Missions', to: '/missions' }, ...(id ? [{ label: name ?? 'Project', to: `/missions/${id}` }] : []), { label: id ? 'Edit' : 'New project' }]}
        title={id ? `Edit ${name ?? 'project'}` : 'New project'}
        lede="Add your own mission by dropping a file or filling in the form. It is listed with the others, and opens the same six steps."
      />

      <div className="flex max-w-3xl flex-col gap-1.5 border-l-[3px] border-line-strong pl-3 text-small leading-5 text-ink-2">
        <p>Only the name is needed. A field you leave empty stays unknown, and a step that is missing its data will offer a scenario instead.</p>
        {modelOff && <p>No AI model is set up here, so a file is read by rules: only dates, names and coordinates are looked for.</p>}
      </div>

      <Panel className="flex flex-col gap-4 p-5 sm:p-6">
        <div className="flex max-w-2xl flex-col gap-3 text-small leading-5 text-ink-2">{writer.fields}</div>
      </Panel>

      <section aria-labelledby="drop-h" className="flex flex-col gap-3">
        <h2 id="drop-h" className="text-title-lg font-semibold tracking-title text-ink">
          Start from a file
        </h2>
        {reading ? (
          <ReadingProgress filename={reading.name} stage={reading.filling ? 'filling' : stageOf(intake.progress)} fraction={intake.progress?.fraction ?? null} />
        ) : (
          <FileDrop options={options.data} busy={false} onFiles={(f) => void readFiles(f)} heldCount={held.length} />
        )}
        {held.length > 0 && !reading && (
          <div>
            <Button onClick={() => void readFiles(held)}>Read the waiting {held.length === 1 ? 'file' : 'files'}</Button>
          </div>
        )}
        {fileProblems.length > 0 && (
          <ul role="alert" className="flex flex-col gap-1 border-l-[3px] border-alert pl-3 text-small leading-5 text-ink">
            {fileProblems.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        )}
        {conflict && (
          <div role="alert" className="flex flex-col gap-3 rounded-card border border-line-strong bg-tray p-4">
            <p className="text-small leading-5 text-ink">
              {conflict.intake.filename} gives a different value for {conflict.groups.map((g) => GROUPS[g].label.toLowerCase()).join(', ')}. The form keeps what it
              has.
            </p>
            <div className="flex flex-wrap gap-3">
              <Button onClick={acceptConflict}>Use the file’s values</Button>
              <Button variant="ghost" onClick={() => setConflict(null)}>
                Keep mine
              </Button>
            </div>
          </div>
        )}
        <IntakeSummary readings={readings} />
      </section>

      {options.error && <ProblemPanel error={options.error} fallbackTitle="The choices could not be loaded" onRetry={() => void options.refetch()} />}

      <form
        noValidate
        aria-label="Project"
        onSubmit={(e) => {
          e.preventDefault()
          void submit()
        }}
        className="flex flex-col gap-5"
      >
        <h2 className="text-title-lg font-semibold tracking-title text-ink">{id ? 'The project' : 'Or fill it in'}</h2>
        {showErrors && errorCount > 0 && (
          <p role="alert" className="text-small font-semibold text-alert">
            <span aria-hidden="true">▲ </span>
            {errorCount === 1 ? 'One field needs a look before this can be saved.' : `${errorCount} fields need a look before this can be saved.`}
          </p>
        )}
        <ProjectForm form={form} options={options.data} errors={errors} provenance={prov} onChange={change} />

        {shownError && <WriteProblem error={shownError} />}
        {del.error && <WriteProblem error={del.error} />}

        {id && (
          <div className="flex flex-col gap-3 rounded-card border border-line p-4">
            <h2 className="text-control font-semibold text-ink">Delete this project</h2>
            {!confirmDelete ? (
              <div>
                <Button variant="secondary" onClick={() => setConfirmDelete(true)}>
                  Delete…
                </Button>
              </div>
            ) : (
              <div role="alertdialog" aria-label="Confirm delete" className="flex flex-col gap-3">
                <p className="text-small leading-5 text-ink-2">Delete {name ?? 'this project'}? It leaves the list and cannot be brought back. Catalogue missions are not affected.</p>
                <div className="flex flex-wrap gap-3">
                  <Button variant="primary" disabled={del.isPending} onClick={() => void remove()}>
                    {del.isPending ? 'Deleting…' : 'Yes, delete it'}
                  </Button>
                  <Button variant="ghost" onClick={() => setConfirmDelete(false)}>
                    Keep it
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}

        <div className="sticky bottom-[calc(5rem+env(safe-area-inset-bottom)+var(--pw-guide-h,0px))] z-20 -mx-4 flex flex-col gap-3 border-t border-line bg-glass px-4 py-3 backdrop-blur lg:bottom-0 lg:mx-0 lg:rounded-card lg:border lg:px-5">
          {leaveTo && (
            <div role="alertdialog" aria-label="Leave without saving" className="flex flex-wrap items-center gap-3">
              <p className="text-small font-semibold text-ink">Leave without saving? What you entered here will be lost.</p>
              <Button onClick={() => setLeaveTo(null)}>Stay</Button>
              <Button
                variant="ghost"
                onClick={() => {
                  baseline.current = JSON.stringify(toRequest(docRef.current.form))
                  const to = leaveTo
                  setLeaveTo(null)
                  setTimeout(() => navigate(to), 0)
                }}
              >
                Leave
              </Button>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" variant="primary" disabled={save.isPending || writer.offline}>
              {save.isPending ? 'Saving…' : id ? 'Save changes' : 'Save project'}
            </Button>
            <Button onClick={cancel}>Cancel</Button>
            {dirty && <span className="text-caption text-ink-3">Not saved yet</span>}
          </div>
        </div>
      </form>
    </div>
  )
}
