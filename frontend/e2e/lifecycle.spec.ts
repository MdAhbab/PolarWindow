import { expect, test, type Page } from '@playwright/test'
import { expectNoSeriousAxe, returningVisitor, watchConsole } from './helpers'
import { fulfillWrite, serveLifecycleFixtures } from './lifecycleFixtures'

/**
 * The mission hub and its six steps, against the contract's fixtures
 * (docs/lifecycle-api.md, src/lib/api/__fixtures__/lifecycle): these tests
 * check the screens' shape and behaviour, not live numbers, because the
 * backend's lifecycle endpoints are being built alongside them. Everything
 * else (the mission record, sign-in, Landing) is the live API.
 */

const QUESTIONS: Record<string, string> = {
  ready: 'What is ready, and what is holding it up?',
  launch: 'When and from where can it launch?',
  trip: 'What does the lander go through on the way?',
  contact: 'How often can the lander talk to Earth?',
  return: 'Where do the booster and any capsule come down, and what is the sea like there?',
}

const steps = (page: Page) => page.getByRole('navigation', { name: 'Mission sections' })

test('the hub (contract fixtures): six steps in order, one open at a time, each deep-linkable', async ({ page, context }) => {
  await returningVisitor(context)
  await serveLifecycleFixtures(context)
  const problems = watchConsole(page)
  await page.goto('/missions/im-2/ready')
  const links = steps(page).getByRole('link')
  await expect(links).toHaveCount(6)
  await expect(links).toHaveText([/^1\s*Ready/, /^2\s*Launch/, /^3\s*Trip/, /^4\s*Landing/, /^5\s*Contact/, /^6\s*Return/])
  // Each step says its state in words, and its summary.
  await expect(links.nth(0)).toHaveAccessibleName(/Ready.*Available.*5 of 9 items ready; 1 blocked/)
  await expect(links.nth(4)).toHaveAccessibleName(/Contact.*Working it out/)
  await expect(links.nth(5)).toHaveAccessibleName(/Return.*Does not apply/)
  await expect(links.nth(0)).toHaveAttribute('aria-current', 'page')
  await expect(page).toHaveTitle(/^IM-2, Ready · POLAR WINDOW$/)

  // By keyboard: focus stays on the step that was pressed, like a tab.
  await links.nth(2).focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/missions\/im-2\/trip$/)
  await expect(links.nth(2)).toHaveAttribute('aria-current', 'page')
  await expect(links.nth(2)).toBeFocused()
  await expect(page.getByRole('heading', { name: QUESTIONS.trip })).toBeVisible()

  // /missions/:id opens on Landing, the page this product began with.
  await page.goto('/missions/im-2')
  await expect(links.nth(3)).toHaveAttribute('aria-current', 'page')
  await expect(page.locator('[data-guide="sun-earth"]')).toBeVisible()
  // An unknown step goes back to the mission.
  await page.goto('/missions/im-2/nothing')
  await expect(page).toHaveURL(/\/missions\/im-2$/)
  expect(problems).toEqual([])
})

for (const section of Object.keys(QUESTIONS)) {
  test(`${section} (contract fixtures): the question, one answer, up to four numbers, a chart with its table twin`, async ({
    page,
    context,
  }) => {
    await returningVisitor(context)
    await serveLifecycleFixtures(context)
    const problems = watchConsole(page)
    await page.goto(`/missions/im-2/${section}`)
    const main = page.locator('main')
    await expect(page.getByRole('heading', { name: QUESTIONS[section] })).toBeVisible()
    await expect(page.locator('[data-guide="section-answer"]')).not.toBeEmpty()
    // No verdicts anywhere (invariant 9).
    await expect(main).not.toContainText(/\b(go\/no-go|no-go|safe to|% ready|risk score)\b/i)
    const table = page.getByRole('button', { name: 'Read the chart as a table' })
    await expect(table).toHaveCount(1)
    await table.click()
    await expect(page.getByRole('button', { name: 'Hide the table' })).toHaveAttribute('aria-expanded', 'true')
    await expect(main.getByRole('table').first()).toBeVisible()
    await expectNoSeriousAxe(page, `/missions/im-2/${section} with its table open`)
    expect(problems).toEqual([])
  })
}

