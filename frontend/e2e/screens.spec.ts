import { expect, test } from '@playwright/test'
import { expectNoSeriousAxe, openRow, returningVisitor, watchConsole } from './helpers'

const ROUTES = [
  '/',
  '/missions',
  '/missions/im-2',
  '/missions/blue-ghost-m1',
  '/missions/cs-8',
  // The six steps (contract fixtures where the backend does not answer yet).
  '/missions/im-2/ready',
  '/missions/im-2/launch',
  '/missions/im-2/trip',
  '/missions/im-2/landing',
  '/missions/im-2/contact',
  '/missions/im-2/return',
  // The steps the service answers, for two more flown missions: IM-1's trip
  // has gaps in NASA's reconstruction, and its contact is worked out on request.
  // Launch: IM-1's flown launch and Griffin-1's calendar.
  '/missions/im-1/ready',
  '/missions/im-1/launch',
  '/missions/griffin-1/launch',
  '/missions/im-1/trip',
  '/missions/im-1/contact',
  // Return: IM-1's booster back on land, Griffin-1's not published yet.
  '/missions/im-1/return',
  '/missions/griffin-1/return',
  '/missions/blue-ghost-m1/trip',
  '/missions/blue-ghost-m1/contact',
  '/map',
  '/site',
  '/compare',
  '/skyline',
  '/plan',
  '/report',
]

for (const theme of ['dark', 'light'] as const) {
  test(`axe: every route, ${theme} theme`, async ({ page, context }) => {
    // Many routes, each read by axe: well past the default minute when the suite runs in parallel.
    test.setTimeout(180_000)
    await returningVisitor(context, { theme })
    const problems = watchConsole(page)
    for (const r of ROUTES) {
      await page.goto(r)
      await expect(page.getByRole('heading', { level: 1 }).or(page.getByRole('heading', { level: 2 })).first()).toBeAttached()
      await page.waitForLoadState('networkidle')
      await expectNoSeriousAxe(page, `${r} (${theme})`)
    }
    // The newest answers with every row open: the correction budget, the weather notes, the sea at Griffin-1's zone.
    for (const r of ['/missions/blue-ghost-m1/trip', '/missions/im-1/launch', '/missions/griffin-1/return']) {
      await page.goto(r)
      await page.waitForLoadState('networkidle')
      for (const s of await page.locator('main summary').all()) await s.click()
      await expectNoSeriousAxe(page, `${r} with every row open (${theme})`)
    }
    // Settings with every project row open, a parameter's form and history among them.
    await page.goto('/missions')
    await page.getByRole('button', { name: 'Settings' }).click()
    const sheet = page.getByRole('dialog', { name: 'Settings' })
    await expect(sheet.locator('summary', { hasText: 'Parameters' })).toContainText(/\d of \d entered/)
    for (const s of await sheet.locator('summary').all()) await s.click()
    await sheet.getByRole('button', { name: /for Battery limit/ }).click()
    await expect(sheet.getByText('Change history')).toBeVisible()
    await expectNoSeriousAxe(page, `settings with every row open (${theme})`)
    expect(problems).toEqual([])
  })
}

test('every closed row opens, and axe passes with them open', async ({ page, context }) => {
  await returningVisitor(context)
  for (const r of [
    '/missions/im-2',
    '/missions/im-2/ready',
    '/missions/im-2/launch',
    '/missions/im-2/trip',
    '/missions/im-2/contact',
    '/missions/im-2/return',
    '/site',
    '/skyline',
    '/plan',
  ]) {
    await page.goto(r)
    await page.waitForLoadState('networkidle')
    for (const s of await page.locator('main summary').all()) await s.click()
    await expectNoSeriousAxe(page, `${r} with every row open`)
  }
})

test('a number says what it means when its label is pressed', async ({ page, context }) => {
  await returningVisitor(context)
  await page.goto('/site')
  const label = page.getByRole('button', { name: /^Time in contact with Earth/ })
  await expect(label).toHaveAttribute('aria-expanded', 'false')
  await expect(page.getByText('Also called Direct-to-Earth (DTE) contact.')).toBeHidden()
  await label.click()
  await expect(label).toHaveAttribute('aria-expanded', 'true')
  await expect(page.getByText('Also called Direct-to-Earth (DTE) contact.')).toBeVisible()
})

