import { useState } from 'react'
import { Link } from 'react-router-dom'
import { authApi, errorMessage } from '../api/client'
import type { ForgotPasswordResponse } from '../api/types'
import { Button, ErrorState, Field, InlineNotice, TextInput } from '../components/ui'

export default function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ForgotPasswordResponse | null>(null)

  async function handleSubmit() {
    setPending(true)
    setError(null)
    setResult(null)
    try {
      const response = await authApi.forgotPassword({ email: email.trim() })
      setResult(response)
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-lg px-4 py-14 sm:px-6">
      <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Forgot your password</h1>
      <p className="mt-2 text-sm text-slate-500">
        Enter the email address for the account. The response is deliberately identical whether or not
        the account exists.
      </p>

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

        {error && <ErrorState message={error} />}

        <Button type="submit" pending={pending} className="w-full">
          Request a reset link
        </Button>
      </form>

      {result && (
        <div className="mt-6 space-y-4">
          <InlineNotice tone="info">{result.message}</InlineNotice>

          {result.reset_token ? (
            <div className="gp-card p-5">
              <h2 className="text-sm font-semibold text-slate-900">
                Development reset token (returned by the API)
              </h2>
              <p className="mt-1 text-xs text-slate-500">
                The backend is running with reset tokens exposed, so the flow can be demonstrated
                without an email service. In production this value is null and the token is delivered
                out of band.
              </p>
              <p className="mt-3 break-all rounded border border-slate-200 bg-slate-50 px-3 py-2 font-mono text-xs text-slate-800">
                {result.reset_token}
              </p>
              <div className="mt-3">
                <Link
                  to={`/reset-password?token=${encodeURIComponent(result.reset_token)}`}
                  className="text-sm text-accent-700 hover:underline"
                >
                  Continue to reset the password with this token
                </Link>
              </div>
            </div>
          ) : (
            <InlineNotice tone="warning">
              The API returned no reset token. That is expected outside development: the token is
              delivered through another channel and is never exposed in the response.
            </InlineNotice>
          )}
        </div>
      )}

      <p className="mt-6 text-sm text-slate-500">
        <Link to="/login" className="text-accent-700 hover:underline">
          Back to sign in
        </Link>
      </p>
    </div>
  )
}
