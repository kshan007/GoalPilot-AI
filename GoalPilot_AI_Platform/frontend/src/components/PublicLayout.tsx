import { Link, Outlet, useLocation } from 'react-router-dom'
import { BrandMark } from './Layout'

export default function PublicLayout() {
  const location = useLocation()

  return (
    <div className="flex min-h-screen flex-col bg-white">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <Link to="/">
            <BrandMark />
          </Link>
          <nav className="flex items-center gap-3 text-sm">
            <Link to="/" className="hidden text-slate-600 hover:text-slate-900 sm:inline">
              Home
            </Link>
            <Link to="/privacy" className="hidden text-slate-600 hover:text-slate-900 sm:inline">
              Privacy
            </Link>
            <Link
              to="/login"
              className={`rounded-md px-3 py-1.5 ${
                location.pathname === '/login'
                  ? 'bg-accent-50 font-medium text-accent-800'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Log in
            </Link>
            <Link
              to="/register"
              className="rounded-md bg-accent-600 px-3 py-1.5 font-medium text-white hover:bg-accent-700"
            >
              Get started
            </Link>
          </nav>
        </div>
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="border-t border-slate-200 bg-slate-50">
        <div className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <BrandMark />
            <nav className="flex flex-wrap items-center gap-4 text-sm text-slate-600">
              <Link to="/privacy#terms" className="hover:underline">
                Terms
              </Link>
              <Link to="/privacy#privacy" className="hover:underline">
                Privacy
              </Link>
              <Link to="/privacy#disclaimer" className="hover:underline">
                Disclaimer
              </Link>
            </nav>
          </div>
          <p className="mt-4 max-w-3xl text-xs text-slate-500">
            GoalPilot AI is an academic research and decision-support prototype. It does not provide
            personalised or regulated financial advice and it does not execute trades, move money or
            originate loans.
          </p>
        </div>
      </footer>
    </div>
  )
}
