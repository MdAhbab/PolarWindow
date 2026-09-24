import AxeBuilder from '@axe-core/playwright'
import { expect, type BrowserContext, type Page } from '@playwright/test'

const API = process.env.E2E_API_BASE ?? 'http://localhost:8000/api/v1'

/**
 * A project manager's session from the one-click sign-in, as the landing
 * page's button gets it. Asked for once per test, from Node, so a test that
 * blocks the API in the browser still starts signed in.
 */
export async function demoSession(context: BrowserContext) {
  const r = await context.request.post(`${API}/auth/demo`)
  expect(r.ok(), 'the one-click sign-in answered').toBeTruthy()
  const b = (await r.json()) as { token: string; role_name: string; expires_at: string }
  return { token: b.token, roleName: b.role_name, expiresAt: Date.parse(b.expires_at), offline: false }
}

/**
 * Signed in, on a known detail level, with the guide closed: a returning
 * project manager. Only on the first load, so a reload sees what the test
 * chose since. `guide: true` leaves the guide as a first visit finds it (open).
 */
export async function returningVisitor(
  context: BrowserContext,
  face: 'public' | 'educator' | 'planner' = 'public',
  { theme = 'dark', motion = 'full', guide = false }: { theme?: 'dark' | 'light'; motion?: 'full' | 'reduced'; guide?: boolean } = {},
) {
  const session = await demoSession(context)
  await context.addInitScript(
    ([f, t, m, g, sess]) => {
      if (localStorage.getItem('pw-session')) return
      localStorage.setItem('pw-session', JSON.stringify(sess))
      localStorage.setItem('pw-prefs', JSON.stringify({ face: f, theme: t, motion: m, shortcuts: true }))
      if (!g) localStorage.setItem('pw-guide', JSON.stringify({ open: false, step: 0 }))
    },
    [face, theme, motion, guide, session] as const,
  )
}

/** Console errors and warnings, collected for the whole test. */
export function watchConsole(page: Page): string[] {
  const problems: string[] = []
  page.on('console', (m) => {
    // The GPU driver's own note when a test reads the front page's WebGL
    // canvas back (axe, screenshots): the browser's, not the page's.
    if (/GL Driver Message/.test(m.text())) return
    if (m.type() === 'error' || m.type() === 'warning') problems.push(`${m.type()}: ${m.text()}`)
  })
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`))
  return problems
}

/** WCAG 2.1 A and AA through axe; serious and critical findings fail the test. */
export async function expectNoSeriousAxe(page: Page, where: string) {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze()
  const bad = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  const report = bad
    .map((v) => `${v.impact} ${v.id}: ${v.help}\n  ${v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join('\n  ')}`)
    .join('\n')
  expect(bad, `axe on ${where}:\n${report}`).toEqual([])
}

/** Client-side navigation, as a link click would do it, without leaving the app. */
export async function goClient(page: Page, path: string) {
  await page.evaluate((p) => {
    history.pushState({}, '', p)
    dispatchEvent(new PopStateEvent('popstate'))
  }, path)
}
