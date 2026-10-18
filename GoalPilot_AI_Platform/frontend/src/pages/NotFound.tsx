import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-50 px-4 text-center">
      <p className="text-xs font-semibold uppercase tracking-wide text-accent-700">Not found</p>
      <h1 className="mt-3 text-2xl font-semibold text-slate-900">That page does not exist</h1>
      <p className="mt-2 max-w-md text-sm text-slate-500">
        The link you followed does not match any screen in the GoalPilot AI prototype.
      </p>
      <div className="mt-6 flex gap-3">
        <Link
          to="/"
          className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
        >
          Back to landing page
        </Link>
        <Link
          to="/dashboard"
          className="rounded-md bg-accent-600 px-4 py-2 text-sm font-medium text-white hover:bg-accent-700"
        >
          Go to dashboard
        </Link>
      </div>
    </div>
  )
}
