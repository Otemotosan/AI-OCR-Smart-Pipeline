import { Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from '@/components/Layout'
import { DashboardPage } from '@/pages/DashboardPage'
import { DocumentListPage } from '@/pages/DocumentListPage'
import { DocumentEditorPage } from '@/pages/DocumentEditorPage'
import { UploadPage } from '@/pages/UploadPage'
import { Toaster } from '@/components/ui/toaster'

function App() {
  return (
    <>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="upload" element={<UploadPage />} />
          <Route path="documents" element={<DocumentListPage />} />
          <Route path="documents/:docHash" element={<DocumentEditorPage />} />
        </Route>
      </Routes>
      <Toaster />
    </>
  )
}

export default App
