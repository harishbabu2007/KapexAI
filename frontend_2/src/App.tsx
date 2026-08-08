import { Navigate, Route, Routes } from 'react-router-dom'
import { ProtectedRoute } from './components/auth/ProtectedRoute'
import { ChatPage } from './pages/ChatPage'
import { CanvasLandingPage } from './pages/CanvasLandingPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<CanvasLandingPage />} />
      <Route element={<ProtectedRoute />}>
        <Route path="/chat" element={<ChatPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
