import { adminApi } from '../api/client'
import type { AdminHealth as HealthPayload } from '../api/types'
import {
  Badge,
  Card,
  ErrorState,
  JsonBlock,
  KeyValueTable,
  LoadingState,
  PageHeader,
  StatCard,
} from '../components/ui'
import { formatDateTime, humanise } from '../lib/format'
import { useAsync } from '../lib/useAsync'

export default function AdminHealth() {
  const { data, loading, error, reload } = useAsync<HealthPayload>(() => adminApi.health(), [])

  if (loading) return <LoadingState label="Checking the system…" />
  if (error) return <ErrorState message={error} onRetry={reload} />
  if (!data) return null

  const rl = data.models.rl as { available?: boolean; reason?: string; checkpoint?: string }

  return (
    <div className="space-y-6">
      <PageHeader
        title="System health"
        description="Live checks against the running service. A component that cannot be verified is reported as unavailable, never assumed healthy."
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Database"
          value={data.database.reachable ? 'reachable' : 'unreachable'}
          tone={data.database.reachable ? 'positive' : 'negative'}
          hint={data.database.error ?? undefined}
        />
        <StatCard
          label="LP solver"
          value={Boolean((data.models.lp as { available?: boolean }).available) ? 'available' : 'unavailable'}
          tone={Boolean((data.models.lp as { available?: boolean }).available) ? 'positive' : 'negative'}
        />
        <StatCard
          label="RL policy"
          value={rl.available ? 'loaded' : 'unavailable'}
          tone={rl.available ? 'positive' : 'negative'}
          hint={rl.reason ?? rl.checkpoint}
        />
        <StatCard
          label="Failed runs"
          value={String(data.optimization.failed_runs)}
          tone={data.optimization.failed_runs > 0 ? 'warning' : 'positive'}
          hint={
            data.optimization.last_failure_at
              ? `Last ${formatDateTime(data.optimization.last_failure_at)}`
              : 'None recorded'
          }
        />
      </div>

      <Card title="Model status" description="Read from the service at request time.">
        <JsonBlock value={data.models} />
      </Card>

      <Card title="Research artefacts" description="Whether the research tree the engines depend on is present.">
        <JsonBlock value={data.research} />
      </Card>

      <Card title="External data sources" description="Status is only claimed where the application can verify it.">
        <div className="overflow-x-auto">
          <table className="gp-table">
            <thead>
              <tr>
                <th>Source</th>
                <th>Kind</th>
                <th>Used for</th>
                <th>Limitation</th>
              </tr>
            </thead>
            <tbody>
              {data.data_sources.map((source) => (
                <tr key={source.name}>
                  <td>{source.name}</td>
                  <td>
                    <Badge tone="neutral">{humanise(source.kind)}</Badge>
                  </td>
                  <td className="text-xs">{source.used_for}</td>
                  <td className="max-w-md text-xs text-slate-600">{source.caveat}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Default assumptions" description="Configuration values that plans start from.">
        <KeyValueTable
          rows={Object.entries(data.assumptions).map(([key, value]) => ({
            key: humanise(key),
            value: String(value),
          }))}
        />
      </Card>
    </div>
  )
}
