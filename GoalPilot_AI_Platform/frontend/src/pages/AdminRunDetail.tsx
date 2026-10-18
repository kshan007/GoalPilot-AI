import { Link, useParams } from 'react-router-dom'
import { adminApi } from '../api/client'
import type { AdminRunDetail as RunDetail } from '../api/types'
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
import { formatDateTime, formatMoney, humanise } from '../lib/format'
import { useAsync } from '../lib/useAsync'

export default function AdminRunDetail() {
  const { runId } = useParams()
  const id = Number(runId)
  const { data, loading, error, reload } = useAsync<RunDetail>(() => adminApi.run(id), [id])

  if (loading) return <LoadingState label="Loading run…" />
  if (error) return <ErrorState message={error} onRetry={reload} />
  if (!data) return null

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Run #${data.id}`}
        description="Operational detail for one run: what was produced, what constrained it, and any warning raised. The account's financial profile is not part of this view."
      />

      <p className="text-sm">
        <Link to="/admin/runs" className="text-accent-700 hover:underline">
          ← Back to run history
        </Link>
      </p>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Status" value={humanise(data.status)} tone={data.status === 'optimal' ? 'positive' : 'warning'} />
        <StatCard label="Feasible" value={data.feasible ? 'yes' : 'no'} />
        <StatCard label="Achievement" value={data.weighted_achievement?.toFixed(3) ?? '--'} />
        <StatCard label="Runtime" value={`${data.runtime_ms} ms`} />
      </div>

      <Card title="Run" description="Recorded at creation and immutable afterwards.">
        <KeyValueTable
          rows={[
            { key: 'When', value: formatDateTime(data.created_at) },
            { key: 'Account', value: data.user_email },
            { key: 'Algorithm', value: humanise(data.algorithm) },
            { key: 'Kind', value: humanise(data.kind) },
            { key: 'Label', value: data.label || '—' },
            { key: 'Model version', value: data.model_version || '—' },
            { key: 'Config version', value: data.config_version || '—' },
            {
              key: 'Objective value',
              value: data.objective_value === null ? 'not applicable' : String(data.objective_value),
            },
            {
              key: 'Total shortfall',
              value: data.total_shortfall === null ? '--' : formatMoney(data.total_shortfall),
            },
          ]}
        />
      </Card>

      {data.warnings.length > 0 && (
        <Card title="Warnings" description="Raised by the engine that produced this run.">
          <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
            {data.warnings.map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        </Card>
      )}

      <Card title="Allocations" description="Per-goal amounts this run produced.">
        <div className="overflow-x-auto">
          <table className="gp-table">
            <thead>
              <tr>
                <th>Goal</th>
                <th>Future cost</th>
                <th>Gap</th>
                <th>Savings</th>
                <th>Investment</th>
                <th>Loan</th>
                <th>EMI</th>
                <th>Projected</th>
                <th>Shortfall</th>
                <th>Achievement</th>
              </tr>
            </thead>
            <tbody>
              {data.allocations.map((allocation) => (
                <tr key={`${allocation.goal_ref}-${allocation.goal_name}`}>
                  <td>{allocation.goal_name || allocation.goal_ref}</td>
                  <td className="gp-num">{formatMoney(allocation.future_goal_cost)}</td>
                  <td className="gp-num">{formatMoney(allocation.funding_gap)}</td>
                  <td className="gp-num">{formatMoney(allocation.monthly_savings_contribution)}</td>
                  <td className="gp-num">{formatMoney(allocation.monthly_investment_contribution)}</td>
                  <td className="gp-num">{formatMoney(allocation.loan_principal)}</td>
                  <td className="gp-num">{formatMoney(allocation.estimated_loan_emi)}</td>
                  <td className="gp-num">{formatMoney(allocation.projected_new_funding)}</td>
                  <td className="gp-num">{formatMoney(allocation.shortfall)}</td>
                  <td>
                    <Badge tone={allocation.achievement_ratio >= 0.999 ? 'positive' : 'warning'}>
                      {(allocation.achievement_ratio * 100).toFixed(1)}%
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Summary" description="The payload the engine returned.">
          <JsonBlock value={data.summary} />
        </Card>
        <Card title="Constraints" description="Capacity and limits the plan was solved against.">
          <JsonBlock value={data.constraints} />
        </Card>
        <Card title="Diagnostics" description="Solver and configuration detail.">
          <JsonBlock value={data.diagnostics} />
        </Card>
        <Card title="Assumptions used" description="The values this run actually applied.">
          <JsonBlock value={data.assumptions} />
        </Card>
      </div>

      {data.alternatives.length > 0 && (
        <Card title="Alternatives evaluated" description="One-change re-solves recorded with this run.">
          <div className="overflow-x-auto">
            <table className="gp-table">
              <thead>
                <tr>
                  <th>Option</th>
                  <th>Goal</th>
                  <th>Change</th>
                  <th>Feasible</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {data.alternatives.map((item, index) => (
                  <tr key={index}>
                    <td>{humanise(String(item.option ?? ''))}</td>
                    <td>{String(item.goal_name ?? '—')}</td>
                    <td>{String(item.change ?? '')}</td>
                    <td>{item.feasible ? 'yes' : 'no'}</td>
                    <td className="max-w-md text-xs">{String(item.detail ?? '')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}
