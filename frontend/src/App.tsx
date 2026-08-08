import { Navigate, Route, Routes } from 'react-router-dom'
import { ProtectedRoute } from './components/auth/ProtectedRoute'
import { BusinessProfilePage } from './pages/BusinessProfilePage'
import { ChatPage } from './pages/ChatPage'
import { LandingPage } from './pages/LandingPage'
import { useAuth } from './lib/auth'

/**
 * The landing route. Fresh signups (and returning users who never saved a
 * business profile) land on the profile page first; everyone else goes straight
 * to the chat workspace. Unauthenticated visitors see the landing page.
 */
function HomeRedirect() {
  const { user, loading, profileEmpty } = useAuth()

  if (loading) {
    return (
      <div className="full-page-loader">
        <div className="spinner" aria-label="Loading" />
      </div>
    )
  }

  if (!user) return <LandingPage />
  return <Navigate to={profileEmpty ? '/business-profile' : '/chat'} replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomeRedirect />} />
      <Route element={<ProtectedRoute />}>
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/business-profile" element={<BusinessProfilePage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}