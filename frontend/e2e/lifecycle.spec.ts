import { expect, test, type Locator, type Page } from '@playwright/test'
import { API, expectNoSeriousAxe, openRow, openRow as openRowOf, returningVisitor, watchConsole } from './helpers'
import { fixtureJson, fulfillWrite, serveLifecycleFixtures } from './lifecycleFixtures'

/**
 * The mission hub and its six steps, against the contract's fixtures
 * (docs/lifecycle-api.md, src/lib/api/__fixtures__/lifecycle): these tests
 * check the screens' shape and behaviour, not live numbers, because the
 * backend's lifecycle endpoints are being built alongside them. Everything
 * else (the mission record, sign-in, Landing) is the live API.
 */

/** One transparent pixel, for the tiles the fixture tests ask the map for. */
const ONE_PIXEL_PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==', 'base64')

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
  await expect(relay).toContainText('60–95')
  await expect(relay).toContainText('if it flies as planned')
  await expect(relay).toContainText('60 to 95 hours')
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
  const opp = page.getByRole('button', { name: /^28 February 2025, 01:56 UTC ±18 min, from LC-39A/ })
  await opp.click()
  await expect(opp).toHaveAttribute('aria-pressed', 'true')
  await expect(page.locator('main')).toContainText('Numbers for the opportunity on 28 February 2025, 01:56 UTC')
  await page.locator('summary', { hasText: 'Weather rules for this opportunity' }).click()
  const rules = page.getByRole('table').filter({ hasText: 'model runs that break it' })
  await expect(rules).toContainText('3 of 31 model runs')
  await expect(rules).toContainText('Models disagree')
  await expect(rules).toContainText('not yet checked against observations')
  await expect(rules).toContainText('Observation only: no forecast number')
  // Two single forecasts beside the runs, each named in full with how it did; the disagreement is a sentence.
  const wind = rules.getByRole('row').filter({ hasText: 'Sustained wind at 162 ft' })
  await expect(wind).toContainText('HRRR puts the wind at 14.2 m/s, over the limit, and NWS at 8.9 m/s, under it.')
  await expect(wind).toContainText('High-Resolution Rapid Refresh (HRRR) forecast: 14.2 m/s, over the limit.')
  await expect(wind).toContainText("HRRR's 10 m wind was off by 1.2 m/s on average")
  await expect(wind).toContainText('National Weather Service (NWS) forecast: 8.9 m/s, under the limit.')
  await expect(wind).toContainText('keeps no archive of its forecasts, so this one cannot be checked against observations.')
  // The row's closed line counts them, and under the table is what the service says about the check.
  await expect(page.locator('summary', { hasText: 'Weather rules for this opportunity' })).toContainText('6 rules; models disagree on 1')
  await expect(page.locator('details').filter({ has: page.locator('summary', { hasText: 'Weather rules for this opportunity' }) })).toContainText(
    'No rule has been checked against observations (hindcast) yet',
  )
  await expectNoSeriousAxe(page, '/missions/im-2/launch with the weather open')
})

test('launch weather (contract fixtures): a rule whose shares were checked against observations says so, in the rule and in the closed row; both themes, a phone', async ({
  page,
  context,
}) => {
  await returningVisitor(context)
  await serveLifecycleFixtures(context)
  // The wind rule's shares, checked; the rest as they are.
  await context.route(/localhost:8000\/api\/v1\/missions\/[^/]+\/launch\/weather/, async (route) => {
    const body = fixtureJson('launch-weather.json')
    for (const p of body.data.rules[0].per_system) if (p.share) p.share.checked = true
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body), headers: { 'access-control-allow-origin': '*' } })
  })
  await page.goto('/missions/im-2/launch')
  const summary = page.locator('summary', { hasText: 'Weather rules for this opportunity' })
  await expect(summary).toContainText('6 rules; models disagree on 1; 1 checked against observations')
  await summary.click()
  const rules = page.getByRole('table').filter({ hasText: 'model runs that break it' })
  await expect(rules.getByRole('row').filter({ hasText: 'Sustained wind at 162 ft' })).toContainText('A forecast model can answer this · checked against observations')
  await expect(rules.getByRole('row').filter({ hasText: 'No precipitation at the pad' })).toContainText('not yet checked against observations')
  await expectNoSeriousAxe(page, 'launch weather with a checked rule (dark)')
  await page.evaluate(() => localStorage.setItem('pw-prefs', JSON.stringify({ theme: 'light', motion: 'full', shortcuts: true })))
  await page.setViewportSize({ width: 375, height: 812 })
  await page.reload()
  await page.locator('summary', { hasText: 'Weather rules for this opportunity' }).click()
  const cards = page.getByRole('list', { name: 'Weather rules' })
  await expect(cards).toContainText('HRRR puts the wind at 14.2 m/s')
  await expect(cards).toContainText('National Weather Service (NWS) forecast: 8.9 m/s, under the limit.')
  await expectNoSeriousAxe(page, 'launch weather with a checked rule (light, 375 px)')
  expect(await page.evaluate(() => document.documentElement.scrollWidth), 'the weather rules scroll sideways at 375 px').toBeLessThanOrEqual(375)
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
  // How many DONKI gave, when more than are shown.
  await expect(row.locator('h5', { hasText: 'Clouds thrown off the Sun' })).toHaveText('Clouds thrown off the Sun (coronal mass ejections) · 3 newest of 133')
  await expect(row.locator('h5', { hasText: 'Flares' })).toHaveText('Flares')
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

