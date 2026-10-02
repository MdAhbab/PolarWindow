/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  worker: { format: 'es' },
  // three.js is one chunk, shared by the front page's Moon and the
  // dashboard's scenes, and fetched only by them: a dashboard page loads it
  // when one of its scenes comes near the screen, never with the page.
  build: {
    chunkSizeWarningLimit: 700,
    // The logo's files stay files: inlined, both themes' versions would ride in the main bundle.
    assetsInlineLimit: (file: string) => (file.includes('/assets/brand/') ? false : undefined),
    rollupOptions: { output: { manualChunks: (id: string) => (id.includes('node_modules/three/') ? 'three' : undefined) } },
  },
  // Unit and component tests only; the browser tests in e2e/ run under Playwright.
  test: { include: ['src/**/*.test.{ts,tsx}'] },
})
