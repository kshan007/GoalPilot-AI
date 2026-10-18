import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { adminApi, errorMessage } from '../api/client'
import type { AdminRunsPage } from '../api/types'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
} from '../components/ui'
import { formatDateTime, formatMoney, humanise } from '../lib/format'

const ALGORITHMS = ['', 'lp', 'rl', 'hybrid', 'rule_baseline']
const STATUSES = ['', 'optimal', 'invalid_plan', 'unavailable', 'failed']
const KINDS = ['', 'plan', 'compare', 'scenario']

export default function AdminRuns() {
  const [params, setParams] = useSearchParams()
  const [data, setData] = useState<AdminRunsPage | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const page = Number(params.get('page') ?? '1')
  const algorithm = params.get('algorithm') ?? ''
  const status = params.get('status') ?? ''
  const kind = params.get('kind') ?? ''
  const search = params.get('search') ?? ''

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    adminApi
      .runs({ page, page_size: 25, algorithm, status, kind, search })
      .then((result) => active && setData(result))
      .catch((err) => active && setError(errorMessage(err)))
      .finally(() => active && setLoading(false))
    return () => {
      active = false
    }
  }, [page, algorithm, status, kind, search])

  function update(key: string, value: string) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    if (key !== 'page') next.delete('page')
    setParams(next)
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Run history"
        description="Every optimisation run, newest first. Inspecting a run records that you opened it and never returns the user's income, assets or transactions."
      />

      <Card>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="text-sm">
            <span className="mb-1 block font-medium text-slate-700">Search</span>
            <input
              type="search"
              defaultValue={search}
              placeholder="Run id or account email"
              onKeyDown={(event) => {
                if (event.key === 'Enter') update('search', (event.target as HTMLInputElement).value)
              }}
              onBlur={(event) => update('search', event.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-medium text-slate-700">Algorithm</span>
            <select
              value={algorithm}
              onChange={(event) => update('algorithm', event.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2"
            >
              {ALGORITHMS.map((value) => (
                <option key={value} value={value}>
                  {value ? humanise(value) : 'All algorithms'}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-medium text-slate-700">Status</span>
            <select
              value={status}
              onChange={(event) => update('status', event.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2"
            >
              {STATUSES.map((value) => (
                <option key={value} value={value}>
                  {value ? humanise(value) : 'All statuses'}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-medium text-slate-700">Kind</span>
            <select
              value={kind}
              onChange={(event) => update('kind', event.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2"
            >
              {KINDS.map((value) => (
                <option key={value} value={value}>
                  {value ? humanise(value) : 'All kinds'}
                </option>
              ))}
            </select>
          </label>
        </div>
      </Card>

      {loading && <LoadingState label="Loading runs…" />}
      {error && <ErrorState message={error} onRetry={() => update('page', String(page))} />}

      {data && !loading && !error && (
        <>
          <Card
            title={`${data.total} run${data.total === 1 ? '' : 's'}`}
            description={`Page ${data.page} of ${data.pages}`}
          >
            {data.items.length === 0 ? (
              <EmptyState
                title="No runs match"
                message="Change the filters, or run a plan from the algorithm console."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="gp-table">
                  <thead>
                    <tr>
                      <th>Run</th>
                      <th>When</th>
                      <th>Account</th>
                      <th>Algorithm</th>
                      <th>Kind</th>
                      <th>Status</th>
                      <th>Feasible</th>
                      <th>Achievement</th>
                      <th>Shortfall</th>
                      <th>Runtime</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((run) => (
                      <tr key={run.id}>
                        <td>
                          <Link className="text-accent-700 hover:underline" to={`/admin/runs/${run.id}`}>
                            #{run.id}
                          </Link>
                        </td>
                        <td>{formatDateTime(run.created_at)}</td>
                        <td className="max-w-[12rem] truncate" title={run.user_email}>
                          {run.user_email}
                        </td>
                        <td>{humanise(run.algorithm)}</td>
                        <td>{humanise(run.kind)}</td>
                        <td>
                          <Badge
                            tone={
                              run.status === 'optimal'
                                ? 'positive'
                                : run.status === 'unavailable'
                                  ? 'negative'
                                  : 'warning'
                            }
                          >
                            {humanise(run.status)}
                          </Badge>
                        </td>
                        <td>{run.feasible ? 'yes' : 'no'}</td>
                        <td className="gp-num">{run.weighted_achievement.toFixed(3)}</td>
                        <td className="gp-num">{formatMoney(run.total_shortfall)}</td>
                        <td className="gp-num">{run.runtime_ms} ms</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="mt-4 flex items-center justify-between">
              <Button
                tone="secondary"
                size="sm"
                disabled={data.page <= 1}
                onClick={() => update('page', String(data.page - 1))}
              >
                Previous
              </Button>
              <span className="text-xs text-slate-500">
                {data.total === 0
                  ? 'No rows'
                  : `${(data.page - 1) * data.page_size + 1}–${Math.min(
                      data.page * data.page_size,
                      data.total,
                    )} of ${data.total}`}
              </span>
              <Button
                tone="secondary"
                size="sm"
                disabled={data.page >= data.pages}
                onClick={() => update('page', String(data.page + 1))}
              >
                Next
              </Button>
            </div>
          </Card>
        </>
      )}
    </div>
  )
}
