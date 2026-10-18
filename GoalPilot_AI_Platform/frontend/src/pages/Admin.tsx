import { Link } from 'react-router-dom'
import { adminApi } from '../api/client'
import { useAsync } from '../lib/useAsync'
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  KeyValueTable,
  LoadingState,
  PageHeader,
  StatCard,
} from '../components/ui'
import { formatDateTime, humanise } from '../lib/format'
import type { AdminOverview } from '../api/types'

const TONE: Record<string, 'positive' | 'warning' | 'negative' | 'neutral'> = {
  ready: 'positive',
  degraded: 'warning',
  unavailable: 'negative',
}

function ActivityChart({ data }: { data: AdminOverview['activity'] }) {
  const max = Math.max(1, ...data.map((point) => point.runs))
  return (
    <div className="flex h-40 items-end gap-1" role="img" aria-label="Optimisation runs per day, last 14 days">
      {data.map((point) => (
        <div key={point.date} className="flex flex-1 flex-col items-center justify-end gap-1">
          <span className="text-[10px] text-slate-400">{point.runs || ''}</span>
          <div
            className="w-full rounded-t bg-slate-800"
            style={{ height: `${Math.max(2, (point.runs / max) * 100)}%` }}
            title={`${point.date}: ${point.runs} run(s)`}
          />
          <span className="text-[9px] text-slate-400">{point.date.slice(8)}</span>
        </div>
      ))}
    </div>
  )
}

function AlgorithmBars({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1])
  const max = Math.max(1, ...entries.map(([, value]) => value))
  if (entries.length === 0) return <p className="text-sm text-slate-500">No runs recorded yet.</p>
  return (
    <ul className="space-y-2">
      {entries.map(([name, value]) => (
        <li key={name}>
          <div className="mb-1 flex justify-between text-xs text-slate-600">
            <span>{humanise(name)}</span>
            <span className="font-medium text-slate-800">{value}</span>
          </div>
          <div className="h-2 rounded bg-slate-100">
            <div className="h-2 rounded bg-slate-800" style={{ width: `${(value / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  )
}

export default function Admin() {
  const { data, loading, error, reload } = useAsync<AdminOverview>(() => adminApi.overview(), [])

  if (loading) return <LoadingState label="Loading platform metrics…" />
  if (error) return <ErrorState message={error} onRetry={reload} />
  if (!data) return null

  return (
    <div className="space-y-6">
      <PageHeader
        title="Overview"
        description="Platform state from stored data. Counts come from the database; anything unavailable is shown as unavailable rather than estimated."
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Users" value={String(data.users.total)} hint={`${data.users.active} active · ${data.users.admins} admin`} />
        <StatCard label="New users (7 days)" value={String(data.users.new_last_7_days)} />
        <StatCard label="Optimisation runs" value={String(data.runs.total)} hint={`${data.runs.last_7_days} in the last 7 days`} />
        <StatCard
          label="Failed runs"
          value={String(data.runs.failed)}
          tone={data.runs.failed > 0 ? 'negative' : 'positive'}
          hint={data.runs.failed > 0 ? 'Inspect recent failures below' : 'None recorded'}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Optimisation activity" description="Runs per day over the last 14 days.">
          <ActivityChart data={data.activity} />
        </Card>
        <Card title="Strategy usage" description="All runs, grouped by the algorithm that produced them.">
          <AlgorithmBars counts={data.runs.by_algorithm} />
          <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate-500">
            {Object.entries(data.runs.by_kind).map(([kind, value]) => (
              <span key={kind} className="rounded bg-slate-100 px-2 py-0.5">
                {humanise(kind)}: {value}
              </span>
            ))}
          </div>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Model availability" description="Reported by the running application, not from a stored flag.">
          <div className="overflow-x-auto">
            <table className="gp-table">
              <thead>
                <tr>
                  <th>Model</th>
                  <th>Kind</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.models.map((model) => (
                  <tr key={model.name}>
                    <td>{model.name}</td>
                    <td>{humanise(model.kind)}</td>
                    <td>
                      <Badge tone={TONE[model.status] ?? 'neutral'}>{humanise(model.status)}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card title="Data sources" description="What the models are built on, and how far each can be trusted.">
          <ul className="space-y-3 text-sm">
            {data.data_sources.map((source) => (
              <li key={source.name}>
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-slate-800">{source.name}</span>
                  <Badge tone="neutral">{humanise(source.kind)}</Badge>
                </div>
                <p className="text-slate-600">{source.used_for}</p>
                <p className="text-xs text-slate-500">{source.caveat}</p>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <Card title="Recent failures" description="Runs whose stored status is not a completed success.">
        {data.recent_failures.length === 0 ? (
          <EmptyState title="No failed runs" message="Nothing has failed since records began." />
        ) : (
          <div className="overflow-x-auto">
            <table className="gp-table">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>When</th>
                  <th>Algorithm</th>
                  <th>Status</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_failures.map((run) => (
                  <tr key={run.id}>
                    <td>
                      <Link className="text-accent-700 hover:underline" to={`/admin/runs/${run.id}`}>
                        #{run.id}
                      </Link>
                    </td>
                    <td>{formatDateTime(run.created_at)}</td>
                    <td>{humanise(run.algorithm)}</td>
                    <td>{humanise(run.status)}</td>
                    <td className="max-w-md text-xs text-slate-600">{run.warnings[0] ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Recent administrative actions" description="Who changed what, from the audit log.">
          {data.recent_audit.length === 0 ? (
            <EmptyState title="No actions yet" message="Role changes and run inspections appear here." />
          ) : (
            <ul className="space-y-2 text-sm">
              {data.recent_audit.map((entry) => (
                <li key={entry.id} className="flex flex-wrap items-baseline justify-between gap-2">
                  <span>
                    <span className="font-medium text-slate-800">{humanise(entry.action)}</span>{' '}
                    <span className="text-slate-500">
                      {entry.target_type} {entry.target_id}
                    </span>
                  </span>
                  <span className="text-xs text-slate-500">
                    {entry.actor_email} · {formatDateTime(entry.created_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Where to go next" description="Direct routes into the operational pages.">
          <div className="grid gap-2 sm:grid-cols-2">
            {[
              { to: '/admin/runs', label: 'Run history' },
              { to: '/admin/users', label: 'Users and access' },
              { to: '/admin/health', label: 'System health' },
              { to: '/admin/data', label: 'Data and assumptions' },
              { to: '/admin/audit', label: 'Audit logs' },
            ].map((item) => (
              <Link
                key={item.to}
                to={item.to}
                className="rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
              >
                {item.label}
              </Link>
            ))}
          </div>
          <div className="mt-4">
            <KeyValueTable
              rows={[
                { key: 'Snapshot', value: formatDateTime(data.generated_at) },
                {
                  key: 'Average runtime',
                  value: Object.entries(data.runs.avg_runtime_ms_by_algorithm)
                    .map(([algo, ms]) => `${humanise(algo)} ${Math.round(ms)} ms`)
                    .join(' · ') || '—',
                },
                {
                  key: 'Statuses',
                  value:
                    Object.entries(data.runs.by_status)
                      .map(([status, count]) => `${humanise(status)} ${count}`)
                      .join(' · ') || '—',
                },
              ]}
            />
          </div>
        </Card>
      </div>
    </div>
  )
}