test('axe and the fixed tab bar on a phone', async ({ page, context }) => {
  await returningVisitor(context)
  await page.setViewportSize({ width: 375, height: 812 })
  const tabs = page.getByRole('navigation', { name: 'Views' }).last()
  for (const r of [
    '/missions?type=volatiles',
    '/missions/im-2',
    '/missions/im-2/ready',
    '/missions/im-2/launch',
    '/missions/im-2/trip',
    '/missions/im-2/contact',
    '/missions/im-2/return',
    '/missions/im-1/trip',
    '/missions/im-1/launch',
    '/missions/griffin-1/launch',
    '/missions/im-1/return',
    '/missions/griffin-1/return',
    '/site',
    '/compare',
  ]) {
    await page.goto(r)
    await page.waitForLoadState('networkidle')
    await expect(tabs.getByRole('link')).toHaveCount(5)
    await expect(tabs).toHaveCSS('position', 'fixed')
    await expectNoSeriousAxe(page, `${r} at 375 px`)
    // Nothing runs off the side: no sideways scroll on a phone.
    expect(await page.evaluate(() => document.documentElement.scrollWidth), `${r} scrolls sideways at 375 px`).toBeLessThanOrEqual(375)
  }
  // Rows open on a phone: the correction budget's table, the weather notes and space weather, and the capsule
  // model's check with its source links still fit; so does the limits form.
  for (const r of ['/missions/blue-ghost-m1/trip', '/missions/griffin-1/return', '/missions/im-1/launch']) {
    await page.goto(r)
    await page.waitForLoadState('networkidle')
    for (const s of await page.locator('main summary').all()) await s.click()
    expect(await page.evaluate(() => document.documentElement.scrollWidth), `${r} with rows open scrolls sideways at 375 px`).toBeLessThanOrEqual(375)
    await expectNoSeriousAxe(page, `${r} with rows open at 375 px`)
  }
  await page.getByRole('button', { name: 'Enter the team’s limits' }).click()
  const limits = page.getByRole('dialog', { name: 'Team weather limits' })
  await expect(limits.getByLabel('Note (optional)').first()).toBeVisible()
  expect(await limits.evaluate((d) => d.scrollWidth - d.clientWidth), 'the limits form scrolls sideways at 375 px').toBeLessThanOrEqual(0)
  await expectNoSeriousAxe(page, 'the team weather limits form at 375 px')
  await limits.getByRole('button', { name: 'Close' }).first().click()
  await page.goto('/compare')
  await page.waitForLoadState('networkidle')
  // The last line of the page is never under the tab bar.
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
  const footer = page.getByText('Estimates from a terrain map', { exact: false })
  const [f, t] = await Promise.all([footer.boundingBox(), tabs.boundingBox()])
  expect(f!.y + f!.height).toBeLessThanOrEqual(t!.y + 1)

  // With the guide open, it sits above the tab bar, and the page still ends above both.
  await page.getByRole('button', { name: 'Guide', exact: true }).click()
  const guide = page.getByRole('region', { name: 'Guide' })
  await expect(guide).toBeVisible()
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
  const [f2, g, t2] = await Promise.all([footer.boundingBox(), guide.boundingBox(), tabs.boundingBox()])
  expect(g!.y + g!.height).toBeLessThanOrEqual(t2!.y + 1)
  expect(f2!.y + f2!.height).toBeLessThanOrEqual(g!.y + 1)
  await expectNoSeriousAxe(page, '/compare at 375 px with the guide open')
})

test('settings on a phone: every project row and a parameter form fit, with no sideways scroll', async ({ page, context }) => {
  await returningVisitor(context)
  await page.setViewportSize({ width: 375, height: 812 })
  await page.goto('/missions')
  await page.getByRole('button', { name: 'Settings' }).click()
  const sheet = page.getByRole('dialog', { name: 'Settings' })
  await expect(sheet.locator('summary', { hasText: 'Parameters' })).toContainText(/\d of \d entered/)
  for (const s of await sheet.locator('summary').all()) await s.click()
  await sheet.getByRole('button', { name: /for Lowest Sun height/ }).click()
  const value = sheet.getByLabel('Value, in degrees')
  await expect(value).toBeVisible()
  const box = await value.boundingBox()
  expect(box!.x + box!.width).toBeLessThanOrEqual(375)
  expect(box!.height).toBeGreaterThanOrEqual(44)
  expect(await sheet.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375)
  await expectNoSeriousAxe(page, 'settings at 375 px with every row open')
})

