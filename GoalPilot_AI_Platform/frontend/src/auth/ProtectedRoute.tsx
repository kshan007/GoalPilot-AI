import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from './AuthContext'
import { LoadingState } from '../components/ui'

/**
 * Renders a loading state while the session is resolving, redirects to /login when there is
 * no authenticated user, and otherwise renders the protected outlet.
 */
export default function ProtectedRoute() {
  const { user, token, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <LoadingState label="Restoring your session..." />
      </div>
    )
  }

  if (!user || !token) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  return <Outlet />
}
