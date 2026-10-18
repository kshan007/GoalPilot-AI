import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { Button, ErrorState, Field, InlineNotice, TextInput } from '../components/ui'

export default function Login() {
  const { login, user, loading } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const next = new URLSearchParams(location.search).get('next')

  useEffect(() => {
    if (!loading && user) {
      navigate(next ? decodeURIComponent(next) : '/dashboard', { replace: true })
    }
  }, [loading, user, navigate, next])

  async function handleSubmit() {
    setPending(true)
    setError(null)
    try {
      await login(email.trim(), password)
      navigate(next ? decodeURIComponent(next) : '/dashboard', { replace: true })
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-md px-4 py-14 sm:px-6">
      <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Sign in</h1>
      <p className="mt-2 text-sm text-slate-500">
        Use the email and password for your GoalPilot AI account.
      </p>

      {location.state && (location.state as { message?: string }).message && (
        <div className="mt-5">
          <InlineNotice tone="info">{(location.state as { message?: string }).message}</InlineNotice>
        </div>
      )}

      <form
        className="gp-card mt-6 space-y-4 p-5"
        onSubmit={(event) => {
          event.preventDefault()
          void handleSubmit()
        }}
      >
        <Field label="Email">
          <TextInput
            type="email"
            value={email}
            onChange={setEmail}
            placeholder="you@example.com"
            disabled={pending}
          />
        </Field>
        <Field label="Password">
          <TextInput type="password" value={password} onChange={setPassword} disabled={pending} />
        </Field>

        {error && <ErrorState message={error} />}

        <Button type="submit" pending={pending} className="w-full">
          Sign in
        </Button>

        <div className="flex items-center justify-between text-sm">
          <Link to="/forgot-password" className="text-accent-700 hover:underline">
            Forgot your password?
          </Link>
          <Link to="/register" className="text-accent-700 hover:underline">
            Create an account
          </Link>
        </div>
        <p className="mt-6 border-t border-slate-200 pt-4 text-center text-xs text-slate-500">
          <Link to="/admin/login" className="hover:underline">
            Administrator sign-in
          </Link>
        </p>
      </form>
    </div>
  )
}
