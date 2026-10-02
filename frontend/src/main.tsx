import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
// The two typefaces ship with the app rather than from a font service, so an
// offline demo or the snapshot build looks the same as the live one. Archivo
// is one variable file with its width axis (decision D4).
import '@fontsource-variable/archivo/wdth.css'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/500.css'
import './styles/globals.css'

/**
 * Query defaults, chosen for the date slider (ADR-2).
 *
 * `retry: 1` with no backoff: a slider that silently retries three times over
 * eight seconds looks broken, and the error state is informative. One retry
 * covers a dropped connection; more covers nothing a user will wait for.
 *
 * `refetchOnWindowFocus: false`: the geometry for a fixed window does not
 * change when you alt-tab, and refetching seven sites because someone switched
 * to their notes is pure noise.
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      retryDelay: 400,
      refetchOnWindowFocus: false,
      staleTime: 5 * 60 * 1000,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
