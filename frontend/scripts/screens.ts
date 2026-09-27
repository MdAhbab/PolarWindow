/**
 * Screenshots of the mission hub and each step the service answers, on a
 * desktop and a 375 px phone, into e2e/__screens__/ (dark theme, guide closed).
 *
 *   npm run screens           # API on :8000 and the dev server on :5174
 *
 * A step still being worked out (202) is waited for, so each picture shows
 * the answer, not the progress panel. APP_URL and API_BASE override the two
 * addresses; SCREENS_OUT writes the pictures somewhere else.
 */
import { mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium, type Page } from '@playwright/test'

const APP = process.env.APP_URL ?? 'http://localhost:5174'
const API = process.env.API_BASE ?? 'http://localhost:8000/api/v1'
const OUT = process.env.SCREENS_OUT ?? join(dirname(fileURLToPath(import.meta.url)), '..', 'e2e', '__screens__')

/** The hub (Landing open, the surface stay) and the steps the service answers. */
const PAGES: [name: string, path: string][] = [
  ['hub-im-2', '/missions/im-2'],
  ['ready-im-2', '/missions/im-2/ready'],
  ['launch-im-1-flown', '/missions/im-1/launch'],
  ['launch-griffin-1-calendar', '/missions/griffin-1/launch'],
  ['trip-im-2', '/missions/im-2/trip'],
  ['trip-im-1-with-gaps', '/missions/im-1/trip'],
  ['contact-im-2', '/missions/im-2/contact'],
]

async function settle(page: Page) {
  await page.waitForLoadState('networkidle')
  // Follow a step being worked out until its answer is on screen.
  // The step's progress panel (the step bar's "Working it out" is another step's).
  await page.getByRole('progressbar', { name: 'Progress' }).waitFor({ state: 'detached', timeout: 180_000 })
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(600)
}

async function main() {
  mkdirSync(OUT, { recursive: true })
  const signIn = (await (await fetch(`${API}/auth/demo`, { method: 'POST' })).json()) as {
    token: string
    role_name: string
    expires_at: string
    user?: { id: number; name: string; team: string | null }
  }
  const session = {
    token: signIn.token,
    roleName: signIn.role_name,
    expiresAt: Date.parse(signIn.expires_at),
    offline: false,
    user: signIn.user,
  }
  const browser = await chromium.launch()
  for (const [device, viewport] of [
    ['desktop', { width: 1440, height: 900 }],
    ['phone', { width: 375, height: 812 }],
  ] as const) {
    const context = await browser.newContext({ viewport, colorScheme: 'dark', deviceScaleFactor: 1 })
    await context.addInitScript((sess) => {
      localStorage.setItem('pw-session', JSON.stringify(sess))
      localStorage.setItem('pw-guide', JSON.stringify({ open: false, step: 0 }))
      localStorage.setItem('pw-prefs', JSON.stringify({ face: 'planner', theme: 'dark', motion: 'reduced', shortcuts: true }))
    }, session)
    const page = await context.newPage()
    for (const [name, path] of PAGES) {
      await page.goto(`${APP}${path}`)
      await settle(page)
      await page.screenshot({ path: join(OUT, `${name}.${device}.png`), fullPage: true })
    }
    // Settings → Project, the parameters and the risk scale open.
    await page.goto(`${APP}/missions`)
    await settle(page)
    await page.getByRole('button', { name: 'Settings' }).click()
    const sheet = page.getByRole('dialog', { name: 'Settings' })
    for (const title of ['Parameters', 'Risk scale']) await sheet.locator('summary', { hasText: title }).click()
    await sheet.locator('summary', { hasText: 'Parameters' }).scrollIntoViewIfNeeded()
    await settle(page)
    await page.screenshot({ path: join(OUT, `settings-project.${device}.png`) })
    await context.close()
  }
  await browser.close()
  console.log(`Saved ${(PAGES.length + 1) * 2} screenshots to ${OUT}`)
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