test('each number says its margin, or why it has none (contract fixtures)', async ({ page, context }) => {
  await returningVisitor(context)
  await serveLifecycleFixtures(context)
  await page.goto('/missions/im-2/contact')
  // A relay is a range, "if it flies as planned".
  const relay = page.locator('div.border.bg-panel', { hasText: 'Through a relay' }).first()
  await expect(relay).toContainText('12–31')
  await expect(relay).toContainText('if it flies as planned')
  await expect(relay).toContainText('12 to 31 hours')
  // The caveat that changes what the numbers mean stays on screen.
  await expect(page.locator('main')).toContainText('Line of sight only')

  await page.goto('/missions/im-2/trip')
  const shadow = page.locator('div.border.bg-panel', { hasText: 'Longest time in shadow' }).first()
  await expect(shadow).toContainText('±0.02')
  // Where it comes from opens from the label (invariant 10).
  await shadow.getByRole('button', { name: /Longest time in shadow/ }).click()
  await expect(shadow).toContainText('Worked out by POLAR WINDOW')
})

test('launch (contract fixtures): choosing an opportunity sets the four numbers; the weather is per rule and per system', async ({
  page,
  context,
}) => {
  await returningVisitor(context)
  await serveLifecycleFixtures(context)
  await page.goto('/missions/im-2/launch')
  const opp = page.getByRole('button', { name: /^28 February 2025, 01:56 UTC ±4 min, from LC-39A/ })
  await opp.click()
  await expect(opp).toHaveAttribute('aria-pressed', 'true')
  await expect(page.locator('main')).toContainText('Numbers for the opportunity on 28 February 2025, 01:56 UTC')
  await page.locator('summary', { hasText: 'Weather rules for this opportunity' }).click()
  const rules = page.getByRole('table').filter({ hasText: 'model runs that break it' })
  await expect(rules).toContainText('3 of 31 model runs')
  await expect(rules).toContainText('Models disagree')
  await expect(rules).toContainText('not yet checked against observations')
  await expect(rules).toContainText('Observation only: no forecast number')
  await expectNoSeriousAxe(page, '/missions/im-2/launch with the weather open')
})

test('working it out (contract fixtures): a 202 shows its progress and what still works', async ({ page, context }) => {
  await returningVisitor(context)
  await serveLifecycleFixtures(context, { working: ['trip'] })
  await page.goto('/missions/im-2/trip')
  await expect(page.getByText('Working it out', { exact: true }).last()).toBeVisible()
  await expect(page.getByRole('progressbar', { name: 'Progress' })).toHaveAttribute('aria-valuenow', '35')
  await expect(page.locator('main')).toContainText('The other sections and the landing numbers are unaffected')
  // The numbers' labels are there, with no values yet.
  await expect(page.locator('main')).toContainText('Longest time in shadow')
  await expectNoSeriousAxe(page, 'trip while working it out')
})

test('needs input and no data (contract fixtures): each says what is missing and what still works', async ({ page, context }) => {
  await returningVisitor(context)
  await serveLifecycleFixtures(context, { swap: { 'ready.json': 'ready-empty.json', 'trip.json': 'trip-none.json' } })
  await page.goto('/missions/im-2/ready')
  await expect(page.getByText('No readiness items entered yet')).toBeVisible()
  await expect(page.locator('main')).toContainText('What still works')
  await page.goto('/missions/im-2/trip')
  await expect(page.getByText('No trip to show yet')).toBeVisible()
  await expect(page.locator('main')).toContainText('No trajectory is published for this mission')
})

