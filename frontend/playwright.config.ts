import { defineConfig, devices } from '@playwright/test'

/**
 * End-to-end tests (`npm run e2e`). They drive the real app against the real
 * API on :8000, so start the backend first (see README); the dev server is
 * started here if one is not already running on :5174.
 *
 * E2E_BASE_URL points them at another build, for example a `vite preview` of
 * the snapshot build on :4173.
 */
const baseURL = process.env.E2E_BASE_URL ?? 'http://localhost:5174'

export default defineConfig({
  testDir: 'e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL,
    viewport: { width: 1440, height: 900 },
    colorScheme: 'dark',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } }],
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: 'npm run dev -- --port 5174 --strictPort',
        url: 'http://localhost:5174',
        reuseExistingServer: true,
        timeout: 60_000,
      },
})
