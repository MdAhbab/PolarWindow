/**
 * Rendering helpers for component tests (jsdom). The app's providers, with a
 * query client that never retries, and the two browser APIs jsdom lacks.
 */
import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { render } from '@testing-library/react'

export function installBrowserShims() {
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
}

export function renderApp(ui: ReactNode, { route = '/', client }: { route?: string; client?: QueryClient } = {}) {
  installBrowserShims()
  const qc =
    client ??
    new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } } })
  return {
    client: qc,
    ...render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
      </QueryClientProvider>,
    ),
  }
}
