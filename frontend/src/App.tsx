import { Navigate, Route, Routes } from 'react-router-dom'
import UploadPage from './pages/UploadPage'
import PublicDownloadPage from './pages/PublicDownloadPage'

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/statement-tools" replace />} />
      <Route path="/statement-tools" element={<UploadPage />} />
      <Route path="/statement-tools/public" element={<PublicDownloadPage />} />
    </Routes>
  )
}
