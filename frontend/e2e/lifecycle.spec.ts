import { expect, test, type Page } from '@playwright/test'
import { API, expectNoSeriousAxe, openRow, returningVisitor, watchConsole } from './helpers'
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

test('team weather limits (contract fixtures): the form starts from the limits as entered, with their notes, and sends every one again', async ({
  page,
  context,
}) => {
  await returningVisitor(context)
  await serveLifecycleFixtures(context)
  let put: unknown = null
  await context.route(/localhost:8000\/api\/v1\/auth\/demo$/, async (route) => {
    if (route.request().method() !== 'POST') return route.fallback()
    const real = await route.fetch()
    const body = await real.json()
    await route.fulfill({ response: real, json: { ...body, user: { id: 7, name: 'Nadia Karim', team: 'Launch' } } })
  })
  await context.route(/localhost:8000\/api\/v1\/vehicles\/falcon-9\/limits$/, async (route) => {
    // The read-back comes from the fixture; the save is caught here.
    if (route.request().method() === 'GET') return route.fallback()
    if (route.request().method() === 'PUT') put = route.request().postDataJSON()
    await fulfillWrite(route, { vehicle_id: 'falcon-9', limits: [] })
  })
  await page.goto('/missions/im-2/launch')
  const row = page.locator('details').filter({ has: page.locator('summary', { hasText: 'Team weather limits' }) })
  await row.locator('summary').click()
  await expect(row.locator('summary')).toContainText('1 entered by the team, 1 not published')
  await expect(row).toContainText('The limit is not published; the team can enter the one it is given.')
  await expect(row).toContainText('Team’s note: As given by the range weather officer for this campaign.')
  await row.getByRole('button', { name: 'Enter the team’s limits' }).click()
  const sheet = page.getByRole('dialog', { name: 'Team weather limits' })
  // The published limits are not offered.
  await expect(sheet.getByRole('group', { name: /Sustained wind at 162 ft/ })).toHaveCount(0)
  // The entered one starts as entered, in a unit its rule takes, with its note.
  const tops = sheet.getByRole('group', { name: /cumulus/i })
  await expect(tops.getByLabel('Limit')).toHaveValue('10000')
  await expect(tops.getByLabel('Unit')).toHaveValue('ft')
  await expect(tops.getByLabel('Unit').locator('option')).toHaveText(['ft', 'm'])
  await expect(tops.getByLabel('Note (optional)')).toHaveValue('As given by the range weather officer for this campaign.')
  await expect(tops).toContainText('Entered by Nadia Karim')
  // A rule with no published unit asks for one.
  const shear = sheet.getByRole('group', { name: /upper-level conditions containing wind shear/ })
  await shear.getByLabel('Limit').fill('25')
  await sheet.getByRole('button', { name: 'Save' }).click()
  await expect(sheet).toContainText('Enter your name')
  await sheet.getByLabel('Your name').fill('Nadia Karim')
  await sheet.getByRole('button', { name: 'Save' }).click()
  await expect(sheet).toContainText('The unit the limit is given in.')
  await shear.getByLabel('Unit').fill('kt')
  await shear.getByLabel('Note (optional)').fill('From the launch provider.')
  await sheet.getByRole('button', { name: 'Save' }).click()
  await expect(sheet.getByText('Saved.')).toBeVisible()
  // The service replaces the vehicle's list: the entered limits go again with their notes, the one for a
  // rule not on this range's list too.
  expect(put).toEqual({
    limits: [
      { rule_id: 'upper-shear', value: 25, unit: 'kt', note: 'From the launch provider.' },
      { rule_id: 'cumulus-tops', value: 10000, unit: 'ft', note: 'As given by the range weather officer for this campaign.' },
      { rule_id: 'wr-upper-shear', value: 30, unit: 'kt', note: 'Vandenberg campaign, from the launch provider.' },
    ],
  })
  await expectNoSeriousAxe(page, 'the team weather limits sheet')
})

test('team weather limits (contract fixtures): a vehicle the service does not know says so and offers no save', async ({ page, context }) => {
  await returningVisitor(context)
  await serveLifecycleFixtures(context)
  await context.route(/localhost:8000\/api\/v1\/auth\/demo$/, async (route) => {
    if (route.request().method() !== 'POST') return route.fallback()
    const real = await route.fetch()
    const body = await real.json()
    await route.fulfill({ response: real, json: { ...body, user: { id: 7, name: 'Nadia Karim', team: 'Launch' } } })
  })
  await context.route(/localhost:8000\/api\/v1\/vehicles\/falcon-9\/limits$/, (route) =>
    route.fulfill({
      status: 404,
      json: {
        detail: {
          type: 'https://polar-window.dev/errors/vehicle-not-found',
          title: 'That launch vehicle isn’t in the list',
          status: 404,
          detail: "'falcon-9' is not a launch vehicle in this dataset.",
          ui: { still_works: 'Every other vehicle and mission is available.', retryable: false, action: 'Back to the mission' },
        },
      },
    }),
  )
  await page.goto('/missions/im-2/launch')
  const row = page.locator('details').filter({ has: page.locator('summary', { hasText: 'Team weather limits' }) })
  await row.locator('summary').click()
  await row.getByRole('button', { name: 'Enter the team’s limits' }).click()
  const sheet = page.getByRole('dialog', { name: 'Team weather limits' })
  await expect(sheet).toContainText('This launch vehicle is not in the service’s list, so no limits can be entered for it.')
  await expect(sheet.getByLabel('Limit', { exact: true })).toHaveCount(0)
})