test('a readiness change asks for a name, needs evidence, and shows its history (contract fixtures)', async ({ page, context }) => {
  await returningVisitor(context)
  await serveLifecycleFixtures(context)
  // The named sign-in and the write, answered as the contract says they will be.
  let signedInAs: unknown = null
  let patched: unknown = null
  await context.route(/localhost:8000\/api\/v1\/auth\/demo$/, async (route) => {
    if (route.request().method() !== 'POST') return route.fallback()
    signedInAs = route.request().postDataJSON()
    const real = await route.fetch()
    const body = await real.json()
    await route.fulfill({ response: real, json: { ...body, user: { id: 7, name: 'Nadia Karim', team: 'Payloads' } } })
  })
  await context.route(/localhost:8000\/api\/v1\/ready\/items\/item-mapp$/, async (route) => {
    if (route.request().method() === 'PATCH') patched = route.request().postDataJSON()
    await fulfillWrite(route, { id: 'item-mapp' })
  })
  await page.goto('/missions/im-2/ready')
  await page.getByRole('button', { name: 'Change MAPP rover' }).first().click()
  const sheet = page.getByRole('dialog', { name: 'Change: MAPP rover' })
  await expect(sheet).toContainText('Every change is recorded with your name.')
  await expect(sheet.getByLabel('New state')).toHaveValue('test_passed')
  await sheet.getByRole('button', { name: 'Save' }).click()
  await expect(sheet).toContainText('Enter your name')
  await sheet.getByLabel('Your name').fill('Nadia Karim')
  await sheet.getByLabel('Team (optional)').fill('Payloads')
  await sheet.getByRole('button', { name: 'Save' }).click()
  await expect(sheet).toContainText('Link the evidence')
  await sheet.getByLabel('Evidence link').fill('https://example.org/vibration-report.pdf')
  await sheet.getByRole('button', { name: 'Save' }).click()
  await expect(sheet.getByText('Saved.')).toBeVisible()
  expect(signedInAs).toEqual({ name: 'Nadia Karim', team: 'Payloads' })
  expect(patched).toMatchObject({ state: 'test_passed', evidence_url: 'https://example.org/vibration-report.pdf' })
  await expect(sheet).toContainText('Change history')
  await expect(sheet).toContainText('state: in test → blocked')
  await expectNoSeriousAxe(page, 'the readiness change sheet')
  await page.keyboard.press('Escape')
  await expect(sheet).toBeHidden()
})

test('settings (contract fixtures): data sources with their age, the risk scale, people', async ({ page, context }) => {
  await returningVisitor(context)
  await serveLifecycleFixtures(context)
  await page.goto('/missions')
  await page.getByRole('button', { name: 'Settings' }).click()
  const sheet = page.getByRole('dialog', { name: 'Settings' })
  await sheet.locator('summary', { hasText: 'Data sources' }).click()
  await expect(sheet).toContainText('4 products from 4 providers: 2 working, 1 out of date, 1 failing')
  await expect(sheet).toContainText('DSN Now')
  await expect(sheet).toContainText('Failing')
  await expect(sheet).toContainText('data from 11 h ago')
  await sheet.locator('summary', { hasText: 'Risk scale' }).click()
  await expect(sheet).toContainText('never multiplied into a score')
  await sheet.locator('summary', { hasText: 'People' }).click()
  await expect(sheet.getByLabel('Your name')).toBeVisible()
  await expectNoSeriousAxe(page, 'settings with the project rows open')
})

test('a phone (contract fixtures): the six steps fit as three by two, with no sideways scroll', async ({ page, context }) => {
  await returningVisitor(context)
  await serveLifecycleFixtures(context)
  await page.setViewportSize({ width: 375, height: 812 })
  for (const s of ['ready', 'launch', 'trip', 'contact', 'return']) {
    await page.goto(`/missions/im-2/${s}`)
    await expect(page.getByRole('heading', { name: QUESTIONS[s] })).toBeVisible()
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    expect(overflow, `${s} scrolls sideways`).toBeLessThanOrEqual(0)
    const boxes = await steps(page).getByRole('link').evaluateAll((els) => els.map((e) => e.getBoundingClientRect().height))
    for (const h of boxes) expect(h).toBeGreaterThanOrEqual(48)
    await expectNoSeriousAxe(page, `/missions/im-2/${s} at 375 px`)
  }
})
