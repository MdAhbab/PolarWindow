import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { BrowserContext, Route } from '@playwright/test'

/**
 * The lifecycle sections' answers from the contract fixtures
 * (`src/lib/api/__fixtures__/lifecycle`), served by route interception.
 *
 * Used while the backend's lifecycle endpoints are still being built: a test
 * that uses this is testing the screens against the contract's shapes, not
 * the live numbers, and says so in its name. Every other request goes to the
 * real API on :8000. `live: true` lets a lifecycle request through when the
 * API already answers it, and falls back to the fixture only on a 404.
 */
const DIR = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'lib', 'api', '__fixtures__', 'lifecycle')
const read = (name: string) => readFileSync(join(DIR, name), 'utf8')

const ROUTES: [RegExp, string][] = [
  [/\/missions\/[^/]+\/sections$/, 'sections.json'],
  [/\/missions\/[^/]+\/ready$/, 'ready.json'],
  [/\/missions\/[^/]+\/launch\/weather$/, 'launch-weather.json'],
  [/\/missions\/[^/]+\/launch$/, 'launch.json'],
  [/\/missions\/[^/]+\/trip$/, 'trip.json'],
  [/\/missions\/[^/]+\/contact\/rover$/, 'rover.json'],
  [/\/missions\/[^/]+\/contact$/, 'contact.json'],
  [/\/missions\/[^/]+\/return$/, 'return.json'],
  [/\/missions\/[^/]+\/parts$/, 'parts.json'],
  [/\/parts\/[^/]+\/impact$/, 'part-impact.json'],
  [/\/risk-scales$/, 'risk-scales.json'],
  [/\/landing-history$/, 'landing-history.json'],
  [/\/lessons$/, 'lessons.json'],
  [/\/ready\/items\/[^/]+\/history$/, 'history.json'],
  [/\/history$/, 'history.json'],
  [/\/feeds$/, 'feeds.json'],
  [/\/parameters$/, 'parameters.json'],
  [/\/jobs\/\d+$/, 'job-running.json'],
]

export interface FixtureOptions {
  /** Answer these sections with 202 and a running job instead of their answer. */
  working?: string[]
  /** Replace a fixture file by another for one route (e.g. `{ 'ready.json': 'ready-empty.json' }`). */
  swap?: Record<string, string>
  /** Try the live API first; use the fixture only where it answers 404. */
  live?: boolean
}

export async function serveLifecycleFixtures(context: BrowserContext, opts: FixtureOptions = {}) {
  await context.route(/localhost:8000\/api\/v1\//, async (route: Route) => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname.replace(/^\/api\/v1/, '')
    const hit = req.method() === 'GET' ? ROUTES.find(([re]) => re.test(path)) : undefined
    if (!hit) return route.fallback()
    if (opts.live) {
      const res = await route.fetch().catch(() => null)
      if (res && res.status() !== 404) return route.fulfill({ response: res })
    }
    const section = path.match(/\/missions\/[^/]+\/([a-z]+)$/)?.[1]
    if (section && opts.working?.includes(section)) {
      return route.fulfill({ status: 202, contentType: 'application/json', body: read('job-running.json'), headers: cors })
    }
    let file = hit[1]
    file = opts.swap?.[file] ?? file
    return route.fulfill({ status: 200, contentType: 'application/json', body: read(file), headers: cors })
  })
}

const cors = { 'access-control-allow-origin': '*' }

/**
 * A write the backend does not answer yet, answered as the contract says:
 * the browser's permission check first (a CORS preflight, since a write
 * carries the session), then the given JSON.
 */
export async function fulfillWrite(route: Route, json: unknown) {
  if (route.request().method() === 'OPTIONS') {
    return route.fulfill({
      status: 204,
      headers: {
        ...cors,
        'access-control-allow-methods': 'GET, POST, PUT, PATCH, DELETE',
        'access-control-allow-headers': 'authorization, content-type',
      },
    })
  }
  return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(json), headers: cors })
}