test('old live data (contract fixtures): a degraded service names the old feeds under the steps, quietly, and opens the data sources', async ({ page, context }) => {
  await returningVisitor(context)
  await serveLifecycleFixtures(context)
  await context.route(/localhost:8000\/api\/v1\/healthz$/, async (route) => {
    const real = await route.fetch()
    const body = await real.json()
    await route.fulfill({ response: real, json: { ...body, status: 'degraded', feeds: { ok: 2, stale: 1, failing: 1 } } })
  })
  await page.goto('/missions/im-2/contact')
  const note = page.getByText(/^Some live data is older than usual/)
  await expect(note).toHaveText(
    'Some live data is older than usual: NOAA NDBC and DSN Now. Each number from them says how old it is, or why it is missing. See the data sources',
  )
  await page.setViewportSize({ width: 375, height: 812 })
  await expectNoSeriousAxe(page, 'the old live data note at 375 px')
  expect(await page.evaluate(() => document.documentElement.scrollWidth), 'the hub scrolls sideways at 375 px').toBeLessThanOrEqual(375)
  await page.getByRole('button', { name: 'See the data sources' }).click()
  await expect(page.getByRole('dialog')).toContainText('Data sources')
})

test('official launch forecast (contract fixtures): a save shows the forecast as stored, not the one before; taking it back shows the one before again', async ({ page, context }) => {
  await returningVisitor(context)
  await serveLifecycleFixtures(context)
  let put: Record<string, unknown> | null = null
  let deletes = 0
  const before = { id: 8, probability_pct: 10, concerns: ['Cumulus cloud rule', 'Thick cloud layers'], pdf_url: 'https://www.patrick.spaceforce.mil/', entered_by: 'A. Rahman', entered_at: '2026-09-26T12:00:00Z' }
  await context.route(/localhost:8000\/api\/v1\/missions\/im-2\/launch\/official-forecast$/, async (route) => {
    const method = route.request().method()
    if (method === 'PUT') put = route.request().postDataJSON()
    if (method === 'DELETE') {
      deletes += 1
      return fulfillWrite(route, { removed_id: 9, official: before })
    }
    // The service answers with the forecast as stored; the weather fixture still carries the older one.
    await fulfillWrite(route, { id: 9, ...put, entered_by: 'Nadia Karim', entered_at: new Date().toISOString() })
  })
  await page.goto('/missions/im-2/launch')
  const summary = page.locator('summary', { hasText: 'Official launch forecast' })
  const row = page.locator('details').filter({ has: summary })
  await summary.click()
  await expect(summary).toContainText('10%, entered by A. Rahman')
  await row.getByRole('button', { name: 'Enter a newer forecast' }).click()
  const sheet = page.getByRole('dialog', { name: 'Official launch forecast' })
  await sheet.getByLabel('Your name').fill('Nadia Karim')
  await sheet.getByLabel('Chance the weather breaks a launch rule (%)').fill('150')
  // Not a web address: our own message shows beside the field, not the browser's bubble.
  await sheet.getByLabel('Link to the forecast PDF').fill('l-1.pdf')
  await sheet.getByRole('button', { name: 'Save' }).click()
  await expect(sheet).toContainText('A whole percent from 0 to 100.')
  await expect(sheet).toContainText('The web address of the forecast PDF.')
  expect(put).toBeNull()
  await sheet.getByLabel('Chance the weather breaks a launch rule (%)').fill('20')
  await sheet.getByLabel('Main concerns').fill('Cumulus cloud rule, surface wind')
  await sheet.getByLabel('Link to the forecast PDF').fill('https://example.test/l-1.pdf')
  await sheet.getByRole('button', { name: 'Save' }).click()
  await expect(sheet.getByText('Saved.')).toBeVisible()
  expect(put).toEqual({ probability_pct: 20, concerns: ['Cumulus cloud rule', 'surface wind'], pdf_url: 'https://example.test/l-1.pdf' })
  await sheet.getByRole('button', { name: 'Close' }).last().click()
  await expect(summary).toContainText('20%, entered by Nadia Karim')
  await expect(row).toContainText('20% chance the weather breaks a launch rule, in the official forecast; main concerns: cumulus cloud rule, surface wind.')
  await expect(row.getByRole('link', { name: /the forecast as issued \(example\.test\)/ })).toHaveAttribute('href', 'https://example.test/l-1.pdf')
  // Take it back: the sheet says which, and the one entered before it is shown again (the weather fixture still carries it).
  await row.getByRole('button', { name: 'Take back this forecast' }).click()
  const back = page.getByRole('dialog', { name: 'Take back the official forecast' })
  await expect(back).toContainText('This takes back the 20% forecast entered by Nadia Karim')
  await expect(back).toContainText('Recorded as Nadia Karim')
  await expectNoSeriousAxe(page, 'the take-back sheet')
  await back.getByRole('button', { name: 'Take back', exact: true }).click()
  await expect(back).toBeHidden()
  expect(deletes).toBe(1)
  await expect(summary).toContainText('10%, entered by A. Rahman')
  await expect(row).toContainText('Taken back. The forecast entered before it is shown again.')
})

