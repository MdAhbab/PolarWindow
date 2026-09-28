/**
 * Save the API's answers along the demo path into public/snapshot/, for the
 * offline build (`npm run build:snapshot`) and the live build's fallback.
 *
 *   npm run snapshot          # API on :8000 and the dev server on :5174
 *
 * It does not guess which requests the app makes: it drives the real app
 * through every screen of the demo path in a headless browser and records the
 * requests the app actually sends, with the exact query strings and bodies it
 * will send again. Each answer is saved as received.
 *
 * APP_URL and API_BASE override the two addresses; SNAPSHOT_OUT writes the
 * copy somewhere else, for a trial run that leaves the saved one alone.
 */
import { mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium, type Page } from '@playwright/test'

const APP = process.env.APP_URL ?? 'http://localhost:5174'
const API = process.env.API_BASE ?? 'http://localhost:8000/api/v1'
const OUT = process.env.SNAPSHOT_OUT ?? join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'snapshot')

interface Entry {
  file: string
  status: number
}
const entries: Record<string, Entry> = {}
let n = 0
/** Answers whose bodies are still being read: settle() waits for them before the page moves on. */
const reading = new Set<Promise<void>>()
const pendingKeys = new Set<string>()
/** Seconds the service asked us to wait after refusing a request for our pace (429); null when none. */
let limited: number | null = null

function keyOf(method: string, url: string, body: string | null): string | null {
  if (!url.startsWith(API)) return null
  const path = url.slice(API.length)
  if (path.startsWith('/tiles/')) return null
  // A copy with no server has no sign-in and no project settings to save.
  if (path.startsWith('/auth/') || path.startsWith('/settings')) return null
  if (method === 'POST') return `POST ${path} ${body ?? 'null'}`
  return `GET ${path}`
}

async function record(page: Page) {
  page.on('response', async (res) => {
    const req = res.request()
    const url = req.url()
    try {
      const tile = url.startsWith(`${API}/tiles/`) && url.match(/\/tiles\/(\w+)\/(\d+)\/(\d+)\/(\d+)(?:\.png)?$/)
      if (tile) {
        if (res.status() !== 200) return
        const file = join(OUT, 'tiles', tile[1], tile[2], tile[3], `${tile[4]}.png`)
        mkdirSync(dirname(file), { recursive: true })
        writeFileSync(file, await res.body())
        return
      }
      const key = keyOf(req.method(), url, req.postData())
      if (!key || entries[key] || pendingKeys.has(key) || !(res.headers()['content-type'] ?? '').includes('json')) return
      // Refused for this script's own pace (site comparison: 60 a minute), not an answer:
      // not saved, and the step is asked again once the wait is over.
      if (res.status() === 429) {
        limited = Math.max(limited ?? 0, Number(res.headers()['retry-after'] ?? 60) || 60)
        return
      }
      // A section still being worked out (202) is not an answer; the copy
      // keeps only finished ones, so it never shows a job it cannot follow.
      if (res.status() === 202 || key.startsWith('GET /jobs/')) return
      // The entry is written only once its body is saved, so the index never
      // points at a file that is not there (a body the page dropped is asked again).
      pendingKeys.add(key)
      const read = (async () => {
        try {
          const body = await res.json()
          const file = `r/${String(++n).padStart(4, '0')}.json`
          writeFileSync(join(OUT, file), JSON.stringify(body))
          entries[key] = { file, status: res.status() }
        } catch {
          console.warn(`${key.slice(0, 100)}: its body was gone before it could be read; not saved`)
        } finally {
          pendingKeys.delete(key)
        }
      })()
      reading.add(read)
      void read.finally(() => reading.delete(read))
    } catch {
      /* a response the page abandoned (a superseded request): not saved */
    }
  })
}

async function settle(page: Page) {
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(400)
  // Every answer's body read before the page moves on and the browser drops it.
  await Promise.allSettled([...reading])
}

/**
 * Wait out a step being worked out, so its answer is on screen (and recorded).
 * One that never starts (no compute worker running) is left out, and said so.
 */
async function answered(page: Page, path: string) {
  try {
    // The step's progress panel (the step bar's "Working it out" is another step's).
    await page.getByRole('progressbar', { name: 'Progress' }).waitFor({ state: 'detached', timeout: 300_000 })
  } catch {
    console.warn(`${path}: still being worked out after 5 minutes (queued behind others, or no compute worker running); not saved`)
  }
  await settle(page)
}

async function visit(page: Page, path: string) {
  await page.goto(`${APP}${path}`)
  await settle(page)
}

/** Every month in a mission's strip, so the dates a viewer picks are there offline. */
async function everyMonth(page: Page) {
  const months = page.getByRole('option')
  const count = await months.count()
  for (let i = 0; i < count; i++) {
    await months.nth(i).click()
    await settle(page)
  }
}

