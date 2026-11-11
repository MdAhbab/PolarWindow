// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { renderApp } from '../test/render'
import { useSession } from '../lib/session'
import options from '../lib/api/__fixtures__/experience/project.options.json'
import saved from '../lib/api/__fixtures__/experience/project.saved.json'
import modelRead from '../lib/api/__fixtures__/experience/intake.model.json'
import rulesRead from '../lib/api/__fixtures__/experience/intake.rules.json'

const reply = vi.hoisted(() => ({ next: null as unknown }))
vi.mock('../lib/api/projects', async (orig) => {
  const real = await orig<typeof import('../lib/api/projects')>()
  return {
    ...real,
    useIntake: () => ({ mutateAsync: async () => reply.next, progress: null }),
  }
})
import { ProjectNewScreen } from './ProjectNewScreen'

const posts: { url: string; body: Record<string, unknown> }[] = []

beforeEach(() => {
  posts.length = 0
  useSession.setState({
    session: { token: 't', roleName: 'Project manager', expiresAt: Date.now() + 1e7, offline: false, user: { id: 1, name: 'Ada', team: null } },
  })
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input))
      const json = (status: number, body: unknown) =>
        Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } }))
      if (url.pathname.endsWith('/projects/options')) return json(200, options)
      if (url.pathname.endsWith('/projects') && init?.method === 'POST') {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>
        posts.push({ url: url.pathname, body })
        if (body.name === 'Bad dates')
          return json(422, {
            detail: { title: 'The dates do not fit', detail: 'Check them.', errors: [{ field: 'landing.date', message: 'Landing is before launch.' }] },
          })
        return json(201, saved)
      }
      return new Promise(() => {})
    }),
  )
})
afterEach(cleanup)

const shell = () =>
  renderApp(
    <Routes>
      <Route path="/projects/new" element={<ProjectNewScreen />} />
      <Route path="/missions/:id" element={<p>hub</p>} />
    </Routes>,
    { route: '/projects/new' },
  )

const dropIn = async (container: HTMLElement, file: File) => {
  const input = container.querySelector('input[type=file]') as HTMLInputElement
  await act(async () => {
    fireEvent.change(input, { target: { files: [file] } })
  })
}

describe('adding a project', () => {
  it('needs only a name, says what an unknown field does, and saves to the new hub', async () => {
    shell()
    expect(screen.getByText(/a step that is missing its data will offer a scenario/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Save project' }))
    const name = await screen.findByLabelText(/Mission name/)
    expect(name.getAttribute('aria-invalid')).toBe('true')
    expect(name.getAttribute('aria-describedby')).toBeTruthy()
    fireEvent.change(name, { target: { value: 'Aurora 1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save project' }))
    expect(await screen.findByText('hub')).toBeTruthy()
    expect(posts[0].body).toMatchObject({ name: 'Aurora 1', launch: null, target: null, payloads: [] })
  })

  it('shows a server refusal on the field it names', async () => {
    shell()
    fireEvent.change(await screen.findByLabelText(/Mission name/), { target: { value: 'Bad dates' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save project' }))
    expect(await screen.findByText('Landing is before launch.')).toBeTruthy()
  })

  it('fills the form from a model reading and shows the evidence on focus', async () => {
    reply.next = modelRead
    const { container } = shell()
    await screen.findByLabelText(/Mission name/)
    await dropIn(container, new File(['x'], 'brief.pdf', { type: 'application/pdf' }))
    await waitFor(() => expect((screen.getByLabelText(/Mission name/) as HTMLInputElement).value).toBe('Aurora 1'))
    expect(screen.getByText('brief.pdf: 7 of 9 fields filled')).toBeTruthy()
    expect(screen.getByText(/Page 5 is a scanned image/)).toBeTruthy()
    const marks = screen.getAllByRole('button', { name: 'From the file' })
    expect(screen.getAllByRole('button', { name: 'Worked out' }).length).toBe(1)
    await act(async () => marks[0].focus())
    expect(marks[0].getAttribute('aria-expanded')).toBe('true')
    const panel = document.getElementById(marks[0].getAttribute('aria-controls')!)!
    expect(within(panel).getByText('Mission Aurora 1 will deliver')).toBeTruthy()
    expect((screen.getAllByLabelText('Launch').find((e) => e.tagName === 'INPUT') as HTMLInputElement).value).toBe('')
  })

  it('says plainly that rules read the file when no model is set up, and keeps what is already filled', async () => {
    reply.next = rulesRead
    const { container } = shell()
    fireEvent.change(await screen.findByLabelText(/Mission name/), { target: { value: 'Mine' } })
    await dropIn(container, new File(['x'], 'dates.txt', { type: 'text/plain' }))
    expect(await screen.findByText(/No AI model is set up, so this file was read by rules/)).toBeTruthy()
    expect((screen.getByLabelText(/Mission name/) as HTMLInputElement).value).toBe('Mine')
    expect(screen.getByText(/gives a different value for mission name/)).toBeTruthy()
  })

  it('refuses a file of the wrong kind before sending it', async () => {
    const { container } = shell()
    await screen.findByLabelText(/Mission name/)
    await waitFor(() => expect(container.querySelector('input[type=file]')!.getAttribute('accept')).toContain('.pdf'))
    await dropIn(container, new File(['x'], 'pic.png', { type: 'image/png' }))
    expect(await screen.findByText(/pic.png is not a kind of file/)).toBeTruthy()
  })
})
