import { Link } from 'react-router-dom'
import { dashboardApi } from '../api/client'
import { useAsync } from '../lib/useAsync'
import { formatDateTime, formatMoney, formatNumber, formatPct, valueText } from '../lib/format'
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  KeyValueTable,
  LoadingState,
  PageHeader,
  StatCard,
  WarningList,
} from '../components/ui'
import {
  CategoryBreakdownChart,
  GoalFundingChart,
  IncomeVsExpenseChart,
  SavingsTrendChart,
} from '../components/Charts'

export default function Dashboard() {
  const { data, loading, error, reload } = useAsync(() => dashboardApi.read(), [])

  if (loading) return <LoadingState label="Loading your dashboard..." />
  if (error) return <ErrorState message={error} onRetry={reload} />
  if (!data) {
    return (
      <EmptyState
        title="No dashboard data"
        message="The API returned no dashboard payload. Reload the page or check the backend."
      />
    )
  }

  const { cashflow, goals, monthly, forecasts, debt, optimization } = data
  const hasRecords = monthly.trend.length > 0

  return (
    <div className="space-y-6">
      <PageHeader
        title="Home"
        description={`Your money at a glance, updated ${formatDateTime(data.as_of)}. Start with what came in and what went out this month, then check your goals.`}
        actions={
          <Link
            to="/monthly"
            className="rounded-md border border-slate-300 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Open monthly workspace
          </Link>
        }
      />

      <Card
        title="New here? Do these three things"
        description="You do not need to understand how any of the maths works — the app does it for you."
      >
        <ol className="grid gap-3 sm:grid-cols-3">
          {[
            {
              to: '/monthly',
              step: '1',
              title: 'Tell us your money in and out',
              body: 'Roughly what comes in each month, and what you spend on bills, food and travel.',
            },
            {
              to: '/goals',
              step: '2',
              title: 'Add what you are saving for',
              body: 'A bike, a course, a deposit. Give each one today’s price and when you want it.',
            },
            {
              to: '/optimize',
              step: '3',
              title: 'Get your plan',
              body: 'We work out how much to set aside each month and what to change if it does not fit.',
            },
          ].map((item) => (
            <li key={item.to} className="rounded-lg border border-slate-200 p-4">
              <Link to={item.to} className="group block">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-accent-50 text-xs font-semibold text-accent-700">
                  {item.step}
                </span>
                <p className="mt-2 font-medium text-slate-900 group-hover:text-accent-800">
                  {item.title}
                </p>
                <p className="mt-1 text-sm leading-relaxed text-slate-600">{item.body}</p>
              </Link>
            </li>
          ))}
        </ol>
      </Card>

      {!hasRecords && (
        <EmptyState
          title="No monthly records yet"
          message="Open the current month in the monthly workspace, add your income and expenses, and the trend charts below will fill in from your own data."
          action={
            <Link to="/monthly" className="text-sm font-medium text-accent-700 hover:underline">
              Go to the monthly workspace
            </Link>
          }
        />
      )}

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
          Situation
        </h2>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            label="Monthly surplus"
            value={formatMoney(cashflow.monthly_surplus)}
            hint={cashflow.is_deficit ? 'The month is in deficit' : 'Income minus obligations'}
            tone={cashflow.is_deficit ? 'negative' : 'positive'}
          />
          <StatCard
            label="Available cash for goals"
            value={formatMoney(cashflow.available_cash_for_goals)}
            hint="Liquid assets after the emergency buffer and goal earmarks"
          />
          <StatCard
            label="Emergency fund progress"
            value={formatPct(cashflow.emergency_fund_progress)}
            hint={`Target ${formatMoney(cashflow.emergency_fund_target)} at ${formatNumber(
              cashflow.emergency_months,
            )} months`}
          />
          <StatCard
            label="EMI to income"
            value={formatPct(cashflow.emi_income_ratio)}
            hint={`Cap ${formatPct(cashflow.emi_income_ratio_cap)}`}
            tone={cashflow.emi_income_ratio > cashflow.emi_income_ratio_cap ? 'warning' : 'neutral'}
          />
        </div>
      </section>

      <WarningList warnings={cashflow.warnings} />

      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="Cash flow" description="Derived from your recorded profile, income, assets and liabilities.">
          <KeyValueTable
            rows={[
              { key: 'Monthly income', value: formatMoney(cashflow.monthly_income) },
              { key: 'Essential expenses', value: formatMoney(cashflow.essential_expenses) },
              { key: 'Discretionary expenses', value: formatMoney(cashflow.discretionary_expenses) },
              { key: 'Existing EMI', value: formatMoney(cashflow.existing_emi) },
              { key: 'Liquid savings', value: formatMoney(cashflow.liquid_savings) },
              { key: 'Emergency savings', value: formatMoney(cashflow.emergency_savings) },
              { key: 'Usable existing investments', value: formatMoney(cashflow.usable_existing_investments) },
              { key: 'Non-liquid assets', value: formatMoney(cashflow.non_liquid_assets) },
              { key: 'Outstanding debt (principal)', value: formatMoney(cashflow.outstanding_debt) },
              { key: 'Emergency fund gap', value: formatMoney(cashflow.emergency_fund_gap) },
              { key: 'Earmarked goal funding', value: formatMoney(cashflow.earmarked_goal_funding) },
              { key: 'Savings target', value: formatMoney(cashflow.savings_target) },
              {
                key: 'Savings target attainment',
                value: (
                  <span className="inline-flex items-center gap-2">
                    {formatPct(cashflow.savings_target_attainment)}
                    {cashflow.savings_target_is_mandatory && <Badge tone="warning">mandatory</Badge>}
                  </span>
                ),
              },
            ]}
          />
        </Card>

        <Card
          title="Goals"
          description="This is a quick check of your monthly surplus and spare cash — not a full plan."
        >
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard label="On track" value={String(goals.on_track)} tone="positive" />
            <StatCard label="At risk" value={String(goals.at_risk)} tone="negative" />
            <StatCard label="Total remaining gap" value={formatMoney(goals.total_remaining_gap)} />
            <StatCard label="Required monthly" value={formatMoney(goals.total_required_monthly)} />
          </div>
          {goals.items.length === 0 ? (
            <div className="mt-4">
              <EmptyState
                title="No goals yet"
                message="Create at least one goal so the planner has something to solve."
                action={
                  <Link to="/goals" className="text-sm font-medium text-accent-700 hover:underline">
                    Create a goal
                  </Link>
                }
              />
            </div>
          ) : (
            <div className="mt-4 overflow-x-auto">
              <table className="gp-table">
                <thead>
                  <tr>
                    <th>Goal</th>
                    <th>Feasibility</th>
                    <th className="gp-num">Future target</th>
                    <th className="gp-num">Gap</th>
                  </tr>
                </thead>
                <tbody>
                  {goals.items.map((goal) => (
                    <tr key={goal.goal_ref}>
                      <td>{goal.name}</td>
                      <td>
                        <Badge tone={goal.feasibility === 'feasible' ? 'positive' : 'warning'}>
                          {goal.feasibility}
                        </Badge>
                      </td>
                      <td className="gp-num">{formatMoney(goal.future_target)}</td>
                      <td className="gp-num">{formatMoney(goal.remaining_gap)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="Income versus expenses" description="Actual and expected values across your monthly records.">
          <IncomeVsExpenseChart data={monthly.trend} />
        </Card>
        <Card title="Expense category breakdown">
          <CategoryBreakdownChart data={monthly.category_breakdown} />
        </Card>
        <Card title="Savings trend">
          <SavingsTrendChart data={monthly.trend} />
        </Card>
        <Card title="Goal funding">
          <GoalFundingChart data={goals.funding_chart} />
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="Debt" description="The monthly obligation is the EMI. Principal is a balance-sheet figure and is never added to it.">
          <KeyValueTable
            rows={[
              { key: 'Outstanding principal', value: formatMoney(debt.outstanding_principal) },
              { key: 'Monthly EMI', value: formatMoney(debt.monthly_emi) },
              { key: 'EMI to income', value: formatPct(debt.emi_income_ratio) },
              { key: 'Configured cap', value: formatPct(debt.emi_income_ratio_cap) },
              {
                key: 'Within cap',
                value: <Badge tone={debt.within_cap ? 'positive' : 'negative'}>{debt.within_cap ? 'yes' : 'no'}</Badge>,
              },
            ]}
          />
        </Card>

        <Card
          title="Your plan"
          description="The last plan we built for you, in plain terms. The detailed calculation lives in the admin area."
        >
          {optimization.last_plan ? (
            <div className="space-y-4">
              <KeyValueTable
                rows={[
                  {
                    key: 'Covers every goal',
                    value: (
                      <Badge
                        tone={
                          (optimization.last_plan.total_shortfall ?? 0) > 0 ? 'warning' : 'positive'
                        }
                      >
                        {(optimization.last_plan.total_shortfall ?? 0) > 0 ? 'not yet' : 'yes'}
                      </Badge>
                    ),
                  },
                  {
                    key: 'Still short',
                    value: formatMoney(optimization.last_plan.total_shortfall ?? 0),
                  },
                  {
                    key: 'Last updated',
                    value: formatDateTime(optimization.last_plan.created_at),
                  },
                ]}
              />
              <div className="flex flex-wrap gap-3 text-sm">
                <Link className="font-medium text-accent-700 hover:underline" to="/optimize">
                  Open my plan
                </Link>
                <Link className="font-medium text-accent-700 hover:underline" to="/goals">
                  Review my goals
                </Link>
              </div>
            </div>
          ) : (
            <EmptyState
              title="No plan yet"
              message="Build your first plan and we'll show how much to set aside each month and whether your goals fit."
              action={
                <Link className="font-medium text-accent-700 hover:underline" to="/optimize">
                  Build my plan
                </Link>
              }
            />
          )}
        </Card>
      </div>

      <Card
        title="What we expect next"
        description="Our estimates for the coming months, based on what you have recorded so far."
      >
        <div className="grid gap-6 xl:grid-cols-2">
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
              Latest estimates
            </p>
            {forecasts.latest.length === 0 ? (
              <EmptyState
                title="Nothing to estimate yet"
                message="Record a month of income and spending and we'll start estimating what is coming."
              />
            ) : (
              <div className="max-h-72 overflow-auto">
                <table className="gp-table">
                  <thead>
                    <tr>
                      <th>Month</th>
                      <th>Category</th>
                      <th className="gp-num">Amount</th>
                      <th>How sure we are</th>
                    </tr>
                  </thead>
                  <tbody>
                    {forecasts.latest.map((item) => (
                      <tr key={`${item.period}-${item.category}-${item.method}`}>
                        <td>{item.period}</td>
                        <td>{item.category}</td>
                        <td className="gp-num">{formatMoney(item.amount)}</td>
                        <td>
                          <Badge tone={item.is_provisional ? 'warning' : 'positive'}>
                            {item.is_provisional ? 'rough' : item.data_quality}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
              Categories that keep going over
            </p>
            {forecasts.persistent_overspend.length === 0 ? (
              <EmptyState
                title="Nothing keeps going over budget"
                message="We show a category here when it goes over its limit month after month."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="gp-table">
                  <tbody>
                    {forecasts.persistent_overspend.map((row, index) => (
                      <tr key={index}>
                        <td className="text-slate-500">{String((row as { category?: string }).category ?? index)}</td>
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
    </div>
  )
}


