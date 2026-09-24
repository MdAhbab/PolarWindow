import { expect, test } from '@playwright/test'
import { expectNoSeriousAxe, returningVisitor, watchConsole } from './helpers'

const ROUTES = [
  '/',
  '/missions',
  '/missions/im-2',
  '/missions/blue-ghost-m1',
  '/missions/cs-8',
  '/map',
  '/clocks',
  '/compare',
  '/horizon',
  '/blackout',
  '/report',
]

for (const theme of ['dark', 'light'] as const) {
  for (const face of ['public', 'planner'] as const) {
    test(`axe: every route, ${theme} theme, ${face === 'public' ? 'Simple' : 'Expert'}`, async ({ page, context }) => {
      await returningVisitor(context, face, { theme })
      const problems = watchConsole(page)
      for (const r of ROUTES) {
        await page.goto(r)
        await expect(page.getByRole('heading', { level: 1 }).or(page.getByRole('heading', { level: 2 })).first()).toBeVisible()
        await page.waitForLoadState('networkidle')
        await expectNoSeriousAxe(page, `${r} (${theme}, ${face})`)
      }
      expect(problems).toEqual([])
    })
  }
}

test('axe and the fixed tab bar on a phone', async ({ page, context }) => {
  await returningVisitor(context)
  await page.setViewportSize({ width: 375, height: 812 })
  const tabs = page.getByRole('navigation', { name: 'Views' }).last()
  for (const r of ['/missions?type=volatiles', '/missions/im-2', '/clocks', '/compare']) {
    await page.goto(r)
    await page.waitForLoadState('networkidle')
    await expect(tabs.getByRole('link')).toHaveCount(5)
    await expect(tabs).toHaveCSS('position', 'fixed')
    await expectNoSeriousAxe(page, `${r} at 375 px`)
  }
  // The last line of the page is never under the tab bar.
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
  const footer = page.getByText('All figures are estimates', { exact: false })
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

test('mission filters live in the URL; the back button undoes a chip', async ({ page, context }) => {
  await returningVisitor(context)
  await page.goto('/missions')
  const count = page.locator('[aria-live="polite"]').filter({ hasText: 'missions' }).first()
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
  await returningVisitor(context, 'planner', { motion: 'reduced' })
  await page.goto('/clocks')
  await expect(page.getByRole('button', { name: 'Play through the dates' })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Step forward six hours' })).toBeVisible()
  const slider = page.getByRole('slider')
  await expect(slider).toHaveAttribute('aria-valuetext', /^Day \d+, \d+ \w+, \d\d:\d\d UTC$/)
})