async function main() {
  rmSync(OUT, { recursive: true, force: true })
  mkdirSync(join(OUT, 'r'), { recursive: true })
  const browser = await chromium.launch()
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  // Signed in as the landing page's button would, with the guide closed.
  const signIn = (await (await fetch(`${API}/auth/demo`, { method: 'POST' })).json()) as {
    token: string
    role_name: string
    expires_at: string
  }
  const session = { token: signIn.token, roleName: signIn.role_name, expiresAt: Date.parse(signIn.expires_at), offline: false }
  await context.addInitScript((sess) => {
    localStorage.setItem('pw-session', JSON.stringify(sess))
    localStorage.setItem('pw-guide', JSON.stringify({ open: false, step: 0 }))
    localStorage.setItem('pw-prefs', JSON.stringify({ face: 'planner', theme: 'dark', motion: 'full', shortcuts: true }))
  }, session)
  const page = await context.newPage()
  await record(page)

  // The candidate sites at the default window, on every screen.
  for (const path of ['/', '/missions', '/map', '/site', '/skyline', '/plan', '/report', '/compare']) {
    await visit(page, path)
  }
  await page.goto(`${APP}/map`)
  await page.getByRole('button', { name: 'Pole close-up', exact: true }).click()
  await settle(page)

  // The comparison the video ranks by longest night, and every ranking.
  for (const rank of ['sunlight', 'earth', 'night', 'blackout']) {
    await visit(page, `/compare?sites=connecting-ridge,de-gerlache-rim,malapert-massif&rank=${rank}`)
    await visit(page, `/compare?sites=connecting-ridge,malapert-massif,faustini-rim&rank=${rank}`)
  }

  // Every mission, its target at its own window, and where it leads.
  const missions = (await (await fetch(`${API}/missions`)).json()) as { items: { id: string; site_id: string | null }[] }
  for (const m of missions.items) {
    await visit(page, `/missions/${m.id}`)
    if (!m.site_id) continue
    await page.getByRole('button', { name: 'Open the site page' }).click()
    await settle(page)
    for (const path of ['/skyline', '/plan', '/report', '/missions']) {
      await page.evaluate((p) => {
        history.pushState({}, '', p)
        dispatchEvent(new PopStateEvent('popstate'))
      }, path)
      await settle(page)
    }
    const compare = async () => {
      await visit(page, `/missions/${m.id}`)
      await page.getByRole('button', { name: 'Compare with nearby sites' }).click()
      await settle(page)
      for (const rank of ['Time in sunlight', 'Time in contact with Earth', 'Longest time without contact', 'Longest night']) {
        await page.getByRole('button', { name: rank, exact: true }).click()
        await settle(page)
      }
    }
    await compare()
    // Asked too fast: wait as told, then ask again, so the copy holds answers, not refusals.
    for (let tries = 0; limited !== null && tries < 3; tries++) {
      const wait = limited
      limited = null
      console.warn(`/missions/${m.id}: comparison refused for pace; waiting ${wait} s`)
      await page.waitForTimeout(wait * 1000 + 500)
      await compare()
    }
  }
  await visit(page, '/missions/nope')

  // Every mission's six steps (Landing is the mission page above). A step the
  // service does not answer yet is saved as its error, which is what it said.
  // A step still being worked out (202) is followed until its answer comes, so
  // the copy holds the answer rather than nothing.
  const STEPS = ['ready', 'launch', 'trip', 'contact', 'return']
  for (const m of missions.items) {
    for (const step of STEPS) {
      await visit(page, `/missions/${m.id}/${step}`)
      await answered(page, `/missions/${m.id}/${step}`)
      // The rover row asks only when opened: open it, so the copy holds its answer too.
      const rover = page.locator('main summary', { hasText: 'Rover and lander line of sight' })
      if (step === 'contact' && (await rover.count())) {
        await rover.first().click()
        try {
          await page.getByTestId('rover-sight').or(page.getByText(/^Not available:/)).first().waitFor({ timeout: 300_000 })
        } catch {
          console.warn(`/missions/${m.id}/contact: the rover's line of sight did not come in 5 minutes; not saved`)
        }
        await settle(page)
      }
    }
  }

  // The demo's dates: every month for IM-2 and for the Mons Mouton missions.
  for (const id of ['im-2', 'blue-moon-mk1-viper']) {
    await visit(page, `/missions/${id}`)
    await everyMonth(page)
    await page.getByRole('button', { name: 'Open the site page' }).click()
    await settle(page)
  }

  // The agents, as the video asks them. Each sits in a closed row; opening the
  // site's row is itself the request.
  await visit(page, '/missions')
  await page.locator('summary', { hasText: 'Ask about missions and sites' }).click()
  await page
    .getByLabel('Your question')
    .fill('Which south-pole missions look for ice, and how long is their longest night?')
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  await page.getByText(/Summary from measurements|AI answer/).first().waitFor()
  await page.locator('summary', { hasText: /numbers, each checked/ }).first().click()
  await page.getByRole('button', { name: 'How the AI got this' }).first().click()
  await settle(page)
  await page.keyboard.press('Escape')
  for (const id of ['im-2', 'blue-ghost-m1', 'blue-moon-mk1-viper']) {
    await visit(page, `/missions/${id}`)
    await page.locator('summary', { hasText: 'What is it like at this site?' }).click()
    await page.getByText(/Summary from measurements|AI answer/).first().waitFor()
  }
  await visit(page, '/compare')
  await page.locator('summary', { hasText: 'Find sites that meet a requirement' }).click()
  await page.getByLabel('The requirement, in your own words').fill('200 W solar and at least 4 hours of Earth contact per day')
  await page.getByRole('button', { name: 'Find sites' }).click()
  await page.getByText(/Summary from measurements|AI answer/).first().waitFor()
  await visit(page, '/report')
  await page.getByRole('button', { name: 'Write a summary memo' }).click()
  await page.getByText(/Summary from measurements|AI answer/).first().waitFor()
  await settle(page)

  await browser.close()
  writeFileSync(
    join(OUT, 'index.json'),
    JSON.stringify({ captured_at: new Date().toISOString(), api_base: API, entries }, null, 1),
  )
  console.log(`Saved ${Object.keys(entries).length} answers to ${OUT}`)
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