test('contact through a relay (contract fixtures): a range with its launch status, waits that count it, orbiters that could see the lander', async ({
  page,
  context,
}) => {
  await returningVisitor(context)
  await serveLifecycleFixtures(context)
  await page.goto('/missions/im-2/contact')
  const main = page.locator('main')
  const answer = page.locator('[data-guide="section-answer"]')
  await expect(answer).toContainText('Through Lunar Pathfinder (not launched) it could reach Earth for 60–95 h, if it flies as planned; that adds 1.5–4 h to direct contact.')
  await expect(answer).toContainText('The longest time without contact is 1.0 ±0.1 h directly, or 0.4–1 h with the relay, if it flies as planned.')
  const tile = (label: string) => page.locator('div.border.bg-panel', { hasText: label }).first()
  const openRow = async (title: string) => {
    await openRowOf(page, title)
    return page.locator('details').filter({ has: page.locator('summary', { hasText: title }) }).first()
  }
  await expect(tile('Longest time without contact')).toContainText('with the relay, if it flies as planned; 1.0 ±0.1 h directly')
  await expect(tile('Longest message wait')).toContainText('24–61')
  // Each relay with its launch status beside it, in words.
  const relays = await openRow('Relays')
  await expect(page.locator('summary', { hasText: 'Relays' })).toContainText('Lunar Pathfinder · not launched')
  await expect(relays).toContainText('Not launched. To fly on Firefly')
  await expect(relays).toContainText('Adds 1.5–4 h to direct contact, 60–95 h in all through it, if it flies as planned.')
  await expect(relays).toContainText('Numbers that use the relay are ranges over what its orbit could be')
  await expect(relays.locator('dt', { hasText: 'Tilt to the Moon’s equator' }).locator('xpath=following-sibling::dd[1]')).toHaveText('46.8–54.9°, assumed')
  await expect(relays).toContainText('Swept over 36 places')
  // Orbiters already flying could see the lander, and are never called relays.
  const orbiters = await openRow('Orbiters that could see the lander')
  await expect(orbiters).toContainText('None of these orbiters offers to relay for a lander; this is geometry, not a service.')
  await expect(orbiters).toContainText('Lunar Reconnaissance Orbiter · NASA')
  await expect(orbiters).toContainText(
    '14 passes over these dates, 5.60 ±0.01 h in view in all; the longest pass 24.00 ±0.05 min, the longest wait between passes 11.60 ±0.01 h.',
  )
  // A trajectory that stops before the dates end says so.
  await expect(orbiters).toContainText('Its recorded trajectory covers 6 March 2025, 17:30 UTC to 11 March 2025 only; passes outside that are not known.')
  await expect(orbiters.getByRole('link', { name: 'JPL Horizons trajectory' }).first()).toBeVisible()
  await expect(main).toContainText('Could see the lander (an orbiter, not a relay)')
  const more = await openRow('More numbers')
  await expect(more).toContainText('166–168 h, if the relay flies as planned')
  await expect(more.locator('dt', { hasText: 'Longest message wait, directly' }).locator('xpath=following-sibling::dd[1]')).toHaveText('61 min')
  await page.getByRole('button', { name: 'Read the chart as a table' }).click()
  await expect(main.getByRole('table').first()).toContainText('Lunar Reconnaissance Orbiter could see the lander (not a relay)')
  await expect(main.getByRole('table').first()).toContainText('Lunar Pathfinder, relay · not launched')
  await expectNoSeriousAxe(page, 'contact with its relay and orbiter rows open (dark)')
  await page.evaluate(() => localStorage.setItem('pw-prefs', JSON.stringify({ theme: 'light', motion: 'full', shortcuts: true })))
  await page.setViewportSize({ width: 375, height: 812 })
  await page.reload()
  await openRow('Relays')
  await openRow('Orbiters that could see the lander')
  await expectNoSeriousAxe(page, 'contact with its relay and orbiter rows open (light, 375 px)')
  expect(await page.evaluate(() => document.documentElement.scrollWidth), 'contact scrolls sideways at 375 px').toBeLessThanOrEqual(375)
})

test('compare a relay (contract fixtures): tick one, ask again, and the answer, its row and the plan follow; both themes, a phone', async ({ page, context }) => {
  await returningVisitor(context)
  await serveLifecycleFixtures(context)
  // The answer asked with a relay added, as the service gives it: that relay's row, marked as added to compare.
  const asked: string[][] = []
  await context.route(/localhost:8000\/api\/v1\/missions\/[^/]+\/contact(\?.*)?$/, async (route) => {
    const relays = new URL(route.request().url()).searchParams.getAll('relay')
    asked.push(relays)
    if (!relays.length) return route.fallback()
    const body = fixtureJson('contact.json')
    const own = body.data.relays[0]
    body.data.relays.push({ ...own, id: 'altus-1', name: 'Altus-1 data-relay satellite', for_this_mission: false })
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body), headers: { 'access-control-allow-origin': '*' } })
  })
  const compare = () => page.locator('details').filter({ has: page.locator('summary', { hasText: 'Compare a relay' }) })
  const addAltus = async () => {
    await page.goto('/missions/im-2/contact')
    await expect(page.locator('summary', { hasText: 'Compare a relay' })).toContainText('none added')
    await openRow(page, 'Compare a relay')
    await expect(compare().getByRole('checkbox')).toHaveCount(2)
    await expect(compare().getByRole('button', { name: 'Work out the numbers with these' })).toBeDisabled()
    await compare().getByRole('checkbox', { name: /^Altus-1 data-relay satellite/ }).check()
    await compare().getByRole('button', { name: 'Work out the numbers with these' }).click()
  }
  await addAltus()
  // The same request, with the relay asked for; the row comes back open with it ticked, named beside its title.
  await expect.poll(() => asked.some((r) => r.join() === 'altus-1')).toBe(true)
  await expect(page.locator('summary', { hasText: 'Compare a relay' })).toContainText('Altus-1 data-relay satellite')
  await expect(compare()).toHaveAttribute('open', '')
  await expect(compare().getByRole('checkbox', { name: /^Altus-1 data-relay satellite/ })).toBeChecked()
  await openRow(page, 'Relays')
  const relays = page.locator('details').filter({ has: page.locator('summary', { hasText: /^Relays/ }) }).first()
  await expect(relays).toContainText('Altus-1 data-relay satellite')
  await expect(relays).toContainText('Added to compare: not planned for this mission.')
  // The plan: the ION file needs a data rate; a relay's contacts are listed only when asked.
  await openRow(page, 'Download the contact plan')
  const plan = page.locator('details').filter({ has: page.locator('summary', { hasText: 'Download the contact plan' }) })
  await expect(plan.getByRole('button', { name: 'Contact plan for ION (DTN)' })).toBeDisabled()
  await expect(plan.getByRole('link', { name: 'Spreadsheet (CSV)' })).not.toHaveAttribute('href', /relay=/)
  await plan.getByLabel('Data rate for the ION plan, bits per second').fill('2,000,000')
  await expect(plan.getByRole('link', { name: 'Contact plan for ION (DTN)' })).toHaveAttribute('href', /format=ion&start=.*&end=.*&rate_bps=2000000$/)
  await plan.getByRole('checkbox', { name: /^Include the contacts of the planned relays: / }).check()
  await expect(plan.getByRole('link', { name: 'Spreadsheet (CSV)' })).toHaveAttribute('href', /format=csv&.*&relay=pathfinder&relay=altus-1$/)
  await expectNoSeriousAxe(page, 'contact with the compare row and the plan row open (dark)')
  // Take it out again: the answer without it (already worked out, so not asked for again) is back.
  await compare().getByRole('checkbox', { name: /^Altus-1 data-relay satellite/ }).uncheck()
  await compare().getByRole('button', { name: 'Work out the numbers without them' }).click()
  await expect(page.locator('summary', { hasText: 'Compare a relay' })).toContainText('none added')
  await expect(page.locator('details').filter({ has: page.locator('summary', { hasText: /^Relays/ }) }).first()).not.toContainText('Altus-1 data-relay satellite')
  // A phone, in the light theme.
  await page.evaluate(() => localStorage.setItem('pw-prefs', JSON.stringify({ theme: 'light', motion: 'full', shortcuts: true })))
  await page.setViewportSize({ width: 375, height: 812 })
  await addAltus()
  await expect(page.locator('summary', { hasText: 'Compare a relay' })).toContainText('Altus-1 data-relay satellite')
  await openRow(page, 'Download the contact plan')
  await expectNoSeriousAxe(page, 'contact with the compare row and the plan row open (light, 375 px)')
  expect(await page.evaluate(() => document.documentElement.scrollWidth), 'contact scrolls sideways at 375 px').toBeLessThanOrEqual(375)
})

