/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  worker: { format: 'es' },
  // Unit and component tests only; the browser tests in e2e/ run under Playwright.
  test: { include: ['src/**/*.test.{ts,tsx}'] },
})
