import { expect, test } from '@playwright/test'
import { returningVisitor, watchConsole } from './helpers'

/**
 * A scene gives its graphics context back when its page goes. Browsers keep
 * about sixteen live contexts and then drop the oldest, so a scene that only
 * frees its resources leaves one behind on every visit.
 *
 * The pages are changed inside one document, as a person moving between a
 * mission's steps does: a full load would throw every context away by itself
 * and prove nothing.
 */
test('WebGL contexts: each scene owns a canvas and gives its graphics context back when it goes', async ({
  page,
  context,
}) => {
  test.setTimeout(120_000)
  await returningVisitor(context)

  await context.addInitScript(() => {
    const counts = { made: 0, lost: 0 }
    ;(window as unknown as { __pwGl: typeof counts }).__pwGl = counts
    const original = HTMLCanvasElement.prototype.getContext as (
      this: HTMLCanvasElement,
      id: string,
      options?: unknown,
    ) => RenderingContext | null
    const seen = new WeakSet<HTMLCanvasElement>()
    HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, id: string, options?: unknown) {
      const made = original.call(this, id, options)
      if (made && (id === 'webgl' || id === 'webgl2') && !seen.has(this)) {
        seen.add(this)
        counts.made++
        this.addEventListener('webglcontextlost', () => counts.lost++, { once: true })
      }
      return made
    } as typeof HTMLCanvasElement.prototype.getContext
  })

  const problems = watchConsole(page)
  const counts = () => page.evaluate(() => (window as unknown as { __pwGl: { made: number; lost: number } }).__pwGl)

  /** Another page of the app, without loading the document again. */
  const visit = async (path: string) => {
    await page.evaluate((to) => {
      window.history.pushState({}, '', to)
      window.dispatchEvent(new PopStateEvent('popstate'))
    }, path)
    await expect(page).toHaveURL(new RegExp(`${path.replace(/[/]/g, '\\/')}$`))
    // A scene starts when the browser is idle and its frame is near the
    // viewport: walk down the page so every frame has been near it.
    await page.evaluate(async () => {
      const step = window.innerHeight
      for (let y = 0; y <= document.documentElement.scrollHeight; y += step) {
        window.scrollTo(0, y)
        await new Promise((r) => setTimeout(r, 120))
      }
    })
    await page.waitForTimeout(1500)
  }

  await page.goto('/missions')
  const scenes = ['/missions/im-2', '/missions/im-2/trip', '/missions/im-2/surface', '/missions/im-2/return']
  for (let round = 0; round < 3; round++) {
    for (const path of scenes) await visit(path)
  }
  const during = await counts()
  expect(during.made, 'the pages visited drew at least one scene').toBeGreaterThan(1)

  await visit('/missions')
  const after = await counts()
  expect(after.made - after.lost, `contexts still alive with no scene on the page (${JSON.stringify(after)})`).toBe(0)
  expect(problems.filter((p) => /too many active webgl contexts/i.test(p))).toEqual([])
})
