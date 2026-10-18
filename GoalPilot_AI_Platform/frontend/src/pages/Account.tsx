import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { accountApi, downloadJson, errorMessage, metaApi } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { useAsync } from '../lib/useAsync'
import { formatDateTime, valueText } from '../lib/format'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  InlineNotice,
  JsonBlock,
  LoadingState,
  PageHeader,
  TextInput,
  WarningList,
} from '../components/ui'

export default function Account() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { data, loading, error, reload } = useAsync(
    () => Promise.all([metaApi.health(), metaApi.dataProvenance()]),
    [],
  )

  const [confirmText, setConfirmText] = useState('')
  const [pending, setPending] = useState(false)
  const [exportPending, setExportPending] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  async function handleExport() {
    setExportPending(true)
    setActionError(null)
    setNotice(null)
    try {
      const payload = await accountApi.export()
      const stamp = new Date().toISOString().replace(/[:.]/g, '-')
      downloadJson(`goalpilot-export-${stamp}.json`, payload)
      setNotice('Export downloaded. No password hash, reset token or session token is included.')
    } catch (caught) {
      setActionError(errorMessage(caught))
    } finally {
      setExportPending(false)
    }
  }

  async function handleDelete() {
    if (confirmText !== 'DELETE') {
      setActionError('Type DELETE exactly to enable account deletion.')
      return
    }
    setPending(true)
    setActionError(null)
    setNotice(null)
    try {
      const response = await accountApi.remove()
      setNotice(response.message)
      await logout()
      navigate('/login', { replace: true })
    } catch (caught) {
      setActionError(errorMessage(caught))
      setPending(false)
    }
  }

  if (loading) return <LoadingState label="Loading account information..." />
  if (error) return <ErrorState message={error} onRetry={reload} />

  const health = data ? data[0] : null
  const provenance = data ? data[1] : null

  return (
    <div className="space-y-6">
      <PageHeader
        title="Account and data"
        description="Export everything this account holds, or delete the account and its records."
      />

      <Card title="Account">
        <div className="overflow-x-auto">
          <table className="gp-table">
            <tbody>
              <tr>
                <td className="text-slate-500">Email</td>
                <td>{user?.email ?? '--'}</td>
              </tr>
              <tr>
                <td className="text-slate-500">Name</td>
                <td>{user?.full_name || '--'}</td>
              </tr>
              <tr>
                <td className="text-slate-500">Account created</td>
                <td>{formatDateTime(user?.created_at)}</td>
              </tr>
              <tr>
                <td className="text-slate-500">Last sign-in</td>
                <td>{formatDateTime(user?.last_login_at)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </Card>

      <Card
        title="Export your data"
        description="Downloads the JSON response from GET /account/export. It contains every record owned by this account and no secret."
      >
        <div className="flex flex-wrap items-center gap-3">
          <Button pending={exportPending} onClick={handleExport}>
            Download JSON export
          </Button>
          {notice && <InlineNotice tone="success">{notice}</InlineNotice>}
        </div>
        {actionError && (
          <div className="mt-4">
            <ErrorState message={actionError} />
          </div>
        )}
      </Card>

      <Card
        title="Delete account"
        description="Deletion removes the account and every record it owns. This is irreversible and there is no recovery path."
      >
        <div className="max-w-md">
          <Field
            label="Type DELETE to confirm"
            hint="The button stays disabled until the text matches exactly. The request is only sent when the button is pressed."
          >
            <TextInput value={confirmText} onChange={setConfirmText} disabled={pending} placeholder="DELETE" />
          </Field>
        </div>
        <div className="mt-4">
          <Button tone="danger" disabled={confirmText !== 'DELETE'} pending={pending} onClick={handleDelete}>
            Permanently delete my account
          </Button>
        </div>
      </Card>

      {health && (
        <Card title="Backend health" description="Reported by GET /health.">
          <div className="overflow-x-auto">
            <table className="gp-table">
              <tbody>
                <tr>
                  <td className="text-slate-500">Status</td>
                  <td>
                    <Badge tone={health.status === 'healthy' ? 'positive' : 'warning'}>{health.status}</Badge>
                  </td>
                </tr>
                <tr>
                  <td className="text-slate-500">Application</td>
                  <td>
                    {health.app_name} {health.version}
                  </td>
                </tr>
                <tr>
                  <td className="text-slate-500">Environment</td>
                  <td>{health.environment}</td>
                </tr>
                <tr>
                  <td className="text-slate-500">Research source</td>
                  <td className="text-xs">{valueText(health.research_source)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div className="mt-4">
            <p className="mb-2 text-sm font-medium text-slate-700">Supported features</p>
            <JsonBlock value={health.supported_features} label="features" />
          </div>
          <div className="mt-4">
            <InlineNotice tone="info">{health.disclaimer}</InlineNotice>
          </div>
        </Card>
      )}

      {provenance && (
        <Card
          title="Data provenance"
          description="Where the numbers the platform uses come from, and the caveat attached to each source."
        >
          {provenance.datasets.length === 0 ? (
            <EmptyState title="No datasets reported" message="The API reported no dataset provenance." />
          ) : (
            <div className="overflow-x-auto">
              <table className="gp-table">
                <thead>
                  <tr>
                    <th>Dataset</th>
                    <th>Kind</th>
                    <th>Used for</th>
                    <th>Caveat</th>
                  </tr>
                </thead>
                <tbody>
                  {provenance.datasets.map((dataset) => (
                    <tr key={dataset.name}>
                      <td>{dataset.name}</td>
                      <td>
                        <Badge tone={dataset.kind === 'synthetic' ? 'warning' : 'neutral'}>
                          {dataset.kind}
                        </Badge>
                      </td>
                      <td className="text-sm text-slate-600">{dataset.used_for}</td>
                      <td className="text-xs text-slate-500">{dataset.caveat}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="mt-3 text-sm text-slate-600">{provenance.note}</p>
        </Card>
      )}

    </div>
  )
}



