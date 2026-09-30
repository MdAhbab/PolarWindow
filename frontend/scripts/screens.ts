/**
 * Screenshots of the mission hub and each step the service answers, on a
 * desktop and a 375 px phone, into e2e/__screens__/ (dark theme, guide closed).
 *
 *   npm run screens           # API on :8000 and the dev server on :5174
 *
 * A step still being worked out (202) is waited for, so each picture shows
 * the answer, not the progress panel. APP_URL and API_BASE override the two
 * addresses; SCREENS_OUT writes the pictures somewhere else; SCREENS_ONLY
 * (names, comma-separated) retakes only those.
 *
 *   SCREENS_ONLY=trip-im-1-radiation,launch-im-1-space-weather npm run screens
 */
import { mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium, type Page } from '@playwright/test'

const APP = process.env.APP_URL ?? 'http://localhost:5174'
const API = process.env.API_BASE ?? 'http://localhost:8000/api/v1'
const OUT = process.env.SCREENS_OUT ?? join(dirname(fileURLToPath(import.meta.url)), '..', 'e2e', '__screens__')
const ONLY = process.env.SCREENS_ONLY?.split(',').map((x) => x.trim()).filter(Boolean)

/** The mission home, Surface and the steps the service answers; some with rows open. */
const PAGES: [name: string, path: string, open?: string[]][] = [
  ['hub-im-2', '/missions/im-2'],
  ['surface-im-2', '/missions/im-2/surface'],
  ['ready-im-2', '/missions/im-2/ready'],
  ['launch-im-1-flown', '/missions/im-1/launch'],
  ['launch-peregrine-m1-flown', '/missions/peregrine-m1/launch', ['The flight as launched']],
  ['launch-griffin-1-calendar', '/missions/griffin-1/launch'],
  ['trip-im-2', '/missions/im-2/trip'],
  ['trip-im-1-with-gaps', '/missions/im-1/trip'],
  ['trip-blue-ghost-m1-corrections', '/missions/blue-ghost-m1/trip', ['Burns', 'Corrections on the way']],
  ['launch-im-1-weather-rules', '/missions/im-1/launch', ['Weather rules for this launch', 'Team weather limits']],
  ['trip-blue-ghost-m1-radiation', '/missions/blue-ghost-m1/trip', ['Radiation on the way', 'How each was worked out']],
  ['launch-im-1-space-weather', '/missions/im-1/launch', ['Space weather now']],
  ['launch-im-1-flight', '/missions/im-1/launch', ['The flight as launched']],
  ['launch-griffin-1-flight', '/missions/griffin-1/launch', ['The flight for this opportunity']],
  ['trip-im-1-radiation', '/missions/im-1/trip', ['Radiation on the way']],
  ['trip-peregrine-m1-radiation', '/missions/peregrine-m1/trip', ['Radiation on the way']],
  ['contact-im-2', '/missions/im-2/contact'],
  ['contact-im-3-relay', '/missions/im-3/contact', ['Relays', 'Orbiters that could see the lander']],
  ['contact-im-2-orbiters', '/missions/im-2/contact', ['Orbiters that could see the lander']],
  ['contact-im-2-rover', '/missions/im-2/contact', ['Rover and lander line of sight']],
  ['contact-im-2-rover-values', '/missions/im-2/contact', ['Rover and lander line of sight', 'Antennas, radio and terrain']],
  ['contact-im-2-compare', '/missions/im-2/contact', ['Compare a relay', 'Download the contact plan']],
  ['return-im-1-land', '/missions/im-1/return'],
  ['return-im-2-droneship', '/missions/im-2/return'],
  ['return-griffin-1-planned', '/missions/griffin-1/return'],
  ['return-im-1-capsule-model', '/missions/im-1/return', ['The capsule model, checked against a real landing']],
]

async function settle(page: Page) {
  await page.waitForLoadState('networkidle')
  // Follow a step being worked out until its answer is on screen.
  // The step's progress panel (the step bar's "Working it out" is another step's).
  await page.getByRole('progressbar', { name: 'Progress' }).waitFor({ state: 'detached', timeout: 180_000 })
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(600)
}

/**
 * The screens that are not a page with rows open: the launch weather for a launch a few hours ahead, and Settings.
 * No planned opportunity is a few hours away, so the first is given the service's own answer for a launch time at
 * the Cape three hours ahead (the same endpoint, with `t0` and `pad`) in place of the one the screen asks for; the
 * words on it are the served ones.
 */
const extras: [name: string, run: (page: Page) => Promise<void>, fullPage: boolean][] = [
  [
    'launch-im-2-weather-forecasts',
    async (page) => {
      const hour = new Date(Math.ceil((Date.now() + 3 * 3_600_000) / 3_600_000) * 3_600_000).toISOString().replace('.000Z', 'Z')
      const served = await (await fetch(`${API}/missions/im-2/launch/weather?t0=${hour}&pad=ksc-lc-39a`)).text()
      const pattern = /\/missions\/im-2\/launch\/weather/
      await page.route(pattern, (route) =>
        route.fulfill({ status: 200, contentType: 'application/json', body: served, headers: { 'access-control-allow-origin': '*' } }),
      )
      await page.goto(`${APP}/missions/im-2/launch`)
      await settle(page)
      await page.locator('main summary', { hasText: 'Weather rules for this launch' }).first().click()
      await page.unroute(pattern)
    },
    true,
  ],
  [
    // Settings → Data sources, scrolled to the lightning mapper: its note says why it holds nothing.
    'settings-data-sources',
    async (page) => {
      await page.goto(`${APP}/missions`)
      await settle(page)
      await page.getByRole('button', { name: 'Settings' }).click()
      const sheet = page.getByRole('dialog', { name: 'Settings' })
      await sheet.getByRole('tab', { name: 'Data sources' }).click()
      await sheet.getByRole('listitem').filter({ hasText: /^glm, / }).last().scrollIntoViewIfNeeded()
    },
    false,
  ],
  [
    // Settings → Parameters: each value, who set it, and a way to change it.
    'settings-project',
    async (page) => {
      await page.goto(`${APP}/missions`)
      await settle(page)
      await page.getByRole('button', { name: 'Settings' }).click()
      const sheet = page.getByRole('dialog', { name: 'Settings' })
      await sheet.getByRole('tab', { name: 'Parameters' }).click()
      await sheet.getByRole('tabpanel').getByText(/of \d entered/).waitFor()
    },
    false,
  ],
]

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
    for (const [name, path, open = []] of PAGES.filter(([n]) => !ONLY || ONLY.includes(n))) {
      await page.goto(`${APP}${path}`)
      await settle(page)
      for (const title of open) await page.locator('main summary', { hasText: title }).first().click()
      if (open.length) await settle(page)
      await page.screenshot({ path: join(OUT, `${name}.${device}.png`), fullPage: true })
    }
    // Screens that need more than a page and its rows: each takes its own picture.
    const shot = (name: string, full: boolean) => page.screenshot({ path: join(OUT, `${name}.${device}.png`), fullPage: full })
    for (const [name, run, full] of extras.filter(([n]) => !ONLY || ONLY.includes(n))) {
      await run(page)
      await settle(page)
      await shot(name, full)
    }
    await context.close()
  }
  await browser.close()
  const n = ONLY ? ONLY.length : PAGES.length + extras.length
  console.log(`Saved ${n * 2} screenshots to ${OUT}`)
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