test('rover line of sight (contract fixtures): the answer first, the map in three states with its table twin, both themes, a phone', async ({
  page,
  context,
}) => {
  await returningVisitor(context)
  await serveLifecycleFixtures(context)
  // The answer's tiles: one clear pixel for every request, and the layers asked for are kept.
  const layers = new Set<string>()
  await context.route(/localhost:8000\/api\/v1\/tiles\/viewshed\/91\//, async (route) => {
    layers.add(new URL(route.request().url()).searchParams.get('layer') ?? '')
    await route.fulfill({ status: 200, contentType: 'image/png', body: ONE_PIXEL_PNG })
  })
  await page.goto('/missions/im-2/contact')
  const summary = page.locator('summary', { hasText: 'Rover and lander line of sight' })
  await expect(summary).toContainText('Yaoki')
  await summary.click()
  const row = page.getByTestId('rover-sight')
  await expect(row.locator('p').first()).toHaveText(
    'Within 500 m of the lander, 18–26% of the ground is out of its sight; the radio path is not clear over 25–33%. No drive is published for Yaoki, so no stretch of it can be measured.',
  )
  await expect(row.getByRole('img', { name: /^Line of sight between Yaoki and the lander, out to 500 m in 36 directions/ })).toBeVisible()
  // Three states, each in a glyph and words beside its swatch.
  for (const words of ['In sight', 'Blocked by the ground', 'Uncertain: the terrain map’s error could tip it either way', 'The ground, shaded from the terrain map']) await expect(row).toContainText(words)
  // Laid over the terrain: the ground's tiles under the line of sight's, both from the answer's own address.
  await expect(row.getByTestId('site-tile-map').locator('image').first()).toBeVisible()
  await expect.poll(() => [...layers].sort().join(',')).toBe('sight,terrain')
  // What the states mean, and what is assumed about the antennas and the radio.
  await expect(row).toContainText('uncertain: the model cannot tell.')
  await row.locator('summary', { hasText: 'Antennas, radio and terrain' }).click()
  await expect(row.locator('dt', { hasText: 'Radio frequency' }).locator('xpath=following-sibling::dd[1]')).toContainText('2,400 MHz, assumed')
  await expect(row).toContainText('LDEM_83S_5M: a height every 5 m, each good to ±0.5 m')
  await row.getByRole('button', { name: 'Radio path' }).click()
  await expect(row.getByRole('button', { name: 'Radio path' })).toHaveAttribute('aria-pressed', 'true')
  await expect(row.getByRole('img', { name: /^Radio path between Yaoki and the lander/ })).toBeVisible()
  await expect.poll(() => [...layers].sort().join(',')).toBe('radio,sight,terrain')
  // The table twin, from the same rays: both the line of sight and the radio path.
  await row.getByRole('button', { name: 'Read the chart as a table' }).click()
  const ray = row.getByRole('row', { name: /^100°/ })
  await expect(ray).toContainText('In sight 25–125 m; uncertain 150–175 m; blocked 200–500 m')
  await expect(ray).toContainText('In sight 25–100 m; uncertain 125–150 m; blocked 175–500 m')
  await expect(row.getByRole('row', { name: /^270° \(west\)/ })).toContainText('uncertain 300 m; blocked 325–425 m; in sight 450–500 m')
  await expectNoSeriousAxe(page, 'rover line of sight open with its table (dark)')
  await page.evaluate(() => localStorage.setItem('pw-prefs', JSON.stringify({ theme: 'light', motion: 'full', shortcuts: true })))
  await page.setViewportSize({ width: 375, height: 812 })
  await page.reload()
  await page.locator('summary', { hasText: 'Rover and lander line of sight' }).click()
  await expect(page.getByTestId('rover-sight').getByRole('img')).toBeVisible()
  await expectNoSeriousAxe(page, 'rover line of sight open (light, 375 px)')
  expect(await page.evaluate(() => document.documentElement.scrollWidth), 'the rover row scrolls sideways at 375 px').toBeLessThanOrEqual(375)
})

