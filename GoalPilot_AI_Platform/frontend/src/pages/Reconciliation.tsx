import { useState } from 'react'
import { Link } from 'react-router-dom'
import { errorMessage, monthlyApi } from '../api/client'
import type { ReconcileResponse } from '../api/types'
import { useAsync } from '../lib/useAsync'
import { currentPeriod, formatMoney, formatPctRaw, valueText } from '../lib/format'
import {
  Badge,
  Button,
  Card,
  Checkbox,
  EmptyState,
  ErrorState,
  Field,
  InlineNotice,
  LoadingState,
  PageHeader,
  Provenance,
  StatCard,
  TextInput,
} from '../components/ui'

export default function Reconciliation() {
  const [period, setPeriod] = useState(currentPeriod())
  const [activePeriod, setActivePeriod] = useState(currentPeriod())
  const { data, loading, error, reload } = useAsync(
    () =>
      Promise.all([monthlyApi.reconciliation(activePeriod), monthlyApi.budgetStatus(activePeriod)]),
    [activePeriod],
  )

  const [markActuals, setMarkActuals] = useState(true)
  const [updateFutureForecast, setUpdateFutureForecast] = useState(true)
  const [pending, setPending] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [result, setResult] = useState<ReconcileResponse | null>(null)

  async function runReconcile() {
    setPending(true)
    setActionError(null)
    try {
      const response = await monthlyApi.reconcile(activePeriod, {
        mark_actuals: markActuals,
        update_future_forecast: updateFutureForecast,
      })
      setResult(response)
      reload()
    } catch (caught) {
      setActionError(errorMessage(caught))
    } finally {
      setPending(false)
    }
  }

  const reconciliation = data ? data[0] : null
  const budgetStatus = data ? data[1] : null

  return (
    <div className="space-y-6">
      <PageHeader
        title="Check a month"
        description="What we expected for the month, next to what actually happened, category by category. Your original estimate is kept so you can see how close it was."
      />

      <Card title="Period">
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Period">
            <TextInput type="month" value={period} onChange={setPeriod} disabled={pending} />
          </Field>
          <Button tone="secondary" disabled={pending} onClick={() => setActivePeriod(period)}>
            Load
          </Button>
        </div>
      </Card>

      {loading && <LoadingState label={`Loading reconciliation for ${activePeriod}...`} />}
      {error &&
        (error.includes('has not been opened') ? (
          // Not a failure: the month simply does not exist yet. Showing an error page for a first
          // visit made the page look broken, so it offers the step that creates the month instead.
          <EmptyState
            title={`${activePeriod} has not been opened yet`}
            message="Open the month on Money in and out first — record what came in and went out — then come back here to compare it with what we expected."
            action={
              <Link className="font-medium text-accent-700 hover:underline" to="/monthly">
                Open the month
              </Link>
            }
          />
        ) : (
          <ErrorState message={error} onRetry={reload} />
        ))}

      {!loading && !error && reconciliation && (
        <>
          {!reconciliation.reconciled ? (
            <EmptyState
              title={`${activePeriod} has not been reconciled`}
              message={
                reconciliation.message ??
                'Generate estimates, record actuals and then reconcile the month.'
              }
            />
          ) : (
            <>
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                <StatCard
                  label="Forecast total"
                  value={formatMoney(reconciliation.totals?.forecast ?? null)}
                  hint={<Provenance kind="estimated" />}
                />
                <StatCard
                  label="Actual total"
                  value={formatMoney(reconciliation.totals?.actual ?? null)}
                  hint={<Provenance kind="actual" />}
                />
                <StatCard
                  label="Absolute error"
                  value={formatMoney(reconciliation.totals?.abs_error ?? null)}
                />
                <StatCard
                  label="Percentage error"
                  value={formatPctRaw(reconciliation.totals?.pct_error ?? null)}
                />
              </div>

              <Card title="Per-category forecast versus actual">
                {!reconciliation.rows || reconciliation.rows.length === 0 ? (
                  <EmptyState
                    title="No reconciled categories"
                    message="The reconciliation returned no rows for this month."
                  />
                ) : (
                  <div className="overflow-x-auto">
                    <table className="gp-table">
                      <thead>
                        <tr>
                          <th>Category</th>
                          <th className="gp-num">Estimated</th>
                          <th className="gp-num">Actual</th>
                          <th className="gp-num">Absolute error</th>
                          <th className="gp-num">Error</th>
                          <th>Assessment</th>
                        </tr>
                      </thead>
                      <tbody>
                        {reconciliation.rows.map((row) => (
                          <tr key={row.category}>
                            <td>{row.category}</td>
                            <td className="gp-num">{formatMoney(row.forecast)}</td>
                            <td className="gp-num">{formatMoney(row.actual)}</td>
                            <td className="gp-num">{formatMoney(row.abs_error)}</td>
                            <td className="gp-num">{formatPctRaw(row.pct_error)}</td>
                            <td>
                              <Badge tone={row.over_budget ? 'negative' : 'positive'}>
                                {row.over_budget ? 'over estimate' : 'at or under estimate'}
                              </Badge>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  <div className="rounded-md border border-red-200 bg-red-50 p-3">
                    <p className="text-sm font-medium text-red-800">Over estimate</p>
                    <p className="mt-1 text-sm text-red-700">
                      {(reconciliation.over_budget_categories ?? []).join(', ') || 'None'}
                    </p>
                  </div>
                  <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3">
                    <p className="text-sm font-medium text-emerald-800">At or under estimate</p>
                    <p className="mt-1 text-sm text-emerald-700">
                      {(reconciliation.under_budget_categories ?? []).join(', ') || 'None'}
                    </p>
                  </div>
                </div>
                {reconciliation.evaluated_at && (
                  <p className="mt-3 text-xs text-slate-500">
                    Evaluation recorded at {reconciliation.evaluated_at}
                  </p>
                )}
              </Card>
            </>
          )}

          {!reconciliation.reconciled && reconciliation.category_actuals && (
            <Card title="Recorded actuals so far" description="Grouped by category, from transactions already marked actual.">
              {Object.keys(reconciliation.category_actuals).length === 0 ? (
                <EmptyState
                  title="No actual expenses recorded"
                  message="Add expense transactions with the status set to actual in the monthly workspace."
                />
              ) : (
                <div className="overflow-x-auto">
                  <table className="gp-table">
                    <thead>
                      <tr>
                        <th>Category</th>
                        <th className="gp-num">Recorded actual</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(reconciliation.category_actuals).map(([category, amount]) => (
                        <tr key={category}>
                          <td>{category}</td>
                          <td className="gp-num">{formatMoney(amount)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          )}
        </>
      )}

      <Card
        title="Reconcile this month"
        description="Reconciliation compares the stored estimate with recorded actuals and keeps the original forecast intact."
      >
        <div className="flex flex-wrap gap-5">
          <Checkbox
            label="Mark recorded expenses as actuals where applicable"
            checked={markActuals}
            disabled={pending}
            onChange={setMarkActuals}
          />
          <Checkbox
            label="Include this month in the next forecast"
            checked={updateFutureForecast}
            disabled={pending}
            onChange={setUpdateFutureForecast}
          />
        </div>

        {actionError && (
          <div className="mt-4">
            <ErrorState message={actionError} />
          </div>
        )}

        <div className="mt-5">
          <Button pending={pending} onClick={runReconcile}>
            Reconcile {activePeriod}
          </Button>
        </div>

        {result && (
          <div className="mt-5 space-y-3">
            <InlineNotice tone="success">
              {result.evaluations_created} evaluation row(s) created. The forecast was preserved:
              {' '}
              {String(result.forecast_preserved)}
            </InlineNotice>
            {result.rows.length > 0 && (
              <div className="overflow-x-auto">
                <table className="gp-table">
                  <thead>
                    <tr>
                      <th>Category</th>
                      <th className="gp-num">Estimated</th>
                      <th className="gp-num">Actual</th>
                      <th>Assessment</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.rows.map((row) => (
                      <tr key={row.category}>
                        <td>{row.category}</td>
                        <td className="gp-num">{formatMoney(row.forecast)}</td>
                        <td className="gp-num">{formatMoney(row.actual)}</td>
                        <td>
                          <Badge tone={row.actual > row.forecast ? 'negative' : 'positive'}>
                            {row.actual > row.forecast ? 'over estimate' : 'at or under estimate'}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {result.next_forecast_note && <InlineNotice tone="info">{result.next_forecast_note}</InlineNotice>}
          </div>
        )}
      </Card>

      {!loading && !error && budgetStatus && (
        <Card
          title="Budget status"
          description="Spending recorded so far against each active budget limit for this period."
        >
          {budgetStatus.budgets.length === 0 ? (
            <EmptyState
              title="No active budgets"
              message="Create a budget in the budgets page to compare spending against a limit you defined."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="gp-table">
                <thead>
                  <tr>
                    <th>Category</th>
                    <th className="gp-num">Limit</th>
                    <th className="gp-num">Spent (actual)</th>
                    <th className="gp-num">Remaining</th>
                    <th className="gp-num">Utilisation</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {budgetStatus.budgets.map((row) => (
                    <tr key={row.category}>
                      <td>{row.category}</td>
                      <td className="gp-num">{formatMoney(row.monthly_limit)}</td>
                      <td className="gp-num">{formatMoney(row.spent)}</td>
                      <td className="gp-num">{formatMoney(row.remaining)}</td>
                      <td className="gp-num">
                        {row.utilisation === null ? '--' : formatPctRaw(row.utilisation * 100, 1)}
                      </td>
                      <td>
                        <Badge tone={row.over_budget ? 'negative' : 'positive'}>
                          {row.over_budget ? 'over budget' : 'within budget'}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="mt-5 grid gap-4 xl:grid-cols-2">
            <div>
              <p className="mb-2 text-sm font-medium text-slate-700">Persistent overspend</p>
              {budgetStatus.persistent_overspend.length === 0 ? (
                <EmptyState
                  title="None detected"
                  message="A category is flagged when it repeatedly exceeds its limit across recorded months."
                />
              ) : (
                <div className="overflow-x-auto">
                  <table className="gp-table">
                    <tbody>
                      {budgetStatus.persistent_overspend.map((row, index) => (
                        <tr key={index}>
                          <td className="text-xs">{valueText(row)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
            <div>
              <p className="mb-2 text-sm font-medium text-slate-700">Recurring categories detected</p>
              {budgetStatus.recurring_categories.length === 0 ? (
                <EmptyState
                  title="None detected"
                  message="Recurring categories are detected from your recorded actual expenses."
                />
              ) : (
                <div className="overflow-x-auto">
                  <table className="gp-table">
                    <tbody>
                      {budgetStatus.recurring_categories.map((row, index) => (
                        <tr key={index}>
                          <td className="text-xs">{valueText(row)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </Card>
      )}
    </div>
  )
}

