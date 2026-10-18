import { Link } from 'react-router-dom'
import { forecastApi, goalsApi, optimizeApi } from '../api/client'
import { useAsync } from '../lib/useAsync'
import { formatDateTime, formatMoney, formatPct, formatPctRaw } from '../lib/format'
import { AccuracyChart } from '../components/Charts'
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Provenance,
  StatCard,
} from '../components/ui'

export default function Reports() {
  const { data, loading, error, reload } = useAsync(
    () => Promise.all([goalsApi.plan(), forecastApi.accuracy(), optimizeApi.runs()]),
    [],
  )

  if (loading) return <LoadingState label="Loading reports..." />
  if (error) return <ErrorState message={error} onRetry={reload} />

  const projections = data ? data[0] : []
  const accuracy = data ? data[1] : null
  const runs = data ? data[2] : null

  const totalRequired = projections.reduce((sum, item) => sum + item.required_monthly_contribution, 0)
  const totalGap = projections.reduce((sum, item) => sum + item.remaining_gap, 0)

  return (
    <div className="space-y-6">
      <PageHeader
        title="Download my data"
        description="Your goals, your monthly records and our estimates, ready to keep or share. Everything here is your own data."
      />

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <StatCard label="Goals tracked" value={String(projections.length)} />
        <StatCard label="Total remaining gap" value={formatMoney(totalGap)} hint={<Provenance kind="projected" />} />
        <StatCard
          label="Total required monthly"
          value={formatMoney(totalRequired)}
          hint={<Provenance kind="projected" />}
        />
      </section>

      <Card
        title="Goal progress"
        description="What your goals look like from what you have recorded — no plan run needed."
        actions={
          <Link to="/goals" className="text-sm text-accent-700 hover:underline">
            Manage goals
          </Link>
        }
      >
        {projections.length === 0 ? (
          <EmptyState
            title="No goals to report on"
            message="Create at least one goal. Until then there is no goal progress to show."
            action={
              <Link to="/goals" className="text-sm font-medium text-accent-700 hover:underline">
                Create a goal
              </Link>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="gp-table">
              <thead>
                <tr>
                  <th>Goal</th>
                  <th>Target date</th>
                  <th className="gp-num">Future target</th>
                  <th className="gp-num">Existing funding</th>
                  <th className="gp-num">Gap</th>
                  <th className="gp-num">Required monthly</th>
                  <th className="gp-num">Achievement</th>
                  <th>Feasibility</th>
                </tr>
              </thead>
              <tbody>
                {projections.map((projection) => (
                  <tr key={projection.goal_ref}>
                    <td>
                      {projection.goal_id === null ? (
                        projection.name
                      ) : (
                        <Link
                          to={`/goals/${projection.goal_id}`}
                          className="font-medium text-accent-700 hover:underline"
                        >
                          {projection.name}
                        </Link>
                      )}
                    </td>
                    <td>{projection.target_date}</td>
                    <td className="gp-num">{formatMoney(projection.future_target)}</td>
                    <td className="gp-num">{formatMoney(projection.existing_funding)}</td>
                    <td className="gp-num">{formatMoney(projection.remaining_gap)}</td>
                    <td className="gp-num">{formatMoney(projection.required_monthly_contribution)}</td>
                    <td className="gp-num">
                      {projection.achievement_ratio === null ? '--' : formatPct(projection.achievement_ratio)}
                    </td>
                    <td>
                      <Badge tone={projection.feasibility === 'feasible' ? 'positive' : 'warning'}>
                        {projection.feasibility}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card
        title="Forecast accuracy history"
        description="Only reconciled months are evaluated. Fewer than four reconciled months is stated as not meaningful rather than hidden."
      >
        {!accuracy || accuracy.periods.length === 0 ? (
          <EmptyState
            title="No accuracy history"
            message="Reconcile at least one month to start recording forecast accuracy."
          />
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-3">
              <StatCard label="Months evaluated" value={String(accuracy.periods_evaluated)} />
              <StatCard
                label="Mean absolute error"
                value={accuracy.mae_per_period === null ? '--' : formatMoney(accuracy.mae_per_period)}
              />
              <StatCard
                label="Latest month error"
                value={formatPctRaw(accuracy.periods[accuracy.periods.length - 1].pct_error)}
              />
            </div>
            <div className="mt-5">
              <AccuracyChart data={accuracy.periods} />
            </div>
            <p className="mt-3 text-sm text-slate-600">{accuracy.evidence_note}</p>
          </>
        )}
      </Card>

      <Card
        title="Plan history"
        description="Plans and comparisons stored for this account, most recent first."
        actions={
          <Link to="/optimize" className="text-sm text-accent-700 hover:underline">
            Run a plan
          </Link>
        }
      >
        {!runs || runs.items.length === 0 ? (
          <EmptyState
            title="No plans yet"
            message="Run a plan or a comparison. Each run is stored with its algorithm, timings and warnings."
            action={
              <Link to="/optimize" className="text-sm font-medium text-accent-700 hover:underline">
                Go to optimise
              </Link>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="gp-table">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Kind</th>
                  <th>Algorithm</th>
                  <th>Status</th>
                  <th>Feasible</th>
                  <th className="gp-num">Weighted achievement</th>
                  <th className="gp-num">Total shortfall</th>
                  <th className="gp-num">Runtime</th>
                  <th>Model version</th>
                  <th>Created</th>
                  <th>Warnings</th>
                </tr>
              </thead>
              <tbody>
                {runs.items.map((run) => (
                  <tr key={run.id}>
                    <td>#{run.id}</td>
                    <td>{run.kind}</td>
                    <td className="font-mono text-xs">{run.algorithm}</td>
                    <td>{run.status}</td>
                    <td>
                      <Badge tone={run.feasible ? 'positive' : 'warning'}>
                        {run.feasible ? 'yes' : 'no'}
                      </Badge>
                    </td>
                    <td className="gp-num">
                      {run.weighted_achievement === null ? '--' : formatPct(run.weighted_achievement)}
                    </td>
                    <td className="gp-num">
                      {run.total_shortfall === null ? '--' : formatMoney(run.total_shortfall)}
                    </td>
                    <td className="gp-num">{run.runtime_ms} ms</td>
                    <td className="text-xs text-slate-500">{run.model_version}</td>
                    <td className="text-xs text-slate-500">{formatDateTime(run.created_at)}</td>
                    <td className="text-xs text-amber-700">
                      {run.warnings.length === 0 ? '--' : run.warnings.join(' ')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}


