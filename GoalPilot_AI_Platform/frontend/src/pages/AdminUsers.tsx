import { useCallback, useEffect, useState } from 'react'
import { adminApi, errorMessage } from '../api/client'
import type { AdminUsersPage } from '../api/types'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  InlineNotice,
  LoadingState,
  PageHeader,
} from '../components/ui'
import { formatDateTime } from '../lib/format'

export default function AdminUsers() {
  const [data, setData] = useState<AdminUsersPage | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [role, setRole] = useState('')
  const [status, setStatus] = useState('')
  const [pendingId, setPendingId] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await adminApi.users({ page, page_size: 25, search, role, status }))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [page, search, role, status])

  useEffect(() => {
    void load()
  }, [load])

  async function change(userId: number, email: string, body: { is_admin?: boolean; is_active?: boolean }, description: string) {
    if (!window.confirm(`${description}\n\nAccount: ${email}`)) return
    setPendingId(userId)
    setError(null)
    setNotice(null)
    try {
      await adminApi.updateUser(userId, body)
      setNotice(`${email}: ${description.toLowerCase()} applied.`)
      await load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setPendingId(null)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Users and access"
        description="Accounts registered on this deployment. Role and status changes are authorised on the server and written to the audit log."
      />

      {notice && <InlineNotice tone="success">{notice}</InlineNotice>}

      <Card>
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="text-sm">
            <span className="mb-1 block font-medium text-slate-700">Search</span>
            <input
              type="search"
              value={search}
              placeholder="Email or name"
              onChange={(event) => {
                setSearch(event.target.value)
                setPage(1)
              }}
              className="w-full rounded-lg border border-slate-300 px-3 py-2"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-medium text-slate-700">Role</span>
            <select
              value={role}
              onChange={(event) => {
                setRole(event.target.value)
                setPage(1)
              }}
              className="w-full rounded-lg border border-slate-300 px-3 py-2"
            >
              <option value="">All roles</option>
              <option value="admin">Administrators</option>
              <option value="user">Ordinary users</option>
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-medium text-slate-700">Status</span>
            <select
              value={status}
              onChange={(event) => {
                setStatus(event.target.value)
                setPage(1)
              }}
              className="w-full rounded-lg border border-slate-300 px-3 py-2"
            >
              <option value="">All statuses</option>
              <option value="active">Active</option>
              <option value="inactive">Deactivated</option>
            </select>
          </label>
        </div>
      </Card>

      {loading && <LoadingState label="Loading accounts…" />}
      {error && <ErrorState message={error} onRetry={load} />}

      {data && !loading && !error && (
        <Card title={`${data.total} account${data.total === 1 ? '' : 's'}`} description={`Page ${data.page} of ${data.pages}`}>
          {data.items.length === 0 ? (
            <EmptyState title="No accounts match" message="Try a different search or filter." />
          ) : (
            <div className="overflow-x-auto">
              <table className="gp-table">
                <thead>
                  <tr>
                    <th>Account</th>
                    <th>Name</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>Runs</th>
                    <th>Joined</th>
                    <th>Last sign-in</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((user) => (
                    <tr key={user.id}>
                      <td className="max-w-[16rem] truncate" title={user.email}>
                        {user.email}
                      </td>
                      <td>{user.full_name || '—'}</td>
                      <td>
                        <Badge tone={user.is_admin ? 'accent' : 'neutral'}>
                          {user.is_admin ? 'admin' : 'user'}
                        </Badge>
                      </td>
                      <td>
                        <Badge tone={user.is_active ? 'positive' : 'negative'}>
                          {user.is_active ? 'active' : 'deactivated'}
                        </Badge>
                      </td>
                      <td className="gp-num">{user.runs}</td>
                      <td>{formatDateTime(user.created_at)}</td>
                      <td>{user.last_login_at ? formatDateTime(user.last_login_at) : 'never'}</td>
                      <td>
                        <div className="flex flex-wrap gap-2">
                          <Button
                            tone="secondary"
                            size="sm"
                            disabled={pendingId === user.id}
                            onClick={() =>
                              change(
                                user.id,
                                user.email,
                                { is_admin: !user.is_admin },
                                user.is_admin ? 'Remove administrator access' : 'Grant administrator access',
                              )
                            }
                          >
                            {user.is_admin ? 'Revoke admin' : 'Make admin'}
                          </Button>
                          <Button
                            tone="secondary"
                            size="sm"
                            disabled={pendingId === user.id}
                            onClick={() =>
                              change(
                                user.id,
                                user.email,
                                { is_active: !user.is_active },
                                user.is_active ? 'Deactivate this account' : 'Reactivate this account',
                              )
                            }
                          >
                            {user.is_active ? 'Deactivate' : 'Reactivate'}
                          </Button>
                        </div>
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
