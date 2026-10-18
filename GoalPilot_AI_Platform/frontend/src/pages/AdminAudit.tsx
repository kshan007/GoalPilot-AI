import { useEffect, useState } from 'react'
import { adminApi, errorMessage } from '../api/client'
import type { AdminAuditPage } from '../api/types'
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
} from '../components/ui'
import { formatDateTime, humanise } from '../lib/format'

const ACTIONS = ['', 'user.update', 'run.inspect']

export default function AdminAudit() {
  const [data, setData] = useState<AdminAuditPage | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [action, setAction] = useState('')

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    adminApi
      .audit({ page, page_size: 50, action })
      .then((result) => active && setData(result))
      .catch((err) => active && setError(errorMessage(err)))
      .finally(() => active && setLoading(false))
    return () => {
      active = false
    }
  }, [page, action])

  return (
    <div className="space-y-6">
      <PageHeader
        title="Audit logs"
        description="Administrative actions only. Entries record who did what, when and to which record — never passwords, tokens or financial payloads."
      />

      <Card>
        <label className="text-sm">
          <span className="mb-1 block font-medium text-slate-700">Action</span>
          <select
            value={action}
            onChange={(event) => {
              setAction(event.target.value)
              setPage(1)
            }}
            className="w-full max-w-xs rounded-lg border border-slate-300 px-3 py-2"
          >
            {ACTIONS.map((value) => (
              <option key={value} value={value}>
                {value ? humanise(value) : 'All actions'}
              </option>
            ))}
          </select>
        </label>
      </Card>

      {loading && <LoadingState label="Loading audit entries…" />}
      {error && <ErrorState message={error} onRetry={() => setPage(page)} />}

      {data && !loading && !error && (
        <Card title={`${data.total} entr${data.total === 1 ? 'y' : 'ies'}`} description={`Page ${data.page} of ${data.pages}`}>
          {data.items.length === 0 ? (
            <EmptyState
              title="No administrative actions yet"
              message="Role changes and run inspections are recorded here as they happen."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="gp-table">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Actor</th>
                    <th>Action</th>
                    <th>Target</th>
                    <th>Details</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((entry) => (
                    <tr key={entry.id}>
                      <td>{formatDateTime(entry.created_at)}</td>
                      <td className="max-w-[14rem] truncate" title={entry.actor_email}>
                        {entry.actor_email}
                      </td>
                      <td>{humanise(entry.action)}</td>
                      <td>
                        {entry.target_type || '—'}
                        {entry.target_id ? ` #${entry.target_id}` : ''}
                      </td>
                      <td className="max-w-md">
                        <code className="text-xs text-slate-600">
                          {Object.keys(entry.details).length > 0 ? JSON.stringify(entry.details) : '—'}
                        </code>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="mt-4 flex items-center justify-between">
            <Button tone="secondary" size="sm" disabled={data.page <= 1} onClick={() => setPage(data.page - 1)}>
              Previous
            </Button>
            <span className="text-xs text-slate-500">
              {data.total === 0 ? 'No rows' : `${(data.page - 1) * data.page_size + 1}–${Math.min(data.page * data.page_size, data.total)} of ${data.total}`}
            </span>
            <Button tone="secondary" size="sm" disabled={data.page >= data.pages} onClick={() => setPage(data.page + 1)}>
              Next
            </Button>
          </div>
        </Card>
      )}
    </div>
  )
}