test('mission filters live in the URL; the back button undoes a chip', async ({ page, context }) => {
  await returningVisitor(context)
  await page.goto('/missions')
  const count = page.locator('[aria-live="polite"]').filter({ hasText: 'missions' }).first()
  await page.getByRole('button', { name: 'Instruments' }).click()
  await page.getByRole('button', { name: 'Volatiles' }).click()
  await page.getByRole('button', { name: 'Upcoming' }).click()
  await expect(page).toHaveURL(/type=volatiles.*status=upcoming|status=upcoming.*type=volatiles/)
  await expect(count).toHaveText('Showing 3 of 20 missions')
  await page.goBack()
  await expect(count).toHaveText('Showing 5 of 20 missions')
  await page.goBack()
  await expect(count).toHaveText('Showing 20 of 20 missions')
  await page.goForward()
  await expect(page.getByRole('button', { name: 'Volatiles' })).toHaveAttribute('aria-pressed', 'true')
})

test('empty state names the filters and relaxes them in one click', async ({ page, context }) => {
  await returningVisitor(context)
  await page.goto('/missions?status=flown&provider=Blue%20Origin')
  await expect(page.getByText('No missions match these filters')).toBeVisible()
  await expect(page.locator('main')).toContainText('provider Blue Origin')
  await page.getByRole('button', { name: 'Remove Blue Origin' }).click()
  await expect(page).not.toHaveURL(/provider=/)
  await expect(page.getByText('No missions match these filters')).toBeHidden()
  await page.goto('/missions?status=flown&provider=Blue%20Origin')
  await page.getByRole('button', { name: 'Clear filters' }).click()
  await expect(page.locator('[aria-live="polite"]').filter({ hasText: 'missions' }).first()).toHaveText(
    'Showing 20 of 20 missions',
  )
})

test('the timeline has a table twin, by button and by T; the shortcut can be switched off', async ({ page, context }) => {
  await returningVisitor(context)
  await page.goto('/missions')
  const table = page.getByRole('table', { name: /Every mission shown/ })
  await openRow(page, 'Timeline')
  await page.getByRole('button', { name: 'Read the timeline as a table' }).click()
  await expect(table).toBeVisible()
  await expect(table.getByRole('row')).toHaveCount(21)
  await page.locator('main').click({ position: { x: 5, y: 5 } })
  await page.keyboard.press('t')
  await expect(table).toBeHidden()
  await page.keyboard.press('t')
  await expect(table).toBeVisible()

  // WCAG 2.1.4: the settings sheet turns single-key shortcuts off.
  await page.getByRole('button', { name: 'Settings' }).click()
  const sheet = page.getByRole('dialog', { name: 'Settings' })
  await expect(sheet).toBeVisible()
  await expectNoSeriousAxe(page, 'settings sheet')
  await sheet.getByRole('group', { name: 'Keyboard shortcuts' }).getByRole('button', { name: 'Off' }).click()
  await page.keyboard.press('Escape')
  await expect(sheet).toBeHidden()
  await page.keyboard.press('t')
  await expect(table).toBeVisible()
  // …and the choice is remembered.
  await page.reload()
  await openRow(page, 'Timeline')
  await page.getByRole('button', { name: 'Read the timeline as a table' }).click()
  await page.keyboard.press('t')
  await expect(page.getByRole('table', { name: /Every mission shown/ })).toBeVisible()
})

test('an unknown mission is a 404 panel with a way back', async ({ page, context }) => {
  await returningVisitor(context)
  await page.goto('/missions/nope')
  await expect(page.locator('main')).toContainText('What still works')
  await page.getByRole('button', { name: 'Back to missions' }).click()
  await expect(page).toHaveURL(/\/missions$/)
})

test('reduced motion swaps play for step buttons, decided in code', async ({ page, context }) => {
  await returningVisitor(context, { motion: 'reduced' })
  await page.goto('/site')
  await expect(page.getByRole('button', { name: 'Play through the dates' })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Step forward six hours' })).toBeVisible()
  const slider = page.getByRole('slider')
  await expect(slider).toHaveAttribute('aria-valuetext', /^Day \d+, \d+ \w+, \d\d:\d\d UTC$/)
})
