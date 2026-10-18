import { forecastApi } from '../api/client'
import { useAsync } from '../lib/useAsync'
import { formatDateTime, formatMoney, formatPctRaw } from '../lib/format'
import { AccuracyChart } from '../components/Charts'
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  InlineNotice,
  JsonBlock,
  LoadingState,
  PageHeader,
  Provenance,
  StatCard,
} from '../components/ui'

export default function ForecastHistory() {
  const { data, loading, error, reload } = useAsync(
    () => Promise.all([forecastApi.history(), forecastApi.accuracy()]),
    [],
  )

  if (loading) return <LoadingState label="Loading forecast history..." />
  if (error) return <ErrorState message={error} onRetry={reload} />

  const history = data ? data[0] : null
  const accuracy = data ? data[1] : null

  return (
    <div className="space-y-6">
      <PageHeader
        title="Forecast accuracy"
        description="How close our past estimates came to what actually happened. We keep each estimate as it was made, so nothing is quietly rewritten after the fact."
      />

      {history && (
        <Card title="Stored estimates" description={history.note}>
          {history.forecasts.length === 0 ? (
            <EmptyState
              title="No estimates stored"
              message="Generate estimates in the monthly workspace. Nothing is shown here until the API has stored a forecast."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="gp-table">
                <thead>
                  <tr>
                    <th>Period</th>
                    <th>Category</th>
                    <th className="gp-num">Amount</th>
                    <th>Method</th>
                    <th>Method version</th>
                    <th>History months</th>
                    <th>Provisional</th>
                    <th>Data quality</th>
                    <th>Input cut-off</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {history.forecasts.map((item, index) => (
                    <tr key={`${item.period}-${item.category}-${index}`}>
                      <td>{item.period}</td>
                      <td>{item.category}</td>
                      <td className="gp-num">{formatMoney(item.amount)}</td>
                      <td className="text-xs">{item.method}</td>
                      <td className="text-xs text-slate-500">{item.method_version}</td>
                      <td>{item.history_months_used}</td>
                      <td>
                        <Badge tone={item.is_provisional ? 'warning' : 'positive'}>
                          {item.is_provisional ? 'provisional' : 'committed'}
                        </Badge>
                      </td>
                      <td className="text-xs text-slate-500">{item.data_quality}</td>
                      <td className="text-xs text-slate-500">{formatDateTime(item.input_cutoff)}</td>
                      <td className="text-xs text-slate-500">{formatDateTime(item.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="mt-4">
            <InlineNotice tone="info">
              All values in this table are estimates, not actuals. Actual spending appears in the
              reconciliation views once a month is reconciled.
            </InlineNotice>
          </div>
        </Card>
      )}

      {accuracy && (
        <>
          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <StatCard label="Reconciled months evaluated" value={String(accuracy.periods_evaluated)} />
            <StatCard
              label="Mean absolute error per month"
              value={accuracy.mae_per_period === null ? '--' : formatMoney(accuracy.mae_per_period)}
            />
            <StatCard label="Evidence" value={accuracy.periods_evaluated < 4 ? 'limited' : 'sufficient'} />
          </section>

          <Card title="Forecast error trend">
            <AccuracyChart data={accuracy.periods} />
          </Card>

          <Card
            title="Per-month accuracy"
            description="Recorded estimate against recorded actual for each reconciled month."
          >
            {accuracy.periods.length === 0 ? (
              <EmptyState
                title="No reconciled months"
                message="Accuracy is only reported for months that have been reconciled. Reconcile a month to populate this table."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="gp-table">
                  <thead>
                    <tr>
                      <th>Period</th>
                      <th className="gp-num">Estimated</th>
                      <th className="gp-num">Actual</th>
                      <th className="gp-num">Absolute error</th>
                      <th className="gp-num">Error</th>
                    </tr>
                  </thead>
                  <tbody>
                    {accuracy.periods.map((period) => (
                      <tr key={period.period}>
                        <td>{period.period}</td>
                        <td className="gp-num">{formatMoney(period.forecast)}</td>
                        <td className="gp-num">{formatMoney(period.actual)}</td>
                        <td className="gp-num">{formatMoney(period.abs_error)}</td>
                        <td className="gp-num">{formatPctRaw(period.pct_error)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="mt-3 text-sm text-slate-600">{accuracy.evidence_note}</p>
            <p className="mt-1 text-xs text-slate-500">
              Provenance: <Provenance kind="estimated" /> estimated values compared with{' '}
              <Provenance kind="actual" /> recorded values.
            </p>
          </Card>

          <Card
            title="How we tested the estimates"
            description="We only use a method where it beats a simple baseline on your own recorded months."
          >
            {Object.keys(accuracy.walk_forward_backtest).length === 0 ? (
              <EmptyState
                title="Nothing to test yet"
                message="This needs a few recorded months. Nothing is shown until there is enough history."
              />
            ) : (
              <JsonBlock value={accuracy.walk_forward_backtest} label="backtest" />
            )}
          </Card>
        </>
      )}
    </div>
  )
}

