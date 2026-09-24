import { expect, test, type BrowserContext } from '@playwright/test'
import { goClient, returningVisitor } from './helpers'

/**
 * The Listen control (U16). Speech itself is stubbed: headless browsers have
 * no voices, and what is under test is the control, not the engine.
 */
async function stubSpeech(context: BrowserContext) {
  await context.addInitScript(() => {
    const spoken: string[] = []
    let queue: SpeechSynthesisUtterance[] = []
    const synth = {
      speak(u: SpeechSynthesisUtterance) {
        queue.push(u)
        spoken.push(u.text)
        if (queue.length === 1) setTimeout(() => u.onstart?.(new Event('start') as SpeechSynthesisEvent), 10)
      },
      cancel() {
        queue = []
      },
      getVoices: () => [],
    }
    Object.defineProperty(window, 'speechSynthesis', { value: synth, configurable: true })
    ;(window as unknown as { __spoken: string[] }).__spoken = spoken
  })
}

for (const where of [
  { path: '/clocks', name: /summary of this site/ },
  { path: '/missions/im-2', name: /summary of this site/ },
  { path: '/compare?sites=connecting-ridge,de-gerlache-rim,malapert-massif&rank=night', name: /summary of this comparison/ },
]) {
  test(`Listen on ${where.path.split('?')[0]}`, async ({ page, context }) => {
    await returningVisitor(context)
    await stubSpeech(context)
    await page.goto(where.path)
    await page.waitForLoadState('networkidle')
    const listen = page.getByRole('button', { name: where.name })
    await expect(listen).toHaveAttribute('aria-pressed', 'false')
    // Never auto-plays.
    expect(await page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken.length)).toBe(0)

    // Something the reader is looking at, near the control.
    const anchor = page.getByRole('slider').first()
    const before = await anchor.boundingBox()
    await listen.click()
    await expect(page.getByRole('button', { name: 'Stop the summary' })).toHaveAttribute('aria-pressed', 'true')
    await expect(page.getByRole('region', { name: 'Summary playing' })).toBeVisible()
    // Captions float: nothing on the page moves.
    expect(await anchor.boundingBox()).toEqual(before)
    const said = await page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken.join(' '))
    expect(said).not.toMatch(/[≈±%]|NaN|undefined/)
    if (where.path.startsWith('/compare')) {
      expect(said).not.toMatch(/\bbest\b/)
      expect(said).toContain("can't be ranked")
      expect(said).toContain('at least')
    }

    await page.keyboard.press('Escape')
    await expect(page.getByRole('region', { name: 'Summary playing' })).toBeHidden()
    await page.keyboard.press('Alt+KeyS')
    await expect(page.getByRole('region', { name: 'Summary playing' })).toBeVisible()
    await page.keyboard.press('Alt+KeyS')
    await expect(page.getByRole('region', { name: 'Summary playing' })).toBeHidden()

    // A hidden tab and a new screen both stop the voice.
    await listen.click()
    await page.evaluate(() => {
      Object.defineProperty(document, 'hidden', { value: true, configurable: true })
      document.dispatchEvent(new Event('visibilitychange'))
    })
    await expect(page.getByRole('region', { name: 'Summary playing' })).toBeHidden()
    await page.evaluate(() => Object.defineProperty(document, 'hidden', { value: false, configurable: true }))
    await listen.click()
    await goClient(page, '/missions')
    await expect(page.getByRole('region', { name: 'Summary playing' })).toBeHidden()
  })
}

test('without speech synthesis, Listen opens the transcript', async ({ page, context }) => {
  await returningVisitor(context)
  await context.addInitScript(() => {
    delete (window as unknown as { speechSynthesis?: unknown }).speechSynthesis
  })
  await page.goto('/clocks')
  await page.getByRole('button', { name: /summary of this site/ }).click()
  await expect(page.getByRole('button', { name: 'Hide text' })).toBeVisible()
  await expect(page.locator('main')).toContainText('These are planning estimates, not official values.')
})
