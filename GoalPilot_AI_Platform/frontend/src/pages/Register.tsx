import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { Button, ErrorState, Field, TextInput } from '../components/ui'

export default function Register() {
  const { register, user, loading } = useAuth()
  const navigate = useNavigate()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!loading && user) navigate('/dashboard', { replace: true })
  }, [loading, user, navigate])

  async function handleSubmit() {
    if (password !== confirm) {
      setError('The two passwords do not match.')
      return
    }
    setPending(true)
    setError(null)
    try {
      await register(email.trim(), password, fullName.trim())
      navigate('/onboarding', { replace: true })
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-md px-4 py-14 sm:px-6">
      <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Create an account</h1>
      <p className="mt-2 text-sm text-slate-500">
        Your records stay inside your own account. Onboarding saves your progress as you go.
      </p>

      <form
        className="gp-card mt-6 space-y-4 p-5"
        onSubmit={(event) => {
          event.preventDefault()
          void handleSubmit()
        }}
      >
        <Field label="Full name">
          <TextInput value={fullName} onChange={setFullName} placeholder="Your name" disabled={pending} />
        </Field>
        <Field label="Email">
          <TextInput
            type="email"
            value={email}
            onChange={setEmail}
            placeholder="you@example.com"
            disabled={pending}
          />
        </Field>
        <Field
          label="Password"
          hint="At least 8 characters, and not only letters or only digits. No leading or trailing spaces."
        >
          <TextInput type="password" value={password} onChange={setPassword} disabled={pending} />
        </Field>
        <Field label="Confirm password">
          <TextInput type="password" value={confirm} onChange={setConfirm} disabled={pending} />
        </Field>

        {error && <ErrorState message={error} />}

        <Button type="submit" pending={pending} className="w-full">
          Create account
        </Button>

        <p className="text-sm text-slate-500">
          Already registered?{' '}
          <Link to="/login" className="text-accent-700 hover:underline">
            Sign in
          </Link>
        </p>
      </form>
    </div>
  )
}
