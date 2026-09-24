import AxeBuilder from '@axe-core/playwright'
import { expect, type BrowserContext, type Page } from '@playwright/test'

/** Skip the first-visit story and start on a known face, as a returning visitor. */
export async function returningVisitor(context: BrowserContext, face: 'public' | 'educator' | 'planner' = 'public') {
  // Only on the first load: a reload must see what the test chose since.
  await context.addInitScript((f) => {
    if (localStorage.getItem('pw-visited')) return
    localStorage.setItem('pw-visited', '1')
    localStorage.setItem('pw-prefs', JSON.stringify({ face: f, theme: 'dark', motion: 'full', shortcuts: true }))
  }, face)
}

/** Console errors and warnings, collected for the whole test. */
export function watchConsole(page: Page): string[] {
  const problems: string[] = []
  page.on('console', (m) => {
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
