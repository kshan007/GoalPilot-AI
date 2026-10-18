import { Link } from 'react-router-dom'
import { adminApi } from '../api/client'
import type { AdminData as DataPayload } from '../api/types'
import {
  Badge,
  Card,
  ErrorState,
  InlineNotice,
  KeyValueTable,
  LoadingState,
  PageHeader,
} from '../components/ui'
import { humanise } from '../lib/format'
import { useAsync } from '../lib/useAsync'

export default function AdminData() {
  const { data, loading, error, reload } = useAsync<DataPayload>(() => adminApi.data(), [])

  if (loading) return <LoadingState label="Loading data sources…" />
  if (error) return <ErrorState message={error} onRetry={reload} />
  if (!data) return null

  return (
    <div className="space-y-6">
      <PageHeader
        title="Data and assumptions"
        description="What the platform's numbers are built on, and which figures are configurable. Historical observations are never presented as forward guarantees."
      />

      <Card title="Sources in use" description="Each source with its purpose and its limitation.">
        <div className="overflow-x-auto">
          <table className="gp-table">
            <thead>
              <tr>
                <th>Source</th>
                <th>Kind</th>
                <th>Used for</th>
                <th>Rows / period</th>
                <th>Limitation</th>
              </tr>
            </thead>
            <tbody>
              {data.datasets.map((dataset) => (
                <tr key={dataset.name}>
                  <td>{dataset.name}</td>
                  <td>
                    <Badge tone={dataset.kind === 'historical' ? 'positive' : 'neutral'}>
                      {humanise(dataset.kind)}
                    </Badge>
                  </td>
                  <td className="text-xs">{dataset.used_for}</td>
                  <td className="text-xs">
                    {dataset.rows ? `${dataset.rows} rows` : ''}
                    {dataset.rows && dataset.period ? ' · ' : ''}
                    {dataset.period ?? (dataset.rows ? '' : '—')}
                  </td>
                  <td className="max-w-md text-xs text-slate-600">{dataset.caveat}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-4 text-xs text-slate-500">{data.note}</p>
      </Card>

      <Card title="Default assumptions" description="Values a plan starts from before any per-plan override.">
        <KeyValueTable
          rows={Object.entries(data.defaults).map(([key, value]) => ({
            key: humanise(key),
            value: String(value),
          }))}
        />
        <p className="mt-3 text-xs text-slate-500">{data.assumption_note}</p>
      </Card>

      <Card title="Editing assumptions" description="Why the defaults are not editable from this screen.">
        <InlineNotice tone={data.editing.supported ? 'success' : 'info'}>
          {data.editing.supported
            ? 'Editable defaults are supported.'
            : data.editing.reason}
        </InlineNotice>
        <div className="mt-4">
          <p className="mb-2 text-sm font-medium text-slate-700">How each figure is labelled</p>
          <ul className="list-disc space-y-1 pl-5 text-sm text-slate-600">
            {data.provenance_rules.map((rule) => (
              <li key={rule}>{rule}</li>
            ))}
          </ul>
        </div>
      </Card>

      <Card title="Model quality evidence" description="How the forecasting methods have performed on recorded months.">
        <Link to="/admin/model-quality" className="text-sm text-accent-700 hover:underline">
          Open forecast accuracy →
        </Link>
      </Card>
    </div>
  )
}
