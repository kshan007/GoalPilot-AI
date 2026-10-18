import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { Button, Field, InlineNotice } from '../components/ui'

/**
 * The administrator door.
 *
 * Deliberately separate from the normal sign-in: the API refuses ordinary accounts here even
 * with a valid password, and the wording never says whether an email exists.
 */
export default function AdminLogin() {
  const { adminLogin, user, loading } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  useEffect(() => {
    if (!loading && user?.is_admin) navigate('/admin', { replace: true })
  }, [loading, user, navigate])

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(null)
    try {
      await adminLogin(email.trim(), password)
      navigate('/admin', { replace: true })
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4 py-12">
      <div className="rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">GoalPilot</p>
        <h1 className="mt-1 text-2xl font-semibold text-slate-900">Administrator sign-in</h1>
        <p className="mt-2 text-sm text-slate-600">
          This entrance is for whoever maintains the deployment. Your normal GoalPilot account will
          not work here.
        </p>

        {error && (
          <div className="mt-4">
            <InlineNotice tone="warning">{error}</InlineNotice>
          </div>
        )}

        <form className="mt-6 space-y-4" onSubmit={submit}>
          <Field label="Administrator email">
            <input
              type="email"
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </Field>
          <Field label="Password">
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </Field>
          <Button type="submit" disabled={pending} className="w-full">
            {pending ? 'Signing in…' : 'Sign in as administrator'}
          </Button>
        </form>

        <div className="mt-6 flex items-center justify-between text-sm">
          <Link to="/login" className="text-accent-700 hover:underline">
            Normal sign-in
          </Link>
          <Link to="/dashboard" className="text-slate-500 hover:underline">
            Back to the app
          </Link>
        </div>
      </div>
    </div>
  )
}

