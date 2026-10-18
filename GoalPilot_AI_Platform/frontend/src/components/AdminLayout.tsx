import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { Button } from './ui'
import { BrandMark, RESEARCH_BANNER } from './Layout'

/**
 * The administrator's own shell.
 *
 * Deliberately separate from the application shell: an administrator working on the platform does
 * not need the user's goals, budgets or plan in the sidebar, and mixing the two made it unclear
 * which area was in use. The only way between them is the explicit link in each shell.
 */
const ADMIN_ITEMS = [
  { to: '/admin', label: 'Overview', end: true },
  { to: '/admin/runs', label: 'Run history', end: false },
  { to: '/admin/data', label: 'Data and assumptions', end: false },
  { to: '/admin/users', label: 'Users and access', end: false },
  { to: '/admin/health', label: 'System health', end: false },
  { to: '/admin/audit', label: 'Audit logs', end: false },
]

export default function AdminLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  async function handleLogout() {
    await logout()
    navigate('/admin/login', { replace: true })
  }

  const links = (
    <ul className="space-y-1">
      {ADMIN_ITEMS.map((item) => (
        <li key={item.to}>
          <NavLink
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              `block rounded-md px-2.5 py-2 text-sm transition-colors ${
                isActive
                  ? 'bg-slate-900 font-medium text-white'
                  : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
              }`
            }
          >
            {item.label}
          </NavLink>
        </li>
      ))}
    </ul>
  )

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="flex min-h-screen">
        {/* Pinned to the viewport: on long pages the old sidebar stretched to the document height
            and pushed the sign-out footer off screen. */}
        <aside className="hidden w-64 shrink-0 border-r border-slate-200 bg-white lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col">
          <div className="border-b border-slate-200 px-4 py-3">
            <Link to="/admin">
              <BrandMark />
            </Link>
            <p className="mt-2 inline-block rounded bg-slate-900 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
              Administrator
            </p>
          </div>
          <nav className="flex-1 overflow-y-auto p-4">
            <p className="mb-2 px-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
              Platform
            </p>
            {links}
          </nav>
          <div className="border-t border-slate-200 p-4 text-sm">
            <p className="mb-2 truncate text-slate-500" title={user?.email ?? ''}>
              {user?.email}
            </p>
            <Link to="/dashboard" className="text-accent-700 hover:underline">
              ← Back to the app
            </Link>
            <Button tone="secondary" size="sm" className="mt-3 w-full" onClick={() => void handleLogout()}>
              Sign out
            </Button>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 border-b border-slate-800 bg-slate-900 text-white">
            <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
              <div className="flex items-center gap-3">
                <span className="rounded bg-white/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide">
                  Administrator
                </span>
                <nav className="flex items-center gap-3 text-sm lg:hidden">
                  {ADMIN_ITEMS.map((item) => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.end}
                      className={({ isActive }) =>
                        isActive ? 'font-medium text-white' : 'text-slate-300 hover:text-white'
                      }
                    >
                      {item.label}
                    </NavLink>
                  ))}
                </nav>
                <span className="hidden text-sm text-slate-300 sm:inline">{user?.email}</span>
              </div>
              <div className="flex items-center gap-3 text-sm">
                <Link to="/dashboard" className="text-slate-200 hover:underline">
                  Back to the app
                </Link>
                <Button tone="secondary" size="sm" onClick={() => void handleLogout()}>
                  Sign out
                </Button>
              </div>
            </div>
          </header>

          <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8">
            <Outlet />
          </main>

          <footer className="border-t border-slate-200 bg-white px-4 py-4 sm:px-6 lg:px-8">
            <p className="text-xs text-slate-500">{RESEARCH_BANNER}</p>
          </footer>
        </div>
      </div>
    </div>
  )
}

