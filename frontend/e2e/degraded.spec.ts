import { expect, test } from '@playwright/test'
import { expectNoSeriousAxe, openRow, returningVisitor, watchConsole } from './helpers'

/**
 * The degraded path: the service cannot be reached, so the app answers from
 * the offline copy (public/snapshot, `npm run snapshot`) and says so, and an
 * agent answers from the measurements alone.
 */
test('API unreachable: saved answers, the Saved copy badge, and a degraded agent', async ({ page, context }) => {
  await returningVisitor(context)
  // Every call to the service fails at the network, as with the service down.
  await context.route(/localhost:8000\//, (route) => route.abort('connectionrefused'))
  const problems = watchConsole(page)

  await page.goto('/missions')
  const badge = page.getByRole('status', { name: /^Data source: Saved copy/ })
  await expect(badge).toBeVisible()
  await expect(badge).toHaveText('Saved copy')
  await page.getByRole('button', { name: 'Instruments' }).click()
  await page.getByRole('button', { name: 'Volatiles' }).click()
  await expect(page.locator('[aria-live="polite"]').filter({ hasText: 'missions' }).first()).toHaveText(
    'Showing 5 of 20 missions',
  )
  await expectNoSeriousAxe(page, '/missions, offline')

  await page.getByRole('link', { name: /^IM-2,/ }).click()
  await expect(page.locator('main')).toContainText('6 Mar 2025, 17:30 UTC')
  await expect(page.locator('main')).toContainText('100% of the time')

  await page.getByRole('link', { name: 'Missions' }).first().click()
  await openRow(page, 'Ask about missions and sites')
  await page.getByLabel('Your question').fill('Which targets carry volatiles instruments?')
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  await expect(page.getByText(/^Summary from measurements \(no AI\)/)).toBeVisible()
  await expect(page.getByText('Built from the measurements')).toBeVisible()

  // A request the copy does not hold is still the real error, never a guess.
  await page.goto('/site')
  await openRow(page, 'Change the dates')
  await page.getByLabel('Start (UTC)').fill('2031-06-01')
  await expect(page.locator('main')).toContainText('Cannot reach the service that does the calculations')
  await expect(page.getByRole('progressbar')).toHaveCount(0)

  // Errors the browser logs for the refused requests are the scenario, not a fault.
  expect(problems.filter((p) => !/Failed to load resource|net::ERR_CONNECTION_REFUSED/.test(p))).toEqual([])
})
