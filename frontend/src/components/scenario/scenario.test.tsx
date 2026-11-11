// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { Routes, Route } from 'react-router-dom'
import { renderApp } from '../../test/render'
import { scenarioApi } from '../../lib/api/scenarios'
import { useSession } from '../../lib/session'
import type { InterpretedDTO, ScenarioDTO, ScenarioGapsDTO } from '../../lib/api/experience.types'
import type { ContactDTO, LaunchCalendarDTO, SectionDTO } from '../../lib/api/lifecycle'
import gapsFixture from '../../lib/api/__fixtures__/experience/gaps.json'
import rulesFixture from '../../lib/api/__fixtures__/experience/interpreted-rules.json'
import modelFixture from '../../lib/api/__fixtures__/experience/interpreted-model.json'
import queuedFixture from '../../lib/api/__fixtures__/experience/scenario-queued.json'
import runningFixture from '../../lib/api/__fixtures__/experience/scenario-running.json'
import doneFixture from '../../lib/api/__fixtures__/experience/scenario-done.json'
import failedFixture from '../../lib/api/__fixtures__/experience/scenario-failed.json'
import { ScenarioEntry } from './ScenarioEntry'
import { ScenarioBuilder } from './ScenarioBuilder'
import { ScenarioGate } from './ScenarioGate'
import { ScenarioBand } from './ScenarioBand'
import { ScenarioProgress } from './ScenarioProgress'
import { useActiveScenario } from './store'
import { contactAnswer } from '../../screens/sections/ContactSection'

const gaps = gapsFixture as unknown as ScenarioGapsDTO
const done = doneFixture as unknown as ScenarioDTO

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  useActiveScenario.setState({ active: {} })
  useSession.setState({ session: null })
})

const signedIn = () =>
  useSession.setState({
    session: { token: 't', roleName: 'pm', expiresAt: Date.now() + 1e7, offline: false, user: { id: 1, name: 'Ada Lovelace', team: null } },
  })

describe('the dead end', () => {
  it('names what is missing and offers one action and the presets', async () => {
    vi.spyOn(scenarioApi, 'gaps').mockResolvedValue(gaps)
    renderApp(<ScenarioEntry missionId="im-3" section="launch" />, { route: '/missions/im-3/launch' })
    const link = await screen.findByRole('link', { name: /Explore a scenario/ })
    expect(link.getAttribute('href')).toContain('scenario=new')
    expect(screen.getByText(/The vehicle is not published/)).toBeTruthy()
    const preset = screen.getByRole('link', { name: /Most likely: Falcon 9/ })
    expect(preset.getAttribute('href')).toContain('scenario=sc-preset-1')
  })
})