test('space weather now (contract fixtures): the readings in a sentence, each with its age, NOAA’s outlook as issued and DONKI’s newest events', async ({
  page,
  context,
}) => {
  await returningVisitor(context)
  await serveLifecycleFixtures(context)
  await page.goto('/missions/im-2/launch')
  const summary = page.locator('summary', { hasText: 'Space weather now' })
  const row = page.locator('details').filter({ has: summary })
  await expect(summary).toContainText('Kp 1, 2 alerts')
  await summary.click()
  await expect(row).toContainText('Now: Kp 1, protons above 10 MeV at 0.23 pfu, X-ray flares class B4.7, solar wind at 456 km/s; 2 alerts in the last 24 hours.')
  // Each reading says how old it is.
  for (const label of ['Geomagnetic activity (Kp, 0 to 9)', 'Protons above 100 MeV', 'Magnetic field from the Sun, north–south (Bz)', 'X-ray flares (class)']) {
    await expect(row.locator('dt', { hasText: label }).locator('xpath=following-sibling::dd[1]')).toContainText(/ · as of .+ ago$/)
  }
  await expect(row).toContainText('ALERT: Electron 2MeV Integral Flux exceeded 1,000pfu')
  await expect(row).toContainText('NOAA’s outlook for Sep 26-Sep 28 2026, issued 26 September 2026, 12:30 UTC: a 1%, 1% and 1% chance of a radiation storm (S1 or greater), day by day; the largest Kp expected is 4.')
  await row.locator('summary', { hasText: 'NOAA’s forecast as issued' }).click()
  await expect(row.locator('pre')).toContainText(':Product: 3-Day Forecast')
  // DONKI: the three newest of each kind, each with its record.
  await expect(row).toContainText('Newest events on the Sun, last 30 days (NASA DONKI)')
  await expect(row.getByRole('link', { name: 'record' })).toHaveCount(3 + 3 + 2)
  await expect(row).toContainText('26 September 2026, 15:24 UTC, 449 km/s; no Earth arrival estimated')
  await expect(row).toContainText('C3.3, peak 19 September 2026, 18:17 UTC')
  await expect(row).toContainText('Doses along a trip are in the Trip section')
  await expectNoSeriousAxe(page, 'space weather now, open (dark)')
  // The other theme, and a phone: nothing runs off the side.
  await page.evaluate(() => localStorage.setItem('pw-prefs', JSON.stringify({ theme: 'light', motion: 'full', shortcuts: true })))
  await page.setViewportSize({ width: 375, height: 812 })
  await page.reload()
  await openRow(page, 'Space weather now')
  await page.locator('summary', { hasText: 'NOAA’s forecast as issued' }).click()
  await expectNoSeriousAxe(page, 'space weather now, open (light, 375 px)')
  expect(await page.evaluate(() => document.documentElement.scrollWidth), 'space weather scrolls sideways at 375 px').toBeLessThanOrEqual(375)
})

test('team sea limits (contract fixtures): the form starts from what is entered, and sends both parts', async ({ page, context }) => {
  await returningVisitor(context)
  await serveLifecycleFixtures(context)
  let put: unknown = null
  await context.route(/localhost:8000\/api\/v1\/missions\/im-2\/return\/limits$/, async (route) => {
    if (route.request().method() === 'PUT') put = route.request().postDataJSON()
    await fulfillWrite(route, {})
  })
  await page.goto('/missions/im-2/return')
  const row = page.locator('details').filter({ has: page.locator('summary', { hasText: 'Team limits' }) })
  await row.locator('summary').click()
  await expect(row.locator('summary')).toContainText('entered by A. Rahman')
  await expect(row).toContainText('Booster landing zone: waves 2.5 m, wind 8 m/s.')
  await row.getByRole('button', { name: 'Enter the team’s limits' }).click()
  const sheet = page.getByRole('dialog', { name: 'Team sea limits' })
  const waves = sheet.getByLabel('Booster landing zone: highest waves (metres)')
  const wind = sheet.getByLabel('Booster landing zone: strongest wind (metres a second)')
  await expect(waves).toHaveValue('2.5')
  await expect(wind).toHaveValue('8')
  // No capsule returns: its fields are not offered.
  await expect(sheet.getByLabel(/Splashdown zone/)).toHaveCount(0)
  // The first change asks for a name to record it against.
  await sheet.getByLabel('Your name').fill('Nadia Karim')
  await waves.fill('-1')
  await sheet.getByRole('button', { name: 'Save' }).click()
  await expect(sheet).toContainText('A limit is a number above zero, or empty for none.')
  await expect(waves).toHaveAttribute('aria-invalid', 'true')
  await waves.fill('3')
  await wind.fill('')
  await sheet.getByRole('button', { name: 'Save' }).click()
  await expect(sheet.getByText('Saved.')).toBeVisible()
  // The service replaces both parts, so the capsule's (none entered) goes as it stands.
  expect(put).toEqual({ booster: { wave_height_m: 3, wind_m_s: null }, capsule: { wave_height_m: null, wind_m_s: null } })
  await expectNoSeriousAxe(page, 'the team sea limits sheet')
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

test('settings (contract fixtures): data sources with their age, the risk scale, parameters with their history, people', async ({
  page,
  context,
}) => {
  await returningVisitor(context)
  await serveLifecycleFixtures(context, { swap: { 'history.json': 'history-parameter.json' } })
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
  await expect(sheet).toContainText('No words are entered for the levels yet')
  await sheet.locator('summary', { hasText: 'Parameters' }).click()
  await expect(sheet.locator('summary', { hasText: 'Parameters' })).toContainText('1 of 4 entered')
  await expect(sheet.getByText('Not entered yet')).toHaveCount(3)
  const change = sheet.getByRole('button', { name: /^Change\s*for Battery limit/ })
  await change.click()
  await expect(change).toHaveAttribute('aria-expanded', 'true')
  await expect(sheet.getByLabel('Value, in hours')).toHaveValue('96')
  await expect(sheet).toContainText('120 h → 96 h')
  await expect(sheet).toContainText('Set to 120 h')
  await sheet.locator('summary', { hasText: 'People' }).click()
  await expect(sheet.getByLabel('Your name').first()).toBeVisible()
  await expectNoSeriousAxe(page, 'settings with the project rows open')
})

test('settings (live API): the parameters and the risk scale as the server has them', async ({ page, context }) => {
  await returningVisitor(context)
  await page.goto('/missions')
  await page.getByRole('button', { name: 'Settings' }).click()
  const sheet = page.getByRole('dialog', { name: 'Settings' })
  const params = sheet.locator('summary', { hasText: 'Parameters' })
  await expect(params).toContainText(/\d of 4 entered/)
  await params.click()
  await expect(sheet).toContainText('Battery limit')
  await expect(sheet).toContainText('Lowest Sun height allowed at landing')
  await sheet.getByRole('button', { name: /for Planned days on the surface/ }).click()
  await expect(sheet.getByLabel('Value, in days')).toBeVisible()
  await expect(sheet).toContainText(/Change history/i)
  await sheet.locator('summary', { hasText: 'Risk scale' }).click()
  await expect(sheet.getByRole('link', { name: 'standards.nasa.gov' })).toBeVisible()
  await expectNoSeriousAxe(page, 'settings, live parameters and risk scale')
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

test('trip and contact (live API): the flown trip with its gaps in the data, and the dates contact covers', async ({ page, context }) => {
  test.setTimeout(120_000)
  await returningVisitor(context)
  const main = page.locator('main')
  // IM-1's reconstruction comes in separate stretches: the note says so and the key names the gaps.
  await page.goto('/missions/im-1/trip')
  // The first visit may answer 202 while the trip is worked out; the answer follows.
  await expect(page.locator('[data-guide="section-answer"]')).toContainText('The trip takes', { timeout: 90_000 })
  await expect(main).toContainText('(as flown)')
  // The answer speaks only for the hours the data covers.
  await expect(page.locator('[data-guide="section-answer"]')).toContainText(/In the [\d.]+ hours NASA’s reconstruction covers, /)
  await expect(main).toContainText('separate stretches')
  await expect(main).toContainText('No data')
  await page.getByRole('button', { name: 'Read the chart as a table' }).click()
  await expect(main.getByRole('table').first()).toContainText('No data')
  // One gap between each two stretches the service lists as covered, none guessed from the samples.
  const covered = (await (await page.request.get(`${API}/missions/im-1/trip`)).json()).data.covered as unknown[]
  expect(covered.length).toBeGreaterThan(1)
  await expect(main.getByRole('table').first().getByRole('row').filter({ hasText: 'No data' })).toHaveCount(covered.length - 1)
  await expectNoSeriousAxe(page, '/missions/im-1/trip (live) with its table open')

  // The flown trajectory downloads, one block per stretch the reconstruction covers.
  await page.locator('summary', { hasText: 'Download the trip' }).click()
  await expect(main).toContainText(/covers the trip in \d+ separate stretches, so the file has \d+ blocks/)
  const [csv] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('link', { name: 'Spreadsheet (CSV)' }).click(),
  ])
  expect(csv.suggestedFilename()).toBe('im-1-trip.csv')
  const oemLink = page.getByRole('link', { name: 'CCSDS orbit file (OEM)' })
  const oem = await page.request.get((await oemLink.getAttribute('href'))!)
  expect(oem.status()).toBe(200)
  const text = await oem.text()
  expect(text.startsWith('CCSDS_OEM_VERS = 2.0')).toBe(true)
  const blocks = Number((await main.textContent())!.match(/so the file has (\d+) blocks/)![1])
  expect(text.match(/^META_START/gm)?.length).toBe(blocks)

  // A mission that has not flown says why there is no trip, and offers nothing to download.
  await page.goto('/missions/griffin-1/trip')
  await expect(page.getByText('No trip to show yet')).toBeVisible({ timeout: 30_000 })
  await expect(page.locator('summary', { hasText: 'Download the trip' })).toHaveCount(0)

  await page.goto('/missions/im-2/contact')
  await expect(page.locator('[data-guide="section-answer"]')).toContainText('A ground station can hear it', { timeout: 90_000 })
  await expect(main).toContainText('Line of sight only')
})

test('launch (live API): a flown launch worked out again, and a planned mission’s calendar', async ({ page, context }) => {
  test.setTimeout(180_000)
  await returningVisitor(context)
  const main = page.locator('main')
  const answer = page.locator('[data-guide="section-answer"]')
  const openRow = async (title: string) => {
    const summary = page.locator('summary', { hasText: title })
    await summary.click()
    return page.locator('details').filter({ has: summary })
  }

  // IM-1 flew: its one launch, worked out again from NASA's reconstruction beside the published liftoff.
  await page.goto('/missions/im-1/launch')
  await expect(answer).toContainText('It launched on 15 Feb 2024', { timeout: 90_000 })
  await expect(answer).toContainText('as worked out again from NASA’s reconstruction of the flight')
  await expect(answer).toContainText('The published liftoff is 15 Feb 2024')
  await expect(main).toContainText('Numbers for the launch on 15 February 2024')
  await expect(main).toContainText('after the published liftoff')
  const flight = await openRow('The flight as launched')
  await expect(flight).toContainText('worked out again from NASA’s reconstruction')
  await expect(flight).toContainText("The climb's direction is not published")
  await expect(flight).toContainText('(published)')
  const rules = await openRow('Weather rules for this launch')
  await expect(rules.locator('summary')).toContainText('no forecast for this date')
  await expect(rules).toContainText('in the past')
  await expect(rules).toContainText('This launch is in the past; the forecasts made before it were not kept.')
  // Its launch is the one it flew: no dates to change.
  await expect(page.locator('summary', { hasText: 'Change the dates' })).toHaveCount(0)
  await openRow('Team weather limits')
  await openRow('Other launches from this range that day')
  await expectNoSeriousAxe(page, '/missions/im-1/launch (live) with its rows open')

  // Griffin-1 has not flown: a calendar worked back from its landing spot.
  await page.goto('/missions/griffin-1/launch')
  await expect(answer).toContainText(/\d+ launch opportunities from Launch Complex 39A between/, { timeout: 90_000 })
  await expect(answer).toContainText('The next is')
  const opps = page.getByRole('group', { name: 'Launch opportunities by day' }).getByRole('button')
  expect(await opps.count()).toBeGreaterThan(1)
  const second = opps.nth(1)
  await second.click()
  await expect(second).toHaveAttribute('aria-pressed', 'true')
  const name = (await second.getAttribute('aria-label'))!
  await expect(main).toContainText(`Numbers for the opportunity on ${name}`)
  const designed = await openRow('The flight for this opportunity')
  await expect(designed).toContainText('designed here from the pad and the landing')
  await expect(designed).toContainText('The landing rule allows a landing from')
  await expect(designed).toContainText('Assumed:')
  await page.getByRole('button', { name: 'Read the chart as a table' }).click()
  await expect(main.getByRole('table').first()).toContainText('Launch Complex 39A')
  const dates = await openRow('Change the dates')
  await expect(dates.locator('summary')).toContainText('the next 90 days')
  await dates.getByLabel('From (UTC)').fill('2027-01-01')
  await dates.getByLabel('To (UTC)').fill('2027-08-01')
  await dates.getByRole('button', { name: 'Show these dates' }).click()
  await expect(dates).toContainText('At most 180 days at once.')
  await expect(page).not.toHaveURL(/from=/)
  await expectNoSeriousAxe(page, '/missions/griffin-1/launch (live) with its table and rows open')
})

test('trip corrections and launch weather words (live API): Blue Ghost’s burns and budget, IM-1’s past years, Griffin-1’s weather notes', async ({
  page,
  context,
}) => {
  test.setTimeout(240_000)
  await returningVisitor(context)
  const main = page.locator('main')
  const answer = page.locator('[data-guide="section-answer"]')
  const row = (title: string) => page.locator('details').filter({ has: page.locator('summary', { hasText: title }) })

  // Blue Ghost: the burns in plain words, each one instant with why it has no margin, and what is not seen.
  await page.goto('/missions/blue-ghost-m1/trip')
  await expect(answer).toContainText('The trip takes', { timeout: 90_000 })
  await openRow(page, 'Burns')
  await expect(row('Burns')).toContainText('Leaving Earth for the Moon')
  await expect(row('Burns')).toContainText('Entering lunar orbit')
  await expect(row('Burns')).toContainText('One instant stands for the burn')
  await expect(row('Burns')).toContainText('Burns in lunar orbit are not listed')
  await expect(main).not.toContainText('TLI')
  // A budget for corrections under assumed errors, never a prediction; each size says its sample.
  await openRow(page, 'Corrections on the way')
  const budget = row('Corrections on the way')
  await expect(budget.locator('summary')).toContainText(/a budget: [\d.]+ m\/s in 99 of 100 runs/)
  await expect(budget).toContainText('not a prediction')
  await expect(budget).toContainText(/In 1,000 runs of the flight as planned/)
  await expect(budget).toContainText('allowing for the number of runs')
  await expect(budget.getByRole('table').getByRole('row')).toHaveCount(5)
  await expect(budget).toContainText('Every error here is assumed')
  await expectNoSeriousAxe(page, '/missions/blue-ghost-m1/trip (live) with its burns and corrections open')

  // IM-1: no burn found outside the gaps in the reconstruction, and a budget all the same.
  await page.goto('/missions/im-1/trip')
  await expect(answer).toContainText('The trip takes', { timeout: 90_000 })
  await expect(row('Burns').locator('summary')).toContainText('none listed')
  await expect(row('Corrections on the way').locator('summary')).toContainText('in 99 of 100 runs')

  // IM-1's launch: the weather row says first what it can show; the wind rule has its past years.
  await page.goto('/missions/im-1/launch')
  await expect(answer).toContainText('It launched on', { timeout: 90_000 })
  await openRow(page, 'Weather rules for this launch')
  const rules = row('Weather rules for this launch')
  await expect(rules).toContainText('This launch has flown', { timeout: 30_000 })
  await expect(rules).toContainText(/Past years \(2001-2024\): over the limit [\d.]+% of the time\./)
  // The lightning rules' past years are thunder heard at the pad, not a share over a limit.
  await expect(rules).toContainText(/Past years \(2019-2025\): thunder could be heard at the pad [\d.]+% of the time\./)
  await expect(rules).toContainText('lightning mappers')
  await expect(rules).toContainText('GOES lightning mapper')
  // The team's limits form starts from what is entered, read back from the service.
  await openRow(page, 'Team weather limits')
  await row('Team weather limits').getByRole('button', { name: 'Enter the team’s limits' }).click()
  const sheet = page.getByRole('dialog', { name: 'Team weather limits' })
  await expect(sheet.getByLabel('Note (optional)').first()).toBeVisible()
  await expect(sheet).not.toContainText('could not be read')
  await expectNoSeriousAxe(page, 'the team weather limits sheet (live)')
  await sheet.getByRole('button', { name: 'Close' }).first().click()

  // Griffin-1: each opportunity's weather row starts with its own note, as the service words it.
  await page.goto('/missions/griffin-1/launch')
  await expect(answer).toContainText('The next is', { timeout: 90_000 })
  const cal = (await (await page.request.get(`${API}/missions/griffin-1/launch`)).json()).data as {
    opportunities: { id: string; weather_note: string }[]
  }
  await openRow(page, 'Weather rules for this opportunity')
  await expect(row('Weather rules for this opportunity')).toContainText(cal.opportunities[0].weather_note, { timeout: 30_000 })
  const opps = page.getByRole('group', { name: 'Launch opportunities by day' }).getByRole('button')
  await opps.last().click()
  await expect(row('Weather rules for this opportunity')).toContainText(cal.opportunities.at(-1)!.weather_note, { timeout: 30_000 })
})

test('return (live API): where each flown booster came down, and a planned one not published yet', async ({ page, context }) => {
  test.setTimeout(90_000)
  await returningVisitor(context)
  const main = page.locator('main')
  const answer = page.locator('[data-guide="section-answer"]')
  const row = (title: string) => page.locator('details').filter({ has: page.locator('summary', { hasText: title }) })

  // IM-1's booster came back to land: no waves, the zone without a published size, and nothing to draw.
  await page.goto('/missions/im-1/return')
  await expect(answer).toContainText('The booster came back to Landing Zone 1', { timeout: 30_000 })
  await expect(answer).toContainText('This launch is in the past; the sea and wind then were not recorded.')
  await expect(answer).toContainText('Nothing comes back to Earth on this mission.')
  await expect(main).toContainText('On land: no waves to forecast.')
  await expect(page.getByRole('button', { name: 'Read the chart as a table' })).toHaveCount(0)
  await expect(row('Booster landing zone').locator('summary')).toContainText('near 28.5°N 80.5°W')
  await row('Booster landing zone').locator('summary').click()
  await expect(row('Booster landing zone')).toContainText('its size is not published')
  await expect(row('Team limits').locator('summary')).toContainText('none entered')
  await expect(main).not.toContainText(/\b0 m\b/)
  // The source is named once, in the sources row, not inside the answer; the answer's time is its newest input's, not the request's.
  await expect(answer).not.toContainText('Launch Library 2')
  await expect(main.getByText(/^Worked out /).first()).not.toHaveText('Worked out just now')
  await expect(row('Where does this come from?').locator('summary')).toContainText('1 source')
  await row('Where does this come from?').locator('summary').click()
  await expect(row('Where does this come from?')).toContainText('Launch Library 2 landing records')
  // The capsule model's check against OSIRIS-REx: the service's words, then the numbers and where they are from.
  const check = row('The capsule model, checked against a real landing')
  await expect(check.locator('summary')).toContainText(/[\d.]+ km from it; the limit is 10 km/)
  await check.locator('summary').click()
  await expect(check).toContainText('where the recovery team found it')
  await expect(check).toContainText('OSIRIS-REx sample return capsule')
  await expect(check.getByRole('link', { name: /naif\.jpl\.nasa\.gov/ })).toHaveCount(1)
  await expectNoSeriousAxe(page, '/missions/im-1/return (live) with rows open')

  // IM-2's landed on a droneship 700 km downrange, whose position is not published.
  await page.goto('/missions/im-2/return')
  await expect(answer).toContainText('A Shortfall of Gravitas', { timeout: 30_000 })
  await expect(answer).toContainText('700 km downrange')
  await expect(row('Booster landing zone').locator('summary')).toContainText('droneship, position not published')

  // Griffin-1 has not flown: the vehicle's practice and the flown landings, and the sea (GFS-Wave) where a
  // droneship would wait for the next opportunity, drawn with no limit beside it.
  await page.goto('/missions/griffin-1/return')
  await expect(answer).toContainText('decided for each launch and not yet published for this one', { timeout: 30_000 })
  await expect(answer).toContainText('IM-1 on Landing Zone 1')
  await expect(answer).toContainText(/Waves there are forecast at [\d.]+ m\. Wind there is forecast at [\d.]+ m\/s\./)
  await expect(main).toContainText('GFS-Wave, run of')
  // Each forecast number says how old it is, and the sources row lists GFS-Wave with its run and fetch.
  await expect(main.getByText(/^as of .+ ago$/)).toHaveCount(2)
  await expect(row('Where does this come from?').locator('summary')).toContainText('2 sources')
  await row('Where does this come from?').locator('summary').click()
  await expect(row('Where does this come from?')).toContainText(/GFS-Wave \(NOAA\)issued .+ · fetched .+ ago/)
  await row('Where does this come from?').locator('summary').click()
  await expect(row('Booster landing zone').locator('summary')).toContainText('not published yet')
  await row('Booster landing zone').locator('summary').click()
  await expect(row('Booster landing zone')).toContainText(/The sea is read near [\d.]+°N [\d.]+°W\./)
  await page.getByRole('button', { name: 'Read the chart as a table' }).click()
  await expect(main).toContainText(/Waves at the booster landing zone[\d.]+ m; no limit entered by the team/)
  await row('Team limits').locator('summary').click()
  await expect(row('Team limits')).toContainText('Booster landing zone: waves none entered, wind none entered.')
  await expectNoSeriousAxe(page, '/missions/griffin-1/return (live) with its limits open')

  // A cancelled delivery: the step's state, not an empty answer.
  await page.goto('/missions/apex-1/return')
  await expect(main).toContainText('Does not apply', { timeout: 30_000 })
  await expect(main).toContainText('This delivery was cancelled.')
})


test('official launch forecast (live API, writes): a signed-in save is stored, shown in the row, in its history and after a reload, then taken back', async ({
  page,
  context,
}) => {
  // The run takes its forecast back at the end, so the mission is left showing what it showed before (the history keeps both entries).
  test.setTimeout(90_000)
  await returningVisitor(context)
  const pct = 1 + Math.floor(Math.random() * 98)
  await page.goto('/missions/peregrine-m1/launch')
  await expect(page.locator('[data-guide="section-answer"]')).toContainText('It launched on', { timeout: 60_000 })
  const summary = page.locator('summary', { hasText: 'Official launch forecast' })
  await expect(summary).toContainText(/not entered|entered by/, { timeout: 60_000 })
  const shownBefore = ((await summary.textContent()) ?? '').replace('Official launch forecast', '').trim()
  await summary.click()
  await page.getByRole('button', { name: /^Enter (the official|a newer) forecast$/ }).click()
  const sheet = page.getByRole('dialog', { name: 'Official launch forecast' })
  const name = sheet.getByLabel('Your name')
  if (await name.isVisible()) await name.fill('End-to-end check')
  await sheet.getByLabel('Chance the weather breaks a launch rule (%)').fill(String(pct))
  await sheet.getByLabel('Main concerns').fill('End-to-end check')
  await sheet.getByLabel('Link to the forecast PDF').fill('https://example.test/end-to-end-check.pdf')
  await sheet.getByRole('button', { name: 'Save' }).click()
  await expect(sheet.getByText('Saved.')).toBeVisible()
  // Its history lists the change.
  await expect(sheet.getByText('Change history')).toBeVisible()
  await expect(sheet.locator('li').first()).toContainText('End-to-end check')
  await sheet.getByRole('button', { name: 'Close' }).last().click()
  await expect(summary).toContainText(`${pct}%, entered by End-to-end check`)
  // The weather answer carries the stored forecast.
  await page.reload()
  const again = page.locator('summary', { hasText: 'Official launch forecast' })
  await expect(again).toContainText(`${pct}%, entered by End-to-end check`, { timeout: 60_000 })
  // Take it back: the forecast shown before the run is shown again, here and after a reload, and the history says so.
  await again.click()
  await page.getByRole('button', { name: 'Take back this forecast' }).click()
  const back = page.getByRole('dialog', { name: 'Take back the official forecast' })
  await expect(back).toContainText(`This takes back the ${pct}% forecast entered by End-to-end check`)
  await back.getByRole('button', { name: 'Take back', exact: true }).click()
  await expect(back).toBeHidden()
  await expect(again).toContainText(shownBefore)
  await page.reload()
  await expect(page.locator('summary', { hasText: 'Official launch forecast' })).toContainText(shownBefore, { timeout: 60_000 })
  await page.locator('summary', { hasText: 'Official launch forecast' }).click()
  await page.getByRole('button', { name: /^Enter (the official|a newer) forecast$/ }).click()
  await expect(page.getByRole('dialog', { name: 'Official launch forecast' }).locator('li').first()).toContainText(`Took back ${pct}%`)
})

test('radiation and space weather (live API): Blue Ghost’s screening with its particle event, IM-1’s belts not counted, the Sun now', async ({
  page,
  context,
}) => {
  test.setTimeout(120_000)
  await returningVisitor(context)
  const row = (title: string) => page.locator('details').filter({ has: page.locator('summary', { hasText: title }) })
  await page.goto('/missions/blue-ghost-m1/trip')
  await expect(page.locator('[data-guide="section-answer"]')).toContainText('The trip takes', { timeout: 90_000 })
  const rad = row('Radiation on the way')
  await expect(rad.locator('summary').first()).toContainText('screening only')
  await openRow(page, 'Radiation on the way')
  await expect(rad).toContainText(/At least [\d.]+ ×\/÷2 h in the radiation belts over \d+ passes\. Cosmic rays give [\d.]+ ±[\d.]+ mGy a day on the way and [\d.]+ ±[\d.]+ mGy a day at the landing spot, before any shielding\./)
  await expect(rad).toContainText('Screening only:')
  await expect(rad).toContainText('Confirm in SPENVIS, OLTARIS or CREME-MC')
  await expect(rad).toContainText(/Electrons above 1 MeV, whole trip≥[\d.]+ × 10¹⁰ ×\/÷2 per cm²/)
  await expect(rad).toContainText('% of the sky open)')
  // The one solar particle event during the trip, with its record.
  await expect(rad).toContainText('25 February 2025, 00:20 UTC')
  await expect(rad.getByRole('link', { name: 'NASA DONKI record' })).toHaveAttribute('href', /DONKI\/view\/SEP/)
  // Three past large events for comparison, each with its measurements.
  await expect(rad.locator('tbody tr')).toHaveCount(3)
  await expect(rad).toContainText('August 1972')
  await rad.locator('summary', { hasText: 'How each was worked out' }).click()
  await expect(rad).toContainText('AE8/AP8')
  await expect(rad).toContainText('CRaTER')

  // IM-1: NASA's reconstruction starts past the belts, so none is counted (never "≥0").
  await page.goto('/missions/im-1/trip')
  await expect(page.locator('[data-guide="section-answer"]')).toContainText('The trip takes', { timeout: 90_000 })
  await openRow(page, 'Radiation on the way')
  await expect(row('Radiation on the way')).toContainText('No time in the radiation belts is counted (the climb out is not in NASA’s reconstruction).')
  await expect(row('Radiation on the way')).not.toContainText('≥0')

  // The Sun now, from the service: each reading with its age, or why it is not shown.
  await page.goto('/missions/im-1/launch')
  await expect(page.locator('[data-guide="section-answer"]')).toContainText('It launched on', { timeout: 90_000 })
  await openRow(page, 'Space weather now')
  const sw = row('Space weather now')
  // The feeds worker records SWPC every few minutes, so every reading is shown, each with its age.
  await expect(sw.getByText(/^Now: /)).toHaveText(
    /^Now: Kp [\d.]+, protons above 10 MeV at [\d.]+ pfu, X-ray flares class [ABCMX][\d.]+, solar wind at [\d.]+ km\/s; (no alerts in the last 24 hours|\d+ alerts? in the last 24 hours|SWPC’s alerts of the last 24 hours are not shown here)\.$/,
    { timeout: 30_000 },
  )
  const reading = (label: string) => sw.locator('dt', { hasText: label }).locator('xpath=following-sibling::dd[1]')
  for (const label of [
    'Geomagnetic activity (Kp, 0 to 9)',
    'Protons above 10 MeV',
    'Protons above 100 MeV',
    'Solar wind speed',
    'Magnetic field from the Sun, north–south (Bz)',
    'X-ray flares (class)',
  ]) {
    await expect(reading(label), label).toHaveText(/^-?[\w.]+ (pfu |km\/s |nT )?· as of (just now|\d+ min ago|\d+ h ago)$/)
  }
  // "None" only when SWPC issued none in the last 24 hours; a list the service holds back says so, with SWPC's own.
  const live = (await (await page.request.get(`${API}/space-weather`)).json()) as {
    data: { now: { alerts: string[] } }
    meta: { sources: { url: string | null; issued_at: string | null }[] }
  }
  const alertsSource = live.meta.sources.find((x) => /\/alerts\.json$/.test(x.url ?? ''))
  const heldBack = !live.data.now.alerts.length && Boolean(alertsSource?.issued_at && Date.now() - Date.parse(alertsSource.issued_at) < 86_400_000)
  await expect(reading('Alerts in the last 24 hours')).toHaveText(
    live.data.now.alerts.length ? live.data.now.alerts.join('; ') : heldBack ? /^Not shown here, though NOAA SWPC issued one .+ ago: SWPC’s alerts$/ : 'None',
  )
  // NOAA's outlook as numbers, and the forecast word for word.
  await expect(sw).toContainText(
    /NOAA’s outlook for .+, issued .+ UTC: a \d+%, \d+% and \d+% chance of a radiation storm \(S1 or greater\), day by day; the largest Kp expected is [\d.]+\./,
  )
  await sw.locator('summary', { hasText: 'NOAA’s forecast as issued' }).click()
  await expect(sw.getByRole('region', { name: 'NOAA’s three-day forecast as issued' })).toContainText(':Product: 3-Day Forecast')
  // DONKI: its newest events with their records, or why they are not shown (with its age).
  await expect(sw).toContainText('(NASA DONKI)')
  await expect(sw).toContainText(/(Clouds thrown off the Sun \(coronal mass ejections\)|The latest data from NASA space weather database \(DONKI\) is \d+ (days?|hours?) old)/)
  await expectNoSeriousAxe(page, 'space weather now (live) with the forecast open')
})
