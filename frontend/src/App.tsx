import { useEffect } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import UploadPage from './pages/UploadPage'
import PublicDownloadPage from './pages/PublicDownloadPage'

const isSidecar = import.meta.env.VITE_MODE === 'sidecar'

export function App() {
  // sidecar/handshake logic: Receive auth token from host securely
  useEffect(() => {
    if (isSidecar) {
      // 1. Signal that we are ready
      window.parent.postMessage({ type: 'PLUGIN_READY' }, '*')

      // 2. Listen for the token
      const handleMessage = (event: MessageEvent) => {
        if (event.data?.type === 'AUTH_TOKEN' && event.data.token) {
          localStorage.setItem('token', event.data.token)
          // Optionally trigger a fresh fetch of data if needed
          window.dispatchEvent(new Event('storage')) 
        }
      }
      window.addEventListener('message', handleMessage)
      return () => window.removeEventListener('message', handleMessage)
    }
  }, [])

  // Sidecar mode: basename='/plugins/statement-tools' is set in main.tsx,
  // so routes are relative to that — '/' renders the upload page directly.
  if (isSidecar) {
    return (
      <Routes>
        <Route path="/" element={<UploadPage />} />
        <Route path="/public" element={<PublicDownloadPage />} />
        <Route path="*" element={<UploadPage />} />
      </Routes>
    )
  }

  // Standalone mode: full paths with /statement-tools prefix.
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/statement-tools" replace />} />
      <Route path="/statement-tools" element={<UploadPage />} />
      <Route path="/statement-tools/public" element={<PublicDownloadPage />} />
      <Route path="*" element={<Navigate to="/statement-tools" replace />} />
    </Routes>
  )
}
