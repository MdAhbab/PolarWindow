/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  worker: { format: 'es' },
  // The front page's own chunk carries three.js and GSAP (about 180 KB
  // gzipped); it loads only on `/`, and the dashboard never downloads it.
  build: { chunkSizeWarningLimit: 700 },
  // Unit and component tests only; the browser tests in e2e/ run under Playwright.
  test: { include: ['src/**/*.test.{ts,tsx}'] },
})
