import { expect, test } from '@playwright/test'
import { returningVisitor, watchConsole } from './helpers'
import { serveLifecycleFixtures } from './lifecycleFixtures'

test('WebGL contexts: each scene owns a canvas and gives its graphics context back when it goes', async ({
  page,
  context,
}) => {
  await returningVisitor(context)
  await serveLifecycleFixtures(context, { live: true })

  await context.addInitScript(() => {
    const pw = { made: 0, lost: 0 }
    // @ts-expect-error test window property
    window.__pw = pw

    const origGetContext = HTMLCanvasElement.prototype.getContext
    // @ts-expect-error override
    HTMLCanvasElement.prototype.getContext = function (
      contextId: string,
      ...args: unknown[]
    ) {
      const res = origGetContext.call(this, contextId, args[0])
      if (contextId === 'webgl' || contextId === 'webgl2') {
        if (res) {
          pw.made++
          this.addEventListener(
            'webglcontextlost',
            () => {
              pw.lost++
            },
            { once: true },
          )
        }
      }
      return res
    }
  })

  const problems = watchConsole(page)

  const urls = [
    '/missions/im-1',
    '/missions/im-2/trip',
    '/missions/artemis-iii/return',
    '/site',
  ]

  for (let i = 0; i < 5; i++) {
    for (const url of urls) {
      await page.goto(url)
      await page.waitForTimeout(300)
    }
  }

  await page.goto('/settings')
  await page.waitForTimeout(500)

  const counts = await page.evaluate(() => {
    // @ts-expect-error test window property
    return window.__pw as { made: number; lost: number }
  })

  expect(counts.made).toBeGreaterThan(0)
  expect(counts.made - counts.lost).toBeLessThanOrEqual(0)

  const webglWarnings = problems.filter((p) =>
    /too many active webgl contexts/i.test(p),
  )
  expect(webglWarnings).toEqual([])
})
