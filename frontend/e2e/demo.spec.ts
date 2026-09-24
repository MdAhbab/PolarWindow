import { expect, test } from '@playwright/test'
import { expectNoSeriousAxe, returningVisitor, watchConsole } from './helpers'

/**
 * The video's path (report-work demo script, beats 1–8), end to end, with
 * axe on every screen it visits and no console errors or warnings.
 */
test('front page: one click signs in and the guide opens on the first feature', async ({ page }) => {
  const problems = watchConsole(page)
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Plan a landing where the Sun barely rises')
  await expectNoSeriousAxe(page, '/ (front page)')
  // The old story's address opens the front page at the four ideas.
  await page.goto('/story')
  await expect(page).toHaveURL(/\/#why$/)
  await expect(page.getByRole('heading', { name: 'The Sun never climbs' })).toBeVisible()

  await page.getByRole('button', { name: 'Open the dashboard' }).first().click()
  await expect(page).toHaveURL(/\/missions$/)
  const guide = page.getByRole('region', { name: 'Guide' })
  await expect(guide).toContainText('1 of 9')
  await expect(guide).toContainText('Find a mission')
  await expect(page.locator('[data-guide-active]')).toHaveAttribute('data-guide', 'missions-filters')
  await expectNoSeriousAxe(page, '/missions with the guide open')

  // Next moves to the page the step is about and points at its feature.
  await guide.getByRole('button', { name: 'Next' }).click()
  await expect(page).toHaveURL(/\/map$/)
  await expect(guide).toContainText('Choose a site on the map')
  await expect(page.locator('[data-guide-active]')).toHaveAttribute('data-guide', 'map')
  await guide.getByRole('button', { name: 'Back' }).click()
  await expect(page).toHaveURL(/\/missions$/)

  // Closed, it stays closed across a reload, and Guide in the header brings it back.
  await guide.getByRole('button', { name: 'Close the guide' }).click()
  await expect(guide).toHaveCount(0)
  await page.reload()
  await expect(page.getByRole('region', { name: 'Guide' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Guide', exact: true }).click()
  await expect(page.getByRole('region', { name: 'Guide' })).toContainText('Find a mission')
  expect(problems).toEqual([])
})

test('a deep link without a session goes to the front page, then on to the page asked for', async ({ page }) => {
  await page.goto('/missions/im-2')
  await expect(page).toHaveURL(/\/\?next=%2Fmissions%2Fim-2$/)
  await page.getByRole('button', { name: 'Open the dashboard' }).first().click()
  await expect(page).toHaveURL(/\/missions\/im-2$/)
  await expect(page.getByRole('heading', { level: 1 })).toContainText('IM-2')
})

test('settings: the project controls, behind a confirm step', async ({ page, context }) => {
  await returningVisitor(context)
  await page.goto('/missions')
  await page.getByRole('button', { name: 'Settings' }).click()
  const sheet = page.getByRole('dialog', { name: 'Settings' })
  await expect(sheet).toContainText('Signed in as Project manager')
  await expect(sheet.getByRole('group', { name: 'AI assistant' })).toBeVisible()
  await expect(sheet.getByText('Moon terrain map')).toBeVisible()
  await expectNoSeriousAxe(page, 'the Settings sheet')
  // A destructive action asks first, and "Keep them" leaves everything as it was.
  const clear = sheet.getByRole('button', { name: 'Clear the AI activity log' })
  if (await clear.isEnabled()) {
    await clear.click()
    await expect(sheet.getByRole('group', { name: 'Clear the AI activity log' })).toContainText('can’t be undone')
    await sheet.getByRole('button', { name: 'Keep them' }).click()
    await expect(clear).toBeVisible()
  }
})

test('demo path: volatiles → IM-2 → shift the date → compare → ask → run log', async ({ page, context }) => {
  await returningVisitor(context)
  const problems = watchConsole(page)

  // Beat 2: the Volatiles chip.
  await page.goto('/missions')
  const count = page.locator('[aria-live="polite"]').filter({ hasText: 'missions' }).first()
  await expect(count).toHaveText('Showing 20 of 20 missions')
  await expectNoSeriousAxe(page, '/missions')
  await page.getByRole('button', { name: 'Volatiles' }).click()
  await expect(page).toHaveURL(/type=volatiles/)
  await expect(count).toHaveText('Showing 5 of 20 missions')
  const list = page.getByRole('region', { name: 'Missions' }).or(page.locator('section[aria-labelledby="missions-list-h"]'))
  await expect(list.getByRole('link')).toHaveCount(5)
  await expectNoSeriousAxe(page, '/missions?type=volatiles')

  // Beat 3: IM-2, named from the data.
  await page.getByRole('link', { name: /^IM-2, Intuitive Machines, landed 6 March 2025, 17:30 UTC, Partly successful, carries volatiles/ }).click()
  await expect(page).toHaveURL(/\/missions\/im-2$/)
  await expect(page.getByRole('heading', { level: 1 })).toContainText('IM-2')
  const main = page.locator('main')
  await expect(main).toContainText('6 Mar 2025, 17:30 UTC')
  await expect(main).toContainText('as flown')
  await expect(main).not.toContainText('[')
  await expect(main).not.toContainText('±0.0')
  await expectNoSeriousAxe(page, '/missions/im-2')

  // Shift the date: a burst of month picks leaves one live request per
  // endpoint, the superseded ones cancelled, and the old numbers dimmed.
  const seen: { url: string; state: string }[] = []
  page.on('request', (r) => {
    if (/\/sites\/mission-im-2\/metrics/.test(r.url())) seen.push({ url: r.url(), state: 'pending' })
  })
  page.on('requestfinished', (r) => {
    const s = seen.find((x) => x.url === r.url() && x.state === 'pending')
    if (s) s.state = 'done'
  })
  page.on('requestfailed', (r) => {
    const s = seen.find((x) => x.url === r.url() && x.state === 'pending')
    if (s) s.state = 'cancelled'
  })
  await page.route(/\/sites\/mission-im-2\/(metrics|windows)/, async (route) => {
    await new Promise((r) => setTimeout(r, 300))
    await route.continue().catch(() => {})
  })
  const months = page.getByRole('option')
  for (const i of [2, 3, 4, 5, 6]) await months.nth(i).click()
  await expect(page.locator('.opacity-70').first()).toBeVisible()
  await expect.poll(() => seen.filter((s) => s.state === 'pending').length).toBe(0)
  const done = seen.filter((s) => s.state === 'done')
  expect(done, JSON.stringify(seen, null, 1)).toHaveLength(1)
  expect(seen.filter((s) => s.state === 'cancelled').length).toBeGreaterThanOrEqual(3)
  await page.unroute(/\/sites\/mission-im-2\/(metrics|windows)/)
  await expect(months.nth(6)).toHaveAttribute('aria-selected', 'true')

  // The month strip by keyboard: arrows move, Enter picks.
  await months.nth(6).focus()
  await page.keyboard.press('ArrowRight')
  await expect(months.nth(7)).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(months.nth(7)).toHaveAttribute('aria-selected', 'true')
  await expect(months.nth(7)).toHaveAttribute('aria-label', /^October 2025: sunlight \d+ percent, Earth \d+ percent/)

  // Beat 5: compare with the nearest candidates, and no "best" on a bound.
  await page.getByRole('button', { name: 'Compare with nearby sites' }).click()
  await expect(page).toHaveURL(/\/compare\?from=im-2&sites=/)
  await expect(page.locator('main')).toContainText('Started from IM-2')
  await expect(page.locator('main')).toContainText('nearest to it by distance')
  await page.getByRole('button', { name: 'Longest night' }).click()
  await expectNoSeriousAxe(page, '/compare')

  // Beat 6: ask, then the run log.
  await page.getByRole('link', { name: 'Missions' }).first().click()
  await page.getByRole('button', { name: 'Ask about missions' }).click()
  await page.getByLabel('Your question').fill('Which south-polar CLPS targets carry volatiles instruments, and what is their longest night?')
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  await expect(page.getByText('Summary from measurements (no AI)')).toBeVisible()
  const how = page.getByRole('button', { name: 'How the AI got this' })
  await how.click()
  const log = page.getByRole('dialog', { name: 'AI activity log' })
  await expect(log).toBeVisible()
  await expect(log.getByRole('table').first()).toBeVisible()
  await expectNoSeriousAxe(page, 'run log')
  await page.keyboard.press('Escape')
  await expect(log).toBeHidden()
  await expect(how).toBeFocused()

  expect(problems).toEqual([])
})

test('beats 4 and 7: VIPER month strip and the far side', async ({ page, context }) => {
  await returningVisitor(context)
  const problems = watchConsole(page)
  await page.goto('/missions/blue-moon-mk1-viper')
  await expect(page.locator('main')).toContainText('Landing known only to the year; choose a date below')
  await expect(page.getByRole('option', { name: /^April 2027: sunlight 8 percent/ })).toBeVisible()
  await expect(page.getByRole('option', { name: /^November 2027: sunlight 41 percent/ })).toBeVisible()
  await expect(page.locator('main')).toContainText('centre of Mons Mouton, not a landing point')

  await page.goto('/missions/apex-1')
  const main = page.locator('main')
  await expect(main).toContainText('There is no terrain data outside 80°S')
  await expect(main).toContainText('Numbers are for the centre of Schrödinger')
  // Earth contact is zero on the far side: a measurement, shown as 0.
  const earth = main.locator('div.border.bg-panel', { hasText: 'Time in contact with Earth' }).first()
  await expect(earth).toContainText('about 0 hours')
  await expectNoSeriousAxe(page, '/missions/apex-1')
  expect(problems).toEqual([])
})
