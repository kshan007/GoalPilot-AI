import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { authApi, errorMessage } from '../api/client'
import { Button, ErrorState, Field, InlineNotice, TextInput } from '../components/ui'

export default function ResetPassword() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [token, setToken] = useState(params.get('token') ?? '')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  async function handleSubmit() {
    if (password !== confirm) {
      setError('The two passwords do not match.')
      return
    }
    setPending(true)
    setError(null)
    setMessage(null)
    try {
      const response = await authApi.resetPassword({ token: token.trim(), new_password: password })
      setMessage(response.message)
      setTimeout(() => navigate('/login', { replace: false }), 1200)
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-md px-4 py-14 sm:px-6">
      <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Reset your password</h1>
      <p className="mt-2 text-sm text-slate-500">
        Paste the reset token and choose a new password. Resetting invalidates every existing session
        for the account.
      </p>

      <form
        className="gp-card mt-6 space-y-4 p-5"
        onSubmit={(event) => {
          event.preventDefault()
          void handleSubmit()
        }}
      >
        <Field label="Reset token">
          <TextInput value={token} onChange={setToken} disabled={pending} placeholder="Paste the token" />
        </Field>
        <Field
          label="New password"
          hint="At least 8 characters, and not only letters or only digits."
        >
          <TextInput type="password" value={password} onChange={setPassword} disabled={pending} />
        </Field>
        <Field label="Confirm new password">
          <TextInput type="password" value={confirm} onChange={setConfirm} disabled={pending} />
        </Field>

        {error && <ErrorState message={error} />}
        {message && <InlineNotice tone="success">{message}</InlineNotice>}

        <Button type="submit" pending={pending} className="w-full">
          Reset password
        </Button>
      </form>

      <p className="mt-6 text-sm text-slate-500">
        <Link to="/login" className="text-accent-700 hover:underline">
          Back to sign in
        </Link>
      </p>
    </div>
  )
}
