import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App } from './App'
import './index.css'

const queryClient = new QueryClient()

// In sidecar mode the UI is served at /plugins/statement-tools/ by the main
// nginx. Setting basename strips that prefix so React Router routes match from /.
const basename = import.meta.env.VITE_MODE === 'sidecar' ? '/plugins/statement-tools' : ''

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename={basename}>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
