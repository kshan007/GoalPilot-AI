import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from './AuthContext'
import { LoadingState } from '../components/ui'

/**
 * Gate for the technical area.
 *
 * Signed-out visitors are sent to the administrator door, and a signed-in ordinary user is sent
 * back to their own home rather than shown a page they cannot use. The API re-checks the flag on
 * every admin-only request, so this guard is convenience, not the security boundary.
 */
export default function AdminRoute() {
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
    return <Navigate to="/admin/login" replace state={{ from: location.pathname }} />
  }

  if (!user.is_admin) {
    return <Navigate to="/dashboard" replace />
  }

  return <Outlet />
}