describe('the builder', () => {
  it('reads a prompt back (rules) and lays it in the form with bases', async () => {
    signedIn()
    vi.spyOn(scenarioApi, 'gaps').mockResolvedValue(gaps)
    vi.spyOn(scenarioApi, 'interpret').mockResolvedValue(rulesFixture as unknown as InterpretedDTO)
    renderApp(<ScenarioBuilder missionId="im-3" section="launch" />, { route: '/missions/im-3/launch?scenario=new' })
    const box = await screen.findByLabelText('Say what to assume')
    fireEvent.change(box, { target: { value: 'ten days' } })
    fireEvent.click(screen.getByRole('button', { name: 'Read it' }))
    expect(await screen.findByText(/No AI model is set up/)).toBeTruthy()
    expect(screen.getByText(/was not recognised/)).toBeTruthy()
    expect(screen.getByText(/will open at once/)).toBeTruthy()
    // Every value shows its basis as words.
    const tags = document.querySelectorAll('[data-basis]')
    expect([...tags].map((t) => t.getAttribute('data-basis'))).toEqual(expect.arrayContaining(['you', 'default', 'live']))
    // A model reading says so differently.
    expect(modelFixture.method).toBe('model')
  })

  it('starts a scenario with only what the person set', async () => {
    signedIn()
    vi.spyOn(scenarioApi, 'gaps').mockResolvedValue(gaps)
    const start = vi.spyOn(scenarioApi, 'start').mockResolvedValue(queuedFixture as unknown as ScenarioDTO)
    renderApp(
      <Routes>
        <Route path="/missions/:id/launch" element={<ScenarioBuilder missionId="im-3" section="launch" />} />
      </Routes>,
      { route: '/missions/im-3/launch?scenario=new' },
    )
    await screen.findByLabelText('Say what to assume')
    // The pad has no default, so the step cannot be worked out until it is given.
    const work = screen.getByRole('button', { name: 'Work it out' })
    expect((work as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText(/Still needed for Launch: launch pad/)).toBeTruthy()
    // Changing the landing date makes it "You"; reset returns it to the resolved one.
    const row = document.querySelector('[data-field="landing_date"]') as HTMLElement
    fireEvent.change(within(row).getByLabelText('Landing date'), { target: { value: '2028-01-05' } })
    expect(row.querySelector('[data-basis]')?.getAttribute('data-basis')).toBe('you')
    fireEvent.click(within(row).getByRole('button', { name: /Reset to 15 November 2027/ }))
    expect(row.querySelector('[data-basis]')?.getAttribute('data-basis')).toBe('live')
    expect(start).not.toHaveBeenCalled()
  })
})

describe('progress', () => {
  it('shows the phases, the real fraction and the other pages being free', () => {
    renderApp(<ScenarioProgress scenario={runningFixture as unknown as ScenarioDTO} />)
    expect(screen.getByRole('progressbar', { name: 'Scenario progress' }).getAttribute('aria-valuenow')).toBe('40')
    expect(screen.getByText('Checking live sources')).toBeTruthy()
    expect(screen.getByText(/other pages are free to use/)).toBeTruthy()
    expect(document.querySelectorAll('[data-state]').length).toBe(5)
  })
})

describe('the answer', () => {
  const gate = (route: string, scenario: ScenarioDTO) => {
    vi.spyOn(scenarioApi, 'one').mockResolvedValue(scenario)
    vi.spyOn(scenarioApi, 'list').mockResolvedValue({ items: [] })
    return renderApp(
      <Routes>
        <Route
          path="/missions/:id/contact"
          element={
            <ScenarioGate<ContactDTO>
              missionId="im-3"
              section="contact"
              question="How often can the lander talk to Earth?"
              record={<p>the record</p>}
              pick={(r) => r.contact as SectionDTO<ContactDTO> | undefined}
            >
              {({ data }) => <p data-testid="answer">{contactAnswer(data)}</p>}
            </ScenarioGate>
          }
        />
      </Routes>,
      { route },
    )
  }

  it('draws the record with no scenario in the address', () => {
    gate('/missions/im-3/contact', done)
    expect(screen.getByText('the record')).toBeTruthy()
  })

  it('draws a finished scenario under the band, labelled Scenario, with its assumptions', async () => {
    gate('/missions/im-3/contact?scenario=sc-1', done)
    expect(await screen.findByTestId('answer')).toBeTruthy()
    expect(screen.getByRole('complementary', { name: 'Scenario' })).toBeTruthy()
    expect(screen.getByText(/Worked out from assumptions, not from the mission’s record/)).toBeTruthy()
    expect(screen.getByRole('heading', { level: 2 }).textContent).toMatch(/^Scenario · /)
    expect(screen.getByRole('link', { name: 'Edit assumptions' }).getAttribute('href')).toContain('edit=sc-1')
    expect(screen.getByRole('link', { name: 'Leave the scenario' }).getAttribute('href')).not.toContain('scenario=')
    expect(document.title.startsWith('Scenario:')).toBe(true)
  })

  it('shows progress while it runs and the error when it failed', async () => {
    gate('/missions/im-3/contact?scenario=sc-1', runningFixture as unknown as ScenarioDTO)
    expect(await screen.findByRole('progressbar', { name: 'Scenario progress' })).toBeTruthy()
    cleanup()
    gate('/missions/im-3/contact?scenario=sc-1', failedFixture as unknown as ScenarioDTO)
    expect(await screen.findByText(/no day that meets the landing rule/)).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Change the assumptions' })).toBeTruthy()
  })

  it('says why a section was left out', async () => {
    gate('/missions/im-3/contact?scenario=sc-1', { ...done, results: { launch: done.results?.launch } })
    expect(await screen.findByText(/Contact was left out of this scenario/)).toBeTruthy()
  })

  it('restores the scenario when a link dropped it, and leaving clears it', async () => {
    useActiveScenario.getState().remember('im-3', 'sc-1')
    gate('/missions/im-3/contact', done)
    expect(await screen.findByTestId('answer')).toBeTruthy()
    fireEvent.click(screen.getByRole('link', { name: 'Leave the scenario' }))
    await waitFor(() => expect(screen.getByText('the record')).toBeTruthy())
    expect(useActiveScenario.getState().active['im-3']).toBeUndefined()
  })
})

describe('the band', () => {
  it('collapses the assumptions to a count', () => {
    vi.spyOn(scenarioApi, 'list').mockResolvedValue({ items: [] })
    renderApp(<ScenarioBand scenario={done} />)
    expect(screen.getByText(/4 · each with where it came from/)).toBeTruthy()
    expect(launchTypeCheck(done)).toBe(true)
  })
})

function launchTypeCheck(s: ScenarioDTO) {
  return (s.results?.launch as SectionDTO<LaunchCalendarDTO>).data.opportunities.length > 0
}
