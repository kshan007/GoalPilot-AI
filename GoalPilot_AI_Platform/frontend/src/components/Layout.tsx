import { useState } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { Button } from './ui'

interface NavItem {
  to: string
  label: string
  group: string
}

/**
 * Navigation is written for someone who has never used a planning tool. Each label says what the
 * page is about in everyday words, the technical pages live under "Admin", and the ordering
 * follows what a person does: set yourself up, record money, set goals, get a plan.
 */
const NAV_ITEMS: NavItem[] = [
  { to: '/dashboard', label: 'Home', group: 'Start here' },
  { to: '/onboarding', label: 'Getting started', group: 'Start here' },
  { to: '/profile', label: 'My details', group: 'Start here' },

  { to: '/monthly', label: 'Money in and out', group: 'My money' },
  { to: '/monthly/reconciliation', label: 'Check a month', group: 'My money' },
  { to: '/budgets', label: 'Spending limits', group: 'My money' },
  { to: '/assets', label: 'Things I own', group: 'My money' },
  { to: '/liabilities', label: 'Money I owe', group: 'My money' },

  { to: '/goals', label: 'My goals', group: 'My goals' },
  { to: '/optimize', label: 'My plan', group: 'My goals' },
  { to: '/algorithms', label: 'Algorithms', group: 'My goals' },
  { to: '/compare', label: 'Strategy comparison', group: 'My goals' },
  { to: '/scenarios', label: 'What if…?', group: 'My goals' },

  { to: '/recommendations', label: 'Ideas for you', group: 'Explore options' },
  { to: '/investments', label: 'Ways to invest', group: 'Explore options' },
  { to: '/loans', label: 'Borrowing', group: 'Explore options' },

  { to: '/reports', label: 'Download my data', group: 'Settings' },
  { to: '/settings', label: 'Preferences', group: 'Settings' },
  { to: '/account', label: 'My account', group: 'Settings' },

]

const GROUPS = ['Start here', 'My money', 'My goals', 'Explore options', 'Settings']

export const RESEARCH_BANNER =
  'Research decision-support prototype. Not financial advice. No trades, transfers or loans are executed.'

export function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <span className="flex h-8 w-8 items-center justify-center rounded bg-accent-600 text-sm font-bold text-white">
        GP
      </span>
      {!compact && (
        <span className="text-base font-semibold tracking-tight text-slate-900">
          GoalPilot <span className="text-accent-700">AI</span>
        </span>
      )}
    </div>
  )
}

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  // Administrators keep their own shell; the app navigation stays the same for everyone, with a
  // single link across for the people who need it.
  const isAdmin = Boolean(user?.is_admin)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(false)

  async function handleLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  const sidebar = (
    <nav className="flex h-full flex-col gap-6 overflow-y-auto p-4">
      {GROUPS.map((group) => (
        <div key={group}>
          {!collapsed && (
            <p className="mb-2 px-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
              {group}
            </p>
          )}
          <ul className="space-y-1">
            {NAV_ITEMS.filter((item) => item.group === group).map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.to === '/monthly'}
                  onClick={() => setMobileOpen(false)}
                  title={collapsed ? item.label : undefined}
                  className={({ isActive }) =>
                    `block rounded-md px-2.5 py-2 text-sm transition-colors ${
                      isActive
                        ? 'bg-accent-50 font-medium text-accent-800'
                        : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                    }`
                  }
                >
                  {collapsed ? item.label.slice(0, 2) : item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  )

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="flex min-h-screen">
        {/* Desktop sidebar */}
        <aside
          className={`hidden shrink-0 border-r border-slate-200 bg-white lg:block ${
            collapsed ? 'w-20' : 'w-64'
          }`}
        >
          <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
            <Link to="/dashboard">
              <BrandMark compact={collapsed} />
            </Link>
            {isAdmin && !collapsed && (
              <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                Administrator
              </span>
            )}
          </div>
          {sidebar}
        </aside>

        {/* Mobile drawer */}
        {mobileOpen && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <div
              className="absolute inset-0 bg-slate-900/40"
              onClick={() => setMobileOpen(false)}
              role="presentation"
            />
            <div className="absolute left-0 top-0 h-full w-72 border-r border-slate-200 bg-white">
              <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
                <BrandMark />
                <Button tone="ghost" size="sm" onClick={() => setMobileOpen(false)}>
                  Close
                </Button>
              </div>
              {sidebar}
            </div>
          </div>
        )}

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
            <div className="flex items-center justify-between gap-3 px-4 py-3">
              <div className="flex items-center gap-2">
                <Button tone="secondary" size="sm" className="lg:hidden" onClick={() => setMobileOpen(true)}>
                  Menu
                </Button>
                <Button
                  tone="secondary"
                  size="sm"
                  className="hidden lg:inline-flex"
                  onClick={() => setCollapsed((value) => !value)}
                >
                  {collapsed ? 'Expand' : 'Collapse'}
                </Button>
                <span className="hidden text-sm text-slate-500 sm:inline">
                  Signed in as {user?.email ?? 'unknown'}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {isAdmin && (
                  <Link
                    to="/admin"
                    className="hidden text-sm font-medium text-slate-700 hover:underline sm:inline"
                  >
                    Admin
                  </Link>
                )}
                <Link to="/settings" className="hidden text-sm text-accent-700 hover:underline sm:inline">
                  Settings
                </Link>
                <Button tone="secondary" size="sm" onClick={handleLogout}>
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
            <p className="mt-1 text-xs text-slate-400">
              <Link to="/privacy" className="hover:underline">
                Privacy, terms and educational disclaimer
              </Link>
            </p>
          </footer>
        </div>
      </div>
    </div>
  )
}



