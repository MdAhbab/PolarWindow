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
 * APP_URL and API_BASE override the two addresses.
 */
import { mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium, type Page } from '@playwright/test'

const APP = process.env.APP_URL ?? 'http://localhost:5174'
const API = process.env.API_BASE ?? 'http://localhost:8000/api/v1'
const OUT = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'snapshot')

interface Entry {
  file: string
  status: number
}
const entries: Record<string, Entry> = {}
let n = 0

function keyOf(method: string, url: string, body: string | null): string | null {
  if (!url.startsWith(API)) return null
  const path = url.slice(API.length)
  if (path.startsWith('/tiles/')) return null
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
      if (!key || entries[key] || !(res.headers()['content-type'] ?? '').includes('json')) return
      const file = `r/${String(++n).padStart(4, '0')}.json`
      entries[key] = { file, status: res.status() }
      writeFileSync(join(OUT, file), JSON.stringify(await res.json()))
    } catch {
      /* a response the page abandoned (a superseded request): not saved */
    }
  })
}

async function settle(page: Page) {
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(400)
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
  await context.addInitScript(() => {
    localStorage.setItem('pw-visited', '1')
    localStorage.setItem('pw-prefs', JSON.stringify({ face: 'planner', theme: 'dark', motion: 'full', shortcuts: true }))
  })
  const page = await context.newPage()
  await record(page)

  // The candidate sites at the default window, on every screen.
  for (const path of ['/story', '/missions', '/map', '/clocks', '/horizon', '/blackout', '/report', '/compare']) {
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
    await page.getByRole('button', { name: 'Open in Site view' }).click()
    await settle(page)
    for (const path of ['/horizon', '/blackout', '/report', '/missions']) {
      await page.evaluate((p) => {
        history.pushState({}, '', p)
        dispatchEvent(new PopStateEvent('popstate'))
      }, path)
      await settle(page)
    }
    await visit(page, `/missions/${m.id}`)
    await page.getByRole('button', { name: 'Compare with nearby candidates' }).click()
    await settle(page)
    for (const rank of ['Time in the Sun', 'Time it can call home', "Longest time it can't call home", 'Longest night']) {
      await page.getByRole('button', { name: rank, exact: true }).click()
      await settle(page)
    }
  }
  await visit(page, '/missions/nope')

  // The demo's dates: every month for IM-2 and for the Mons Mouton missions.
  for (const id of ['im-2', 'blue-moon-mk1-viper']) {
    await visit(page, `/missions/${id}`)
    await everyMonth(page)
    await page.getByRole('button', { name: 'Open in Site view' }).click()
    await settle(page)
  }

  // The agents, as the video asks them.
  await visit(page, '/missions')
  await page.getByRole('button', { name: 'Ask about missions' }).click()
  await page
    .getByLabel('Your question')
    .fill('Which south-polar CLPS targets carry volatiles instruments, and what is their longest night?')
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  await page.getByText('Summary from measurements').waitFor()
  await page.getByRole('button', { name: 'AI activity log' }).click()
  await settle(page)
  await page.keyboard.press('Escape')
  for (const id of ['im-2', 'blue-ghost-m1', 'blue-moon-mk1-viper']) {
    await visit(page, `/missions/${id}`)
    await page.getByText('What is it like at this site?').click()
    await page.getByRole('button', { name: 'Explain this site' }).click()
    await page.getByText(/Summary from measurements|AI answer/).first().waitFor()
  }
  await visit(page, '/compare')
  await page.getByLabel('The requirement, in your own words').fill('200 W solar and at least 4 hours of Earth contact per day')
  await page.getByRole('button', { name: 'Find sites' }).click()
  await page.getByText(/Summary from measurements|AI answer/).first().waitFor()
  await visit(page, '/report')
  await page.getByRole('button', { name: 'Write the three briefs' }).click()
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
