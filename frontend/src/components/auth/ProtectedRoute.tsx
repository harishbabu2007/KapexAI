import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../../lib/auth'

/**
 * Guards a route so only authenticated users can reach it. While the stored
 * session is being validated a loader is shown; unauthenticated visitors are
 * redirected to the landing page.
 */
export function ProtectedRoute() {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="full-page-loader">
        <div className="spinner" aria-label="Loading" />
      </div>
    )
  }

  if (!user) return <Navigate to="/" replace />

  return <Outlet />
}