test('rover line of sight (contract fixtures): tiles that do not load say so, and the table still has the answer', async ({ page, context }) => {
  await returningVisitor(context)
  await serveLifecycleFixtures(context)
  await context.route(/localhost:8000\/api\/v1\/tiles\/viewshed\//, (route) => route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"no-viewshed"}' }))
  await page.goto('/missions/im-2/contact')
  await page.locator('summary', { hasText: 'Rover and lander line of sight' }).click()
  const row = page.getByTestId('rover-sight')
  await expect(row.getByRole('status')).toHaveText('The map layer did not load, so nothing is drawn over the terrain. The table has the same answer.')
  await row.getByRole('button', { name: 'Read the chart as a table' }).click()
  await expect(row.getByRole('row', { name: /^270° \(west\)/ })).toContainText('blocked 325–425 m')
  await expectNoSeriousAxe(page, 'rover map with its tiles missing (dark)')
})

test('rover line of sight (contract fixtures): other values are asked for as typed, a slip is told at its box, and the assumed values come back on request; both themes, a phone', async ({
  page,
  context,
}) => {
  await returningVisitor(context)
  await serveLifecycleFixtures(context)
  await context.route(/localhost:8000\/api\/v1\/tiles\/viewshed\//, (route) => route.fulfill({ status: 200, contentType: 'image/png', body: ONE_PIXEL_PNG }))
  const asked: Record<string, string>[] = []
  await context.route(/localhost:8000\/api\/v1\/missions\/[^/]+\/contact\/rover(\?.*)?$/, (route) => {
    asked.push(Object.fromEntries(new URL(route.request().url()).searchParams))
    return route.fallback()
  })
  await page.goto('/missions/im-2/contact')
  await page.locator('summary', { hasText: 'Rover and lander line of sight' }).click()
  const row = page.getByTestId('rover-sight')
  const antennas = row.locator('details').filter({ has: page.locator('summary', { hasText: 'Antennas, radio and terrain' }) })
  await antennas.locator('summary').click()
  const form = row.getByTestId('rover-inputs')
  const field = (label: string) => form.getByLabel(label)
  const go = form.getByRole('button', { name: 'Work it out with these' })
  const dd = (label: string) => antennas.locator('dt', { hasText: label }).locator('xpath=following-sibling::dd[1]')
  // What is in force for each box, and that nothing is asked until the button is pressed.
  await expect(form.getByText('Between 50 and 5,000 m. In use: 500 m, assumed.')).toBeVisible()
  await expect(form.getByText('Between 30 and 100,000 MHz. In use: 2,400 MHz, assumed.')).toBeVisible()
  await expect(go).toBeDisabled()
  await expect(dd('Lander’s antenna above the ground')).toContainText('3 m, assumed')
  await expect(antennas).not.toContainText('Give lander_antenna_m')
  expect(asked).toEqual([{ rover: 'im-2/yaoki' }])
  // A slip is told at its box, and nothing is asked.
  await field('How far from the lander, metres').fill('10')
  await field('Radio frequency, MHz').fill('fast')
  await go.click()
  await expect(form.getByText('Between 50 and 5,000 m.', { exact: true })).toBeVisible()
  await expect(form.getByText('Give a number. Between 30 and 100,000 MHz.')).toBeVisible()
  await expect(field('How far from the lander, metres')).toHaveAttribute('aria-invalid', 'true')
  expect(asked).toHaveLength(1)
  await expectNoSeriousAxe(page, 'rover values form with its messages (dark)')
  // Typed values are asked for, and only those; the row comes back open with them as the team's.
  await field('How far from the lander, metres').fill('300')
  await field('Radio frequency, MHz').fill('')
  await field('Lander’s antenna above the ground, metres').fill('4')
  await go.click()
  await expect.poll(() => asked.length).toBe(2)
  expect(asked[1]).toEqual({ rover: 'im-2/yaoki', radius_m: '300', lander_antenna_m: '4' })
  await expect(antennas).toHaveAttribute('open', '')
  await expect(dd('Lander’s antenna above the ground')).toContainText('3 m, as you gave it')
  await expect(dd('Rover’s antenna above the ground')).toContainText('assumed')
  // Back to the assumed values: the answer already worked out for them is shown again.
  await antennas.getByRole('button', { name: 'Back to the assumed values' }).click()
  await expect(dd('Lander’s antenna above the ground')).toContainText('3 m, assumed')
  await expect(antennas.getByRole('button', { name: 'Back to the assumed values' })).toHaveCount(0)
  // A phone, in the light theme.
  await page.evaluate(() => localStorage.setItem('pw-prefs', JSON.stringify({ theme: 'light', motion: 'full', shortcuts: true })))
  await page.setViewportSize({ width: 375, height: 812 })
  await page.reload()
  await page.locator('summary', { hasText: 'Rover and lander line of sight' }).click()
  await page.locator('summary', { hasText: 'Antennas, radio and terrain' }).click()
  await expect(page.getByTestId('rover-inputs')).toBeVisible()
  await expectNoSeriousAxe(page, 'rover values form open (light, 375 px)')
  expect(await page.evaluate(() => document.documentElement.scrollWidth), 'the rover row scrolls sideways at 375 px').toBeLessThanOrEqual(375)
})

test('rover line of sight (contract fixtures): a site outside the terrain map says why, with no map', async ({ page, context }) => {
  await returningVisitor(context)
  await serveLifecycleFixtures(context, { swap: { 'rover.json': 'rover-unresolvable.json' } })
  await page.goto('/missions/im-2/contact')
  await page.locator('summary', { hasText: 'Rover and lander line of sight' }).click()
  const row = page.getByTestId('rover-sight')
  await expect(row).toContainText('Cannot be said here. Reiner Gamma is outside the polar terrain map (south of 80°S)')
  await expect(row.getByRole('img')).toHaveCount(0)
})

test('the capsule model (contract fixtures): whether the plan’s limit is met and the air the fall went through, in the row and its closed line; both themes, a phone', async ({
  page,
  context,
}) => {
  await returningVisitor(context)
  await serveLifecycleFixtures(context)
  const check = (returnJson: { data: { capsule: { model_check: { atmosphere: string; passed: boolean; limit_km: number } } } }) => returnJson.data.capsule.model_check
  const served = check(fixtureJson('return.json'))
  await page.goto('/missions/im-2/return')
  const row = page.locator('details').filter({ has: page.locator('summary', { hasText: 'The capsule model, checked against a real landing' }) })
  await expect(row.locator('summary')).toContainText('12.1 km from it; the plan’s 10 km is not met')
  await row.locator('summary').click()
  // The air and the limit as the fixture serves them, the not-met one with its triangle.
  await expect(row).toContainText('The air the modelled fall went through')
  await expect(row).toContainText(served.atmosphere)
  await expect(row).toContainText('The plan’s 10 km is not met: 2.1 km over the limit.')
  await expectNoSeriousAxe(page, 'the capsule model row open (dark)')
  // The same row with the limit met: no triangle, and what is to spare.
  await context.route(/localhost:8000\/api\/v1\/missions\/im-2\/return$/, async (route) => {
    const body = fixtureJson('return.json')
    Object.assign(body.data.capsule.model_check, { distance_km: 9.5, distance_range_km: [6.7, 12.2], passed: true, note: 'The entry model lands its capsule 9.5 km from where the recovery team found it (the limit is 10 km).' })
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body), headers: { 'access-control-allow-origin': '*' } })
  })
  await page.evaluate(() => localStorage.setItem('pw-prefs', JSON.stringify({ theme: 'light', motion: 'full', shortcuts: true })))
  await page.setViewportSize({ width: 375, height: 812 })
  await page.reload()
  const met = page.locator('details').filter({ has: page.locator('summary', { hasText: 'The capsule model, checked against a real landing' }) })
  await expect(met.locator('summary')).toContainText('9.5 km from it; the plan’s 10 km is met')
  await met.locator('summary').click()
  await expect(met).toContainText('The plan’s 10 km is met, with 0.5 km to spare.')
  await expect(met).not.toContainText('not met')
  await expectNoSeriousAxe(page, 'the capsule model row open (light, 375 px)')
  expect(await page.evaluate(() => document.documentElement.scrollWidth), 'the capsule row scrolls sideways at 375 px').toBeLessThanOrEqual(375)
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
  // The climb's direction is worked out from the reconstruction (inertial), with its heading over the ground.
  const dd = (row: Locator, label: string) => row.locator('dt', { hasText: label }).locator('xpath=following-sibling::dd[1]')
  await expect(dd(flight, 'Direction of the climb')).toHaveText(
    /^88\.8°Worked out by POLAR WINDOW: The climb's direction is not published\. This is the inertial one worked out from NASA's reconstruction.+Over the ground it is [\d.]+°, inside the pad's 35 to 120°\.$/,
  )
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
  // A designed launch climbs the way the vehicle's flown lunar launches did, averaged; that sets the ± on its time.
  await expect(dd(designed, 'Direction of the climb')).toHaveText(
    /^87\.7°Assumed: The direction the vehicle's direct lunar flights climbed \(IM-1 88\.8°, IM-2 86\.6°\).+Each degree moves the launch instant by about 7 minutes, which sets the margin on the liftoff\.$/,
  )
  await expect(dd(designed, 'Launch time')).toContainText('±18 min')
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

test('launch period (live API): Peregrine and Blue Ghost 1 show the period Launch Library 2 published, in the row, the table and the calendar’s mark; IM-1 and Griffin-1 are one instant', async ({
  page,
  context,
}) => {
  test.setTimeout(240_000)
  await returningVisitor(context)
  const main = page.locator('main')
  const answer = page.locator('[data-guide="section-answer"]')
  const period = page.getByTestId('launch-period')
  const flight = page.locator('details').filter({ has: page.locator('summary', { hasText: 'The flight as launched' }) })
  const opens = async () => {
    if ((await flight.getAttribute('open')) === null) await flight.locator('summary').click()
  }
  for (const [mission, words] of [
    ['peregrine-m1', '07:18 to 08:03 UTC'],
    ['blue-ghost-m1', '06:06 to 06:45 UTC'],
  ] as const) {
    await page.goto(`/missions/${mission}/launch`)
    await expect(answer).toContainText('It launched on', { timeout: 90_000 })
    // The service's own sentence under the numbers, and the same period in the row, the mark's name and the table.
    await expect(main).toContainText(`published with a launch window from ${words}`)
    await opens()
    await expect(period).toHaveText(`${words} (published)`)
    await expect(page.getByRole('group', { name: 'Launch opportunities by day' }).getByRole('button')).toHaveAttribute('aria-label', new RegExp(`, a launch period from ${words}$`))
    await expect(page.getByText('The launch period, from its opening to its close')).toBeVisible()
    await page.getByRole('button', { name: 'Read the chart as a table' }).click()
    await expect(main.getByRole('table').first()).toContainText(`Launch period, ${words}`)
    await expectNoSeriousAxe(page, `/missions/${mission}/launch (live) with its flight row and table open`)
  }
  // Launches published as one instant say so, and draw no period.
  for (const mission of ['im-1', 'griffin-1']) {
    await page.goto(`/missions/${mission}/launch`)
    await expect(answer).toContainText(/It launched on|launch opportunit/, { timeout: 90_000 })
    if (mission === 'im-1') {
      await opens()
      await expect(period).toHaveText('One instant (published)')
    }
    await expect(page.getByText('The launch period, from its opening to its close')).toHaveCount(0)
  }
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

test('launch weather (live API): the forecasts for a launch a few hours ahead, each with the service’s note, and any disagreement in the service’s sentence', async ({ page, context }) => {
  test.setTimeout(120_000)
  await returningVisitor(context)
  // No planned opportunity is a few hours away, so the screen is given the service's answer for a launch time at the Cape three hours
  // ahead (the same endpoint, `t0` and `pad`) in place of the one it asks for; the words on the screen are the served ones.
  const hour = new Date(Math.ceil((Date.now() + 3 * 3_600_000) / 3_600_000) * 3_600_000).toISOString().replace('.000Z', 'Z')
  const served = await page.request.get(`${API}/missions/im-2/launch/weather`, { params: { t0: hour, pad: 'ksc-lc-39a' } })
  expect(served.ok(), 'the service answered the launch weather for a time and a pad').toBeTruthy()
  const wx = (await served.json()) as {
    data: { rules: { text: string; disagreement: boolean; disagreement_note: string | null; one_forecast: { system: string; note: string | null }[] }[] }
  }
  const forecasts = wx.data.rules.flatMap((r) => r.one_forecast)
  expect(forecasts.length, 'at least the National Weather Service’s hourly forecast is in the answer').toBeGreaterThan(0)
  await context.route(/localhost:8000\/api\/v1\/missions\/im-2\/launch\/weather/, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(wx), headers: { 'access-control-allow-origin': '*' } }),
  )
  await page.goto('/missions/im-2/launch')
  await expect(page.locator('[data-guide="section-answer"]')).toContainText('It launched on', { timeout: 90_000 })
  await openRow(page, 'Weather rules for this launch')
  const rules = page.getByRole('table').filter({ hasText: 'model runs that break it' })
  for (const f of forecasts) {
    if (f.note) await expect(rules).toContainText(f.note)
    await expect(rules).toContainText(f.system === 'NWS' ? 'National Weather Service (NWS) forecast:' : 'High-Resolution Rapid Refresh (HRRR) forecast:')
  }
  for (const r of wx.data.rules) {
    if (r.disagreement_note) await expect(rules).toContainText(r.disagreement_note)
    expect(Boolean(r.disagreement_note), `${r.text}: the sentence is there when the rule is marked as disagreeing`).toBe(r.disagreement)
  }
  // No rule shown as checked unless a share was (the service says which).
  await expect(page.locator('summary', { hasText: 'Weather rules for this launch' })).toContainText(/\d+ rules?/)
  await expectNoSeriousAxe(page, '/missions/im-2/launch with the forecasts of a launch three hours ahead (live)')
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
  // Whether the plan's limit is met, and which air the modelled fall went through, are read from the answer, not from here.
  const served = ((await (await page.request.get(`${API}/missions/im-1/return`)).json()).data.capsule as { model_check: { atmosphere: string; passed: boolean; limit_km: number } }).model_check
  expect(served.atmosphere.length, 'the service says which air the modelled fall went through').toBeGreaterThan(0)
  await expect(check.locator('summary')).toContainText(new RegExp(`[\\d.]+ km from it; the plan’s ${served.limit_km} km is ${served.passed ? 'met' : 'not met'}`))
  await check.locator('summary').click()
  await expect(check).toContainText('The air the modelled fall went through')
  await expect(check).toContainText(served.atmosphere)
  await expect(check).toContainText(new RegExp(`The plan’s ${served.limit_km} km is ${served.passed ? 'met, with' : 'not met:'} [\\d.]+ km ${served.passed ? 'to spare' : 'over the limit'}\\.`))
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

test('radiation and space weather (live API): Blue Ghost’s screening with its particle event, IM-1’s belts not counted, Peregrine’s surface, the Sun now', async ({
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
  // No elevation data at its site: the open sky is a flat horizon, assumed, and it says so.
  const dd = (label: string) => rad.locator('dl').first().locator('dt', { hasText: label }).locator('xpath=following-sibling::dd[1]')
  await expect(dd('Cosmic-ray dose at the landing spot')).toHaveText(/^[\d.]+ ±[\d.]+ mGy a day \(100% of the sky open, assumed\)$/)
  await expect(rad).toContainText('The elevation model does not cover this landing site, so its horizon is taken as flat (open sky 1)')
  // The one solar particle event during the trip, in the singular, with its record.
  await expect(rad).toContainText("One solar particle event crossed NOAA's threshold (10 pfu above 10 MeV at GOES) during the trip, from NASA DONKI; its fluence is not worked out.")
  await expect(rad).toContainText('25 February 2025, 00:20 UTC')
  await expect(rad.getByRole('link', { name: 'NASA DONKI record' })).toHaveAttribute('href', /DONKI\/view\/SEP/)
  // Three past large events for comparison, each with its measurements.
  await expect(rad.locator('tbody tr')).toHaveCount(3)
  await expect(rad).toContainText('August 1972')
  await rad.locator('summary', { hasText: 'How each was worked out' }).click()
  await expect(rad).toContainText('AE8/AP8')
  await expect(rad).toContainText('CRaTER')
  await expect(rad).toContainText('A flat horizon, assumed: the elevation model does not cover this site.')

  // IM-1: NASA's reconstruction starts past the belts, so they are not counted, and it says why once (never "≥0" or "0 ×/÷2").
  await page.goto('/missions/im-1/trip')
  await expect(page.locator('[data-guide="section-answer"]')).toContainText('The trip takes', { timeout: 90_000 })
  await openRow(page, 'Radiation on the way')
  const im1 = row('Radiation on the way')
  const why = "NASA's reconstruction starts 242,208 km above Earth, beyond the belts, so the crossing of them is not in it and is not counted."
  await expect(im1.locator('p').first()).toHaveText(new RegExp(`^${why.replace(/[.()]/g, '\\$&')} Cosmic rays give [\\d.]+ ±[\\d.]+ mGy a day on the way and [\\d.]+ ±[\\d.]+ mGy a day at the landing spot, before any shielding\\.$`))
  const im1dd = (label: string) => im1.locator('dl').first().locator('dt', { hasText: label }).locator('xpath=following-sibling::dd[1]')
  await expect(im1dd('Time in the radiation belts')).toHaveText(why)
  await expect(im1dd('Electrons above 1 MeV, whole trip')).toHaveText('Not counted, as above')
  await expect(im1dd('Protons above 10 MeV in the belts, whole trip')).toHaveText('Not counted, as above')
  await expect(im1).not.toContainText('≥0')
  await expect(im1).not.toContainText(/\b0 ×\/÷2/)

  // Peregrine was lost before reaching the Moon: no surface dose, and it says why.
  await page.goto('/missions/peregrine-m1/trip')
  await expect(page.locator('[data-guide="section-answer"]')).toContainText('The trip takes', { timeout: 90_000 })
  await openRow(page, 'Radiation on the way')
  const per = row('Radiation on the way')
  await expect(per.locator('p').first()).toHaveText(/ in the radiation belts over 2 passes\. Cosmic rays give [\d.]+ ±[\d.]+ mGy a day on the way, before any shielding\.$/)
  await expect(per).toContainText('It was lost before reaching the Moon, so there is no surface dose.')
  await expect(per.locator('dt', { hasText: 'Cosmic-ray dose at the landing spot' })).toHaveCount(0)
  await expectNoSeriousAxe(page, '/missions/peregrine-m1/trip (live) with radiation open')

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
  // "None" only when the service says its list is current and empty; a list it cannot show says why, with SWPC's own.
  const live = (await (await page.request.get(`${API}/space-weather`)).json()) as {
    data: {
      now: { xray_class: string | null; xray_missing_reason: string | null; alerts: string[]; alerts_missing_reason: string | null }
      donki: { cme: unknown[]; counts: { cme: number | null } }
    }
  }
  const now = live.data.now
  await expect(reading('Alerts in the last 24 hours')).toHaveText(
    now.alerts.length ? now.alerts.join('; ') : now.alerts_missing_reason ? `${now.alerts_missing_reason} SWPC’s alerts` : 'None',
  )
  if (!now.xray_class) await expect(reading('X-ray flares (class)')).toHaveText(now.xray_missing_reason ?? 'Not reported')
  // DONKI: "3 newest of {n}" when it gave more than three.
  const cmes = live.data.donki.counts.cme ?? live.data.donki.cme.length
  if (cmes > 3) await expect(sw.locator('h5', { hasText: 'Clouds thrown off the Sun' })).toContainText(`· 3 newest of ${cmes}`)
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

test('compare a relay (live API): Lunar Pathfinder added at IM-2’s landing spot, its row marked as added to compare, and both plan files list it as planned', async ({
  page,
  context,
  request,
}) => {
  test.setTimeout(240_000)
  await returningVisitor(context)
  const answer = page.locator('[data-guide="section-answer"]')
  await page.goto('/missions/im-2/contact')
  await expect(answer).toContainText('A ground station can hear it', { timeout: 120_000 })
  await expect(page.locator('summary', { hasText: 'Compare a relay' })).toContainText('none added')
  await openRow(page, 'Compare a relay')
  const compare = page.locator('details').filter({ has: page.locator('summary', { hasText: 'Compare a relay' }) })
  // The catalogue's relays, each with who runs it and where it stands; IM-2 plans none of them.
  await expect(compare.getByRole('checkbox', { name: /^Altus-1 data-relay satellite · Intuitive Machines/ })).toBeVisible()
  await compare.getByRole('checkbox', { name: /^Lunar Pathfinder · ESA/ }).check()
  await compare.getByRole('button', { name: 'Work out the numbers with these' }).click()
  await expect(answer).toContainText(/Through Lunar Pathfinder \(planned, not launched\) it could reach Earth for [\d,.]+–[\d,.]+ h, if it flies as planned/, { timeout: 180_000 })
  await expect(page.locator('summary', { hasText: 'Compare a relay' })).toContainText('Lunar Pathfinder')
  await openRow(page, /^Relays/)
  const relays = page.locator('details').filter({ has: page.locator('summary', { hasText: /^Relays/ }) }).first()
  await expect(relays).toContainText('Added to compare: not planned for this mission.')
  await expect(relays).toContainText('673 km')
  // The plan lists the relay's contacts only when asked, and says they are planned.
  await openRow(page, 'Download the contact plan')
  const plan = page.locator('details').filter({ has: page.locator('summary', { hasText: 'Download the contact plan' }) })
  const csvLink = plan.getByRole('link', { name: 'Spreadsheet (CSV)' })
  const direct = await request.get((await csvLink.getAttribute('href')) as string)
  expect(direct.status()).toBe(200)
  expect(await direct.text()).not.toContain('planned relay')
  await plan.getByRole('checkbox', { name: /^Include the contacts of the planned relay: Lunar Pathfinder\./ }).check()
  const withRelay = await request.get((await csvLink.getAttribute('href')) as string)
  expect(withRelay.status()).toBe(200)
  const csv = await withRelay.text()
  expect(csv.split(/\r?\n/)[0]).toBe('from,to,start_utc,end_utc,hours,basis')
  expect(csv).toMatch(/lander,lunar-pathfinder,.*planned relay; node [\d.]+ deg, phase [\d.]+ deg, one of 5184 placements/)
  await plan.getByLabel('Data rate for the ION plan, bits per second').fill('2,000,000')
  const ion = await request.get((await plan.getByRole('link', { name: 'Contact plan for ION (DTN)' }).getAttribute('href')) as string)
  expect(ion.status()).toBe(200)
  const text = await ion.text()
  expect(text).toContain('# PLANNED relay Lunar Pathfinder')
  expect(text).toMatch(/^a contact /m)
  expect(text).toMatch(/^a range /m)
  await expectNoSeriousAxe(page, 'IM-2 contact with Lunar Pathfinder added (dark)')
})

test('rover line of sight (live API): other values are worked out again, 300 m out and a 4 m antenna on the lander, in the sentence, the map and the table, and the assumed values come back', async ({
  page,
  context,
}) => {
  test.setTimeout(300_000)
  await returningVisitor(context)
  await page.goto('/missions/im-2/contact')
  await page.locator('summary', { hasText: 'Rover and lander line of sight' }).click()
  const yaoki = page.getByTestId('rover-sight')
  await expect(yaoki.locator('p').first()).toContainText(/^Within 500 m of the lander, /, { timeout: 180_000 })
  const antennas = yaoki.locator('details').filter({ has: page.locator('summary', { hasText: 'Antennas, radio and terrain' }) })
  await antennas.locator('summary').click()
  const form = yaoki.getByTestId('rover-inputs')
  // The service's own assumptions, as it says them.
  await expect(form.getByText('Between 50 and 5,000 m. In use: 500 m, assumed.')).toBeVisible()
  await expect(antennas.locator('dt', { hasText: 'Lander’s antenna above the ground' }).locator('xpath=following-sibling::dd[1]')).toContainText(/^2 m, assumed/)
  await expect(antennas).not.toContainText(/Give [a-z]+_[a-z]+/)
  await form.getByLabel('How far from the lander, metres').fill('300')
  await form.getByLabel('Lander’s antenna above the ground, metres').fill('4')
  await form.getByRole('button', { name: 'Work it out with these' }).click()
  await expect(yaoki.locator('p').first()).toContainText(/^Within 300 m of the lander, [\d.]+–[\d.]+% of the ground is out of its sight/, { timeout: 240_000 })
  await expect(yaoki.getByRole('img', { name: /^Line of sight between Yaoki and the lander, out to 300 m in 72 directions/ })).toBeVisible()
  await expect(antennas).toHaveAttribute('open', '')
  await expect(antennas.locator('dt', { hasText: 'Lander’s antenna above the ground' }).locator('xpath=following-sibling::dd[1]')).toHaveText('4 m, as you gave it')
  await expect(antennas.locator('dt', { hasText: 'Rover’s antenna above the ground' }).locator('xpath=following-sibling::dd[1]')).toContainText(/assumed/)
  // The map is this answer's own: its tiles are drawn, and none failed.
  const tiles = yaoki.getByTestId('site-tile-map').locator('image')
  await expect
    .poll(async () => (await tiles.evaluateAll((els) => els.map((e) => (e as SVGImageElement).getAttribute('href') ?? ''))).filter((h) => /layer=(terrain|sight)$/.test(h)).length, {
      timeout: 60_000,
    })
    .toBeGreaterThan(1)
  await page.waitForLoadState('networkidle')
  await expect(yaoki.getByRole('status')).toHaveCount(0)
  await yaoki.getByRole('button', { name: 'Read the chart as a table' }).click()
  await expect(yaoki.getByRole('row', { name: /^90° \(east\)/ })).toBeVisible()
  await expectNoSeriousAxe(page, 'rover answer with the team’s values (dark)')
  // Back to the assumed values.
  await antennas.getByRole('button', { name: 'Back to the assumed values' }).click()
  await expect(yaoki.locator('p').first()).toContainText(/^Within 500 m of the lander, /, { timeout: 120_000 })
})

test('relays, orbiters and rovers (live API): IM-3’s planned relay as a range, IM-2’s orbiter passes and Yaoki’s line of sight, a rover off the polar map', async ({
  page,
  context,
}) => {
  test.setTimeout(240_000)
  await returningVisitor(context)
  const answer = page.locator('[data-guide="section-answer"]')
  const row = async (title: string) => {
    await openRow(page, title)
    return page.locator('details').filter({ has: page.locator('summary', { hasText: title }) }).first()
  }

  // IM-3: Altus-1 flies alongside it, its orbit assumed from NASA's reference relay orbits.
  await page.goto('/missions/im-3/contact')
  await expect(answer).toContainText(/Through Altus-1 data-relay satellite \(planned, not launched\) it could reach Earth for [\d,.]+–[\d,.]+ h, if it flies as planned/, {
    timeout: 120_000,
  })
  await expect(answer).toContainText(/The longest time without contact is [\d.]+ h directly, or [\d.]+–[\d.]+ h with the relay, if it flies as planned\./)
  const relays = await row('Relays')
  await expect(relays).toContainText('Planned, not launched.')
  await expect(relays).toContainText(/in all through it, if it flies as planned\./)
  await expect(relays.locator('dt', { hasText: 'Tilt to the Moon’s equator' }).locator('xpath=following-sibling::dd[1]')).toHaveText(/°, assumed$/)
  // Its dates are past the recorded orbiter trajectories: not known, never "no pass".
  const orbiters = await row('Orbiters that could see the lander')
  await expect(orbiters).toContainText('Not known: No JPL Horizons trajectory is recorded for these dates')
  await expect(orbiters).not.toContainText('No pass over these dates')
  // Its rovers are off the polar terrain map, and it says so.
  const rover = page.locator('details').filter({ has: page.locator('summary', { hasText: 'Rover and lander line of sight' }) })
  await rover.locator('summary').click()
  await expect(rover.getByTestId('rover-sight')).toContainText(/^\? Cannot be said here\. .*outside the polar terrain model/, { timeout: 60_000 })
  await expect(rover.getByLabel('Rover')).toBeVisible()
  await expectNoSeriousAxe(page, 'IM-3 contact with relays, orbiters and rover open (dark)')

  // IM-2: LRO and Danuri passed over the landing spot; Yaoki's line of sight on the polar map.
  await page.goto('/missions/im-2/contact')
  await expect(answer).toContainText('A ground station can hear it', { timeout: 120_000 })
  const passes = await row('Orbiters that could see the lander')
  await expect(passes).toContainText(/Lunar Reconnaissance Orbiter · NASA\d+ passes over these dates, [\d.]+ ±[\d.]+ h in view in all/)
  await page.getByRole('button', { name: 'Read the chart as a table' }).first().click()
  await expect(page.locator('main').getByRole('table').first()).toContainText('Lunar Reconnaissance Orbiter could see the lander (not a relay)')
  await page.locator('summary', { hasText: 'Rover and lander line of sight' }).click()
  const yaoki = page.getByTestId('rover-sight')
  await expect(yaoki.locator('p').first()).toContainText(
    /^Within 500 m of the lander, [\d.]+–[\d.]+% of the ground is out of its sight; the radio path is not clear over [\d.]+–[\d.]+%\. No drive is published for Yaoki/,
    { timeout: 120_000 },
  )
  await expect(yaoki.getByRole('img', { name: /^Line of sight between Yaoki and the lander, out to 500 m in 72 directions/ })).toBeVisible()
  // Over the terrain: the service's tiles for this answer, the ground and the line of sight, drawn (not the broken-image kind).
  const tiles = yaoki.getByTestId('site-tile-map').locator('image')
  await expect
    .poll(async () => (await tiles.evaluateAll((els) => els.map((e) => (e as SVGImageElement).getAttribute('href') ?? ''))).filter((h) => /layer=(terrain|sight)$/.test(h)).length, {
      timeout: 60_000,
    })
    .toBeGreaterThan(1)
  await page.waitForLoadState('networkidle')
  await expect(yaoki.getByRole('status')).toHaveCount(0)
  await expect(yaoki).toContainText('The ground, shaded from the terrain map')
  await expect(yaoki.getByRole('row', { name: /^90° \(east\)/ })).toBeVisible()
  await yaoki.locator('summary', { hasText: 'Antennas, radio and terrain' }).click()
  await expect(yaoki).toContainText(/LOLA_LDEM_80S_20M: a height every 20 m, each good to ±2 m/)
  await expectNoSeriousAxe(page, 'IM-2 contact with orbiters and Yaoki open (dark)')
  await page.evaluate(() => localStorage.setItem('pw-prefs', JSON.stringify({ theme: 'light', motion: 'full', shortcuts: true })))
  await page.setViewportSize({ width: 375, height: 812 })
  await page.reload()
  await openRow(page, 'Orbiters that could see the lander')
  await page.locator('summary', { hasText: 'Rover and lander line of sight' }).click()
  await expect(page.getByTestId('rover-sight').getByRole('img')).toBeVisible({ timeout: 60_000 })
  await expectNoSeriousAxe(page, 'IM-2 contact with orbiters and Yaoki open (light, 375 px)')
  expect(await page.evaluate(() => document.documentElement.scrollWidth), 'IM-2 contact scrolls sideways at 375 px').toBeLessThanOrEqual(375)
})
