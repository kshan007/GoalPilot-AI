import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { errorMessage, monthlyApi } from '../api/client'
import type { EstimateResponse, MonthDetail, ReconcileResponse, TransactionInput } from '../api/types'
import { useAsync } from '../lib/useAsync'
import { currentPeriod, formatDate, formatDateTime, formatMoney, formatPctRaw } from '../lib/format'
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
  SelectInput,
  StatCard,
  TextInput,
} from '../components/ui'

interface CategoryRow {
  category: string
  amount: string
}

function emptyTransaction(period: string): TransactionInput {
  return {
    kind: 'expense',
    category: 'groceries',
    label: '',
    amount: 0,
    txn_date: `${period}-01`,
    status: 'actual',
    is_recurring: false,
    note: '',
  }
}

export default function Monthly() {
  const [period, setPeriod] = useState(currentPeriod())
  const [activePeriod, setActivePeriod] = useState(currentPeriod())
  const { data, loading, error, reload, setData } = useAsync(() => monthlyApi.read(activePeriod), [activePeriod])

  const [pending, setPending] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const [txnForm, setTxnForm] = useState<TransactionInput>(emptyTransaction(activePeriod))
  const [editingTxnId, setEditingTxnId] = useState<number | null>(null)

  const [estimateRows, setEstimateRows] = useState<CategoryRow[]>([{ category: '', amount: '' }])
  const [recurringRows, setRecurringRows] = useState<CategoryRow[]>([{ category: '', amount: '' }])
  const [persistEstimates, setPersistEstimates] = useState(true)
  const [estimateResult, setEstimateResult] = useState<EstimateResponse | null>(null)

  const [markActuals, setMarkActuals] = useState(true)
  const [updateFutureForecast, setUpdateFutureForecast] = useState(true)
  const [reconcileResult, setReconcileResult] = useState<ReconcileResponse | null>(null)

  useEffect(() => {
    setTxnForm(emptyTransaction(activePeriod))
    setEditingTxnId(null)
  }, [activePeriod])

  async function run<T>(action: () => Promise<T>, successMessage?: string): Promise<T | null> {
    setPending(true)
    setActionError(null)
    setNotice(null)
    try {
      const result = await action()
      if (successMessage) setNotice(successMessage)
      setPending(false)
      return result
    } catch (caught) {
      setActionError(errorMessage(caught))
      setPending(false)
      return null
    }
  }

  if (loading) return <LoadingState label={`Loading ${activePeriod}...`} />

  // A month that has not been opened is an *empty* state, not an error. It used to short-circuit
  // here and hide the period card, so the only visible control was a button labelled "Retry"
  // while the message said "open it below" — with nothing below. The action is now explicit.
  const monthNotOpened = Boolean(error && /not been opened|validation_error/i.test(error))

  if (error && !monthNotOpened) {
    return (
      <div className="space-y-6">
        <PageHeader title="Monthly workspace" description="Record what actually happened, then reconcile." />
        <ErrorState message={error} onRetry={reload} />
      </div>
    )
  }

  if (monthNotOpened) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Monthly workspace"
          description="Record what actually happened, then reconcile."
        />
        <Card
          title="Period"
          description="Months are stored as YYYY-MM. Opening a month seeds expected income and recurring obligations."
        >
          <div className="flex flex-wrap items-end gap-3">
            <Field label="Period">
              <TextInput type="month" value={period} onChange={setPeriod} disabled={pending} />
            </Field>
            <Button tone="secondary" disabled={pending} onClick={() => setActivePeriod(period)}>
              Load
            </Button>
            <Button
              pending={pending}
              onClick={async () => {
                const opened = await run(
                  () => monthlyApi.open(period),
                  `${period} opened. Recurring income and obligations were seeded where they did not already exist.`,
                )
                if (opened) {
                  setActivePeriod(period)
                  // `reload()` rather than `setData()`: the failed read that produced the
                  // "not opened" state left `error` set, and setting only the data would keep
                  // the empty state on screen until a manual browser refresh.
                  reload()
                }
              }}
            >
              Open month
            </Button>
          </div>
          {actionError && (
            <div className="mt-4">
              <ErrorState message={actionError} />
            </div>
          )}
        </Card>

        <EmptyState
          title={`${activePeriod} has not been opened`}
          message="Open the month to create its record and seed expected income and recurring obligations. Estimates and actual transactions can then be recorded against it."
          action={
            <Button
              pending={pending}
              onClick={async () => {
                const opened = await run(() => monthlyApi.open(activePeriod), `${activePeriod} opened.`)
                // `reload()` clears the stale error from the failed read; `setData()` alone left
                // this empty state on screen until the user refreshed the browser.
                if (opened) reload()
              }}
            >
              Open {activePeriod}
            </Button>
          }
        />
      </div>
    )
  }

  const detail: MonthDetail | null = data
  const month = detail?.month ?? null

  const categories = detail ? Object.entries(detail.categories) : []

  return (
    <div className="space-y-6">
      <PageHeader
        title="Monthly workspace"
        description="Each figure says where it came from: recorded means you entered it, forecast means we estimated it, planned means it comes from your plan."
        actions={
          <Link
            to="/monthly/reconciliation"
            className="rounded-md border border-slate-300 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Reconciliation view
          </Link>
        }
      />

      <Card title="Period" description="Months are stored as YYYY-MM. Opening a month seeds expected income and recurring obligations.">
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Period">
            <TextInput type="month" value={period} onChange={setPeriod} disabled={pending} />
          </Field>
          <Button tone="secondary" disabled={pending} onClick={() => setActivePeriod(period)}>
            Load
          </Button>
          <Button
            disabled={pending}
            onClick={async () => {
              const opened = await run(
                () => monthlyApi.open(period),
                `${period} opened. Recurring income and obligations were seeded where they did not already exist.`,
              )
              if (opened) {
                setActivePeriod(period)
                setData(opened)
              }
            }}
          >
            Open month
          </Button>
        </div>
        {actionError && (
          <div className="mt-4">
            <ErrorState message={actionError} />
          </div>
        )}
        {notice && (
          <div className="mt-4">
            <InlineNotice tone="success">{notice}</InlineNotice>
          </div>
        )}
      </Card>

      {!month ? (
        <EmptyState
          title={`${activePeriod} has not been opened`}
          message="Open the month to create its record and seed expected income and recurring obligations."
          action={
            <Button
              onClick={async () => {
                const opened = await run(() => monthlyApi.open(activePeriod), `${activePeriod} opened.`)
                if (opened) setData(opened)
              }}
              disabled={pending}
            >
              Open {activePeriod}
            </Button>
          }
        />
      ) : (
        <>
          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
              label="Income (actual)"
              value={formatMoney(month.total_income_actual)}
              hint={<Provenance kind="actual" />}
            />
            <StatCard
              label="Income (expected)"
              value={formatMoney(month.total_income_expected)}
              hint={<Provenance kind="estimated" />}
            />
            <StatCard
              label="Expenses (actual)"
              value={formatMoney(month.total_expense_actual)}
              hint={<Provenance kind="actual" />}
            />
            <StatCard
              label="Expenses (estimated)"
              value={formatMoney(month.total_expense_estimated)}
              hint={<Provenance kind="estimated" />}
            />
            <StatCard
              label="Surplus (actual)"
              value={formatMoney(month.surplus_actual)}
              hint={<Provenance kind="actual" />}
              tone={month.surplus_actual < 0 ? 'negative' : 'positive'}
            />
            <StatCard
              label="Surplus (projected)"
              value={formatMoney(month.surplus_projected)}
              hint={<Provenance kind="projected" />}
            />
            <StatCard label="Status" value={month.status} hint={`${month.transaction_count} transactions`} />
            <StatCard
              label="Reconciled at"
              value={month.reconciled_at ? formatDateTime(month.reconciled_at) : 'Not reconciled'}
            />
          </section>

          <Card
            title="Transactions"
            description="Set the status deliberately: estimated for a planned or forecast line, actual for something that really happened. The two are never merged."
          >
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <Field label="Kind">
                <SelectInput
                  value={txnForm.kind}
                  onChange={(value) => setTxnForm({ ...txnForm, kind: value as TransactionInput['kind'] })}
                  options={[
                    { value: 'expense', label: 'expense' },
                    { value: 'income', label: 'income' },
                  ]}
                  disabled={pending}
                />
              </Field>
              <Field label="Category">
                <TextInput
                  value={txnForm.category}
                  onChange={(value) => setTxnForm({ ...txnForm, category: value })}
                  disabled={pending}
                />
              </Field>
              <Field label="Label">
                <TextInput
                  value={txnForm.label}
                  onChange={(value) => setTxnForm({ ...txnForm, label: value })}
                  disabled={pending}
                />
              </Field>
              <Field label="Amount">
                <TextInput
                  type="number"
                  value={String(txnForm.amount)}
                  onChange={(value) => setTxnForm({ ...txnForm, amount: value === '' ? 0 : Number(value) })}
                  disabled={pending}
                />
              </Field>
              <Field label="Date">
                <TextInput
                  type="date"
                  value={txnForm.txn_date}
                  onChange={(value) => setTxnForm({ ...txnForm, txn_date: value })}
                  disabled={pending}
                />
              </Field>
              <Field label="Status">
                <SelectInput
                  value={txnForm.status}
                  onChange={(value) => setTxnForm({ ...txnForm, status: value as TransactionInput['status'] })}
                  options={[
                    { value: 'actual', label: 'actual' },
                    { value: 'estimated', label: 'estimated' },
                  ]}
                  disabled={pending}
                />
              </Field>
              <Field label="Note">
                <TextInput
                  value={txnForm.note}
                  onChange={(value) => setTxnForm({ ...txnForm, note: value })}
                  disabled={pending}
                />
              </Field>
              <div className="flex items-end">
                <Checkbox
                  label="Recurring"
                  hint="Recurring lines are carried forward when the next month is opened."
                  checked={txnForm.is_recurring}
                  disabled={pending}
                  onChange={(value) => setTxnForm({ ...txnForm, is_recurring: value })}
                />
              </div>
            </div>

            <div className="mt-5 flex flex-wrap gap-2">
              <Button
                pending={pending}
                onClick={async () => {
                  if (editingTxnId === null) {
                    const created = await run(
                      () => monthlyApi.addTransaction(activePeriod, txnForm),
                      'Transaction added.',
                    )
                    if (created) {
                      setTxnForm(emptyTransaction(activePeriod))
                      reload()
                    }
                  } else {
                    const updated = await run(
                      () => monthlyApi.updateTransaction(activePeriod, editingTxnId, txnForm),
                      'Transaction updated.',
                    )
                    if (updated) {
                      setEditingTxnId(null)
                      setTxnForm(emptyTransaction(activePeriod))
                      reload()
                    }
                  }
                }}
              >
                {editingTxnId === null ? 'Add transaction' : 'Save transaction'}
              </Button>
              {editingTxnId !== null && (
                <Button
                  tone="secondary"
                  disabled={pending}
                  onClick={() => {
                    setEditingTxnId(null)
                    setTxnForm(emptyTransaction(activePeriod))
                  }}
                >
                  Cancel edit
                </Button>
              )}
            </div>

            <div className="mt-5">
              {!detail || detail.transactions.length === 0 ? (
                <EmptyState
                  title="No transactions in this month"
                  message="Add income and expense lines above, or generate estimates in the next section."
                />
              ) : (
                <div className="overflow-x-auto">
                  <table className="gp-table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Kind</th>
                        <th>Category</th>
                        <th>Label</th>
                        <th className="gp-num">Amount</th>
                        <th>Where it came from</th>
                        <th>Class</th>
                        <th>Recurring</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.transactions.map((transaction) => (
                        <tr key={transaction.id}>
                          <td>{formatDate(transaction.txn_date)}</td>
                          <td>{transaction.kind}</td>
                          <td>{transaction.category}</td>
                          <td>{transaction.label || '--'}</td>
                          <td className="gp-num">{formatMoney(transaction.amount)}</td>
                          <td>
                            <Badge tone={transaction.status === 'actual' ? 'positive' : 'warning'}>
                              {transaction.status}
                            </Badge>
                          </td>
                          <td>{transaction.classification}</td>
                          <td>{transaction.is_recurring ? 'yes' : 'no'}</td>
                          <td>
                            <div className="flex gap-2">
                              <Button
                                tone="secondary"
                                size="sm"
                                disabled={pending}
                                onClick={() => {
                                  setTxnForm({
                                    kind: transaction.kind as TransactionInput['kind'],
                                    category: transaction.category,
                                    label: transaction.label,
                                    amount: transaction.amount,
                                    txn_date: transaction.txn_date,
                                    status: transaction.status as TransactionInput['status'],
                                    is_recurring: transaction.is_recurring,
                                    goal_id: transaction.goal_id,
                                    note: transaction.note,
                                  })
                                  setEditingTxnId(transaction.id)
                                }}
                              >
                                Edit
                              </Button>
                              <Button
                                tone="danger"
                                size="sm"
                                disabled={pending}
                                onClick={async () => {
                                  const removed = await run(
                                    () => monthlyApi.removeTransaction(activePeriod, transaction.id),
                                    'Transaction removed.',
                                  )
                                  if (removed) reload()
                                }}
                              >
                                Delete
                              </Button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </Card>

          <Card
            title="Category totals"
            description="Estimated and actual amounts are kept in separate columns. A budget limit, where one exists, is shown alongside."
          >
            {categories.length === 0 ? (
              <EmptyState
                title="No expense categories in this month"
                message="Add an expense transaction or generate estimates to populate this table."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="gp-table">
                  <thead>
                    <tr>
                      <th>Category</th>
                      <th className="gp-num">Actual</th>
                      <th className="gp-num">Estimated</th>
                      <th className="gp-num">Budget</th>
                    </tr>
                  </thead>
                  <tbody>
                    {categories.map(([category, totals]) => (
                      <tr key={category}>
                        <td>{category}</td>
                        <td className="gp-num">{formatMoney(totals.actual)}</td>
                        <td className="gp-num">{formatMoney(totals.estimated)}</td>
                        <td className="gp-num">{formatMoney(totals.budget)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card
            title="Estimate expenses"
            description="Estimates use your own declared recurring amounts and guesses first. A personalised method is used only where a walk-forward backtest beats the baseline."
          >
            <div className="grid gap-6 xl:grid-cols-2">
              <div>
                <p className="mb-2 text-sm font-medium text-slate-700">Your own category estimates</p>
                <div className="space-y-2">
                  {estimateRows.map((row, index) => (
                    <div key={index} className="flex gap-2">
                      <TextInput
                        value={row.category}
                        onChange={(value) =>
                          setEstimateRows((rows) =>
                            rows.map((item, position) => (position === index ? { ...item, category: value } : item)),
                          )
                        }
                        placeholder="category"
                        disabled={pending}
                      />
                      <TextInput
                        type="number"
                        value={row.amount}
                        onChange={(value) =>
                          setEstimateRows((rows) =>
                            rows.map((item, position) => (position === index ? { ...item, amount: value } : item)),
                          )
                        }
                        placeholder="amount"
                        disabled={pending}
                      />
                    </div>
                  ))}
                </div>
                <Button
                  tone="secondary"
                  size="sm"
                  className="mt-2"
                  disabled={pending}
                  onClick={() => setEstimateRows((rows) => [...rows, { category: '', amount: '' }])}
                >
                  Add estimate row
                </Button>
              </div>

              <div>
                <p className="mb-2 text-sm font-medium text-slate-700">
                  Known recurring amounts (fixed obligations)
                </p>
                <div className="space-y-2">
                  {recurringRows.map((row, index) => (
                    <div key={index} className="flex gap-2">
                      <TextInput
                        value={row.category}
                        onChange={(value) =>
                          setRecurringRows((rows) =>
                            rows.map((item, position) => (position === index ? { ...item, category: value } : item)),
                          )
                        }
                        placeholder="category"
                        disabled={pending}
                      />
                      <TextInput
                        type="number"
                        value={row.amount}
                        onChange={(value) =>
                          setRecurringRows((rows) =>
                            rows.map((item, position) => (position === index ? { ...item, amount: value } : item)),
                          )
                        }
                        placeholder="amount"
                        disabled={pending}
                      />
                    </div>
                  ))}
                </div>
                <Button
                  tone="secondary"
                  size="sm"
                  className="mt-2"
                  disabled={pending}
                  onClick={() => setRecurringRows((rows) => [...rows, { category: '', amount: '' }])}
                >
                  Add recurring row
                </Button>
                <p className="mt-3 text-xs text-slate-500">
                  Liability EMIs are added automatically as a recurring loan_payments amount, because
                  the EMI is a known obligation.
                </p>
              </div>
            </div>

            <div className="mt-4">
              <Checkbox
                label="Persist these estimates"
                hint="Persisted estimates are stored with their method, version and input cut-off. A committed forecast is never overwritten afterwards."
                checked={persistEstimates}
                disabled={pending}
                onChange={setPersistEstimates}
              />
            </div>

            <div className="mt-5">
              <Button
                pending={pending}
                onClick={async () => {
                  const toMap = (rows: CategoryRow[]) => {
                    const out: Record<string, number> = {}
                    for (const row of rows) {
                      if (row.category.trim() && row.amount !== '') out[row.category.trim()] = Number(row.amount)
                    }
                    return out
                  }
                  const result = await run(
                    () =>
                      monthlyApi.estimateExpenses(activePeriod, {
                        category_estimates: toMap(estimateRows),
                        recurring_categories: toMap(recurringRows),
                        persist: persistEstimates,
                      }),
                    'Estimates generated.',
                  )
                  if (result) {
                    setEstimateResult(result)
                    reload()
                  }
                }}
              >
                Generate estimates
              </Button>
            </div>

            {estimateResult && (
              <div className="mt-6 space-y-4">
                <InlineNotice tone={estimateResult.personalised ? 'success' : 'warning'}>
                  {estimateResult.estimation_method}
                </InlineNotice>
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                  <StatCard
                    label="Expected month-end spending"
                    value={formatMoney(estimateResult.expected_month_end_spending)}
                    hint={<Provenance kind="estimated" />}
                  />
                  <StatCard
                    label="Projected surplus"
                    value={formatMoney(estimateResult.projected_surplus)}
                    hint={<Provenance kind="projected" />}
                  />
                  <StatCard label="History months used" value={String(estimateResult.history_months_available)} />
                  <StatCard label="Estimates persisted" value={String(estimateResult.persisted_count)} />
                </div>
                <p className="text-sm text-slate-600">{estimateResult.data_quality_note}</p>
                <div className="overflow-x-auto">
                  <table className="gp-table">
                    <thead>
                      <tr>
                        <th>Category</th>
                        <th className="gp-num">Estimated amount</th>
                        <th>Method</th>
                        <th>History months</th>
                        <th>Observations</th>
                        <th>Provisional</th>
                        <th>Data quality</th>
                      </tr>
                    </thead>
                    <tbody>
                      {estimateResult.forecast.category_forecasts.map((row) => (
                        <tr key={row.category}>
                          <td>{row.category}</td>
                          <td className="gp-num">{formatMoney(row.amount)}</td>
                          <td className="text-xs">{row.method}</td>
                          <td>{row.history_months_used}</td>
                          <td>{row.observations_used}</td>
                          <td>
                            <Badge tone={row.is_provisional ? 'warning' : 'positive'}>
                              {row.is_provisional ? 'provisional' : 'committed'}
                            </Badge>
                          </td>
                          <td className="text-xs text-slate-500">{row.data_quality}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </Card>

          <Card
            title="Reconcile the month"
            description="Reconciliation compares the stored estimate with recorded actuals. The original forecast is preserved and is never overwritten."
          >
            <div className="flex flex-wrap gap-5">
              <Checkbox
                label="Mark recorded expenses as actuals where applicable"
                checked={markActuals}
                disabled={pending}
                onChange={setMarkActuals}
              />
              <Checkbox
                label="Include this month's actuals in the next forecast"
                checked={updateFutureForecast}
                disabled={pending}
                onChange={setUpdateFutureForecast}
              />
            </div>

            <div className="mt-5">
              <Button
                pending={pending}
                onClick={async () => {
                  const result = await run(
                    () =>
                      monthlyApi.reconcile(activePeriod, {
                        mark_actuals: markActuals,
                        update_future_forecast: updateFutureForecast,
                      }),
                    'Month reconciled.',
                  )
                  if (result) {
                    setReconcileResult(result)
                    reload()
                  }
                }}
              >
                Reconcile {activePeriod}
              </Button>
            </div>

            {reconcileResult && (
              <div className="mt-6 space-y-4">
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                  <StatCard
                    label="Forecast total"
                    value={formatMoney(reconcileResult.totals.forecast)}
                    hint={<Provenance kind="estimated" />}
                  />
                  <StatCard
                    label="Actual total"
                    value={formatMoney(reconcileResult.totals.actual)}
                    hint={<Provenance kind="actual" />}
                  />
                  <StatCard label="Absolute error" value={formatMoney(reconcileResult.totals.abs_error)} />
                  <StatCard label="Percentage error" value={formatPctRaw(reconcileResult.totals.pct_error)} />
                </div>

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
                      {reconcileResult.rows.map((row) => (
                        <tr key={row.category}>
                          <td>{row.category}</td>
                          <td className="gp-num">{formatMoney(row.forecast)}</td>
                          <td className="gp-num">{formatMoney(row.actual)}</td>
                          <td className="gp-num">{formatMoney(row.abs_error)}</td>
                          <td className="gp-num">{formatPctRaw(row.pct_error)}</td>
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

                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="rounded-md border border-red-200 bg-red-50 p-3">
                    <p className="text-sm font-medium text-red-800">Over estimate</p>
                    {reconcileResult.over_budget_categories.length === 0 ? (
                      <p className="mt-1 text-sm text-red-700">No category exceeded its estimate.</p>
                    ) : (
                      <p className="mt-1 text-sm text-red-700">
                        {reconcileResult.over_budget_categories.join(', ')}
                      </p>
                    )}
                  </div>
                  <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3">
                    <p className="text-sm font-medium text-emerald-800">At or under estimate</p>
                    {reconcileResult.under_budget_categories.length === 0 ? (
                      <p className="mt-1 text-sm text-emerald-700">Every category exceeded its estimate.</p>
                    ) : (
                      <p className="mt-1 text-sm text-emerald-700">
                        {reconcileResult.under_budget_categories.join(', ')}
                      </p>
                    )}
                  </div>
                </div>

                <div className="overflow-x-auto rounded border border-slate-200">
                  <table className="gp-table">
                    <tbody>
                      <tr>
                        <td className="text-slate-500">Income recorded</td>
                        <td className="gp-num">{formatMoney(reconcileResult.financial_impact.income_actual)}</td>
                      </tr>
                      <tr>
                        <td className="text-slate-500">Expenses recorded</td>
                        <td className="gp-num">{formatMoney(reconcileResult.financial_impact.expense_actual)}</td>
                      </tr>
                      <tr>
                        <td className="text-slate-500">Surplus (actual)</td>
                        <td className="gp-num">{formatMoney(reconcileResult.financial_impact.surplus_actual)}</td>
                      </tr>
                      <tr>
                        <td className="text-slate-500">Surplus projected at estimation time</td>
                        <td className="gp-num">
                          {formatMoney(reconcileResult.financial_impact.surplus_projected_at_estimation)}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <InlineNotice tone="info">{reconcileResult.financial_impact.note}</InlineNotice>
                {reconcileResult.next_forecast_note && (
                  <InlineNotice tone="info">{reconcileResult.next_forecast_note}</InlineNotice>
                )}
                {reconcileResult.forecast_preserved && (
                  <InlineNotice tone="success">
                    The original forecast for this month was preserved. Reconciliation appends an
                    evaluation row beside it rather than replacing it.
                  </InlineNotice>
                )}
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  )
}

