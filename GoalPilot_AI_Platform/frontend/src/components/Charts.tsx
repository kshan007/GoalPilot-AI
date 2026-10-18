import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { formatMoney, formatMoneyCompact } from '../lib/format'
import type { DashboardCategoryPoint, DashboardFundingPoint, DashboardTrendPoint } from '../api/types'
import { EmptyState } from './ui'

const AXIS = { fontSize: 11, fill: '#64748b' }

function tooltipMoney(value: unknown): string {
  return formatMoney(Number(value))
}

function tooltipPercent(value: unknown): string {
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return String(value)
  return `${(numeric * 100).toFixed(1)}%`
}

function ChartFrame({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: React.ReactNode
}) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
      {description && <p className="mb-3 mt-0.5 text-xs text-slate-500">{description}</p>}
      <div className="h-64 w-full">{children}</div>
    </div>
  )
}

export function IncomeVsExpenseChart({ data }: { data: DashboardTrendPoint[] }) {
  if (!data || data.length === 0) {
    return (
      <ChartFrame title="Income versus expenses">
        <div className="flex h-full items-center">
          <EmptyState
            title="No monthly records yet"
            message="Open a month in the monthly workspace and record income and expenses. The trend appears once monthly records exist."
          />
        </div>
      </ChartFrame>
    )
  }
  return (
    <ChartFrame
      title="Income versus expenses"
      description="Solid lines are recorded actuals; dashed lines are the values that were expected or estimated. Values are labelled by provenance."
    >
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="period" tick={AXIS} />
          <YAxis tick={AXIS} tickFormatter={(value: number) => formatMoneyCompact(value)} width={80} />
          <Tooltip formatter={tooltipMoney} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line type="monotone" dataKey="income_actual" name="Income (actual)" stroke="#1d4ed8" strokeWidth={2} />
          <Line
            type="monotone"
            dataKey="income_expected"
            name="Income (expected)"
            stroke="#93c5fd"
            strokeDasharray="5 3"
            strokeWidth={2}
          />
          <Line type="monotone" dataKey="expense_actual" name="Expenses (actual)" stroke="#b91c1c" strokeWidth={2} />
          <Line
            type="monotone"
            dataKey="expense_estimated"
            name="Expenses (estimated)"
            stroke="#fca5a5"
            strokeDasharray="5 3"
            strokeWidth={2}
          />
        </LineChart>
      </ResponsiveContainer>
    </ChartFrame>
  )
}

export function CategoryBreakdownChart({ data }: { data: DashboardCategoryPoint[] }) {
  if (!data || data.length === 0) {
    return (
      <ChartFrame title="Expense category breakdown">
        <div className="flex h-full items-center">
          <EmptyState
            title="No expense transactions yet"
            message="Add expense transactions to a month to see the category breakdown."
          />
        </div>
      </ChartFrame>
    )
  }
  return (
    <ChartFrame
      title="Expense category breakdown"
      description="Most recent month that has expense data. Actual and estimated amounts are shown separately."
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="category" tick={AXIS} interval={0} angle={-20} textAnchor="end" height={60} />
          <YAxis tick={AXIS} tickFormatter={(value: number) => formatMoneyCompact(value)} width={80} />
          <Tooltip formatter={tooltipMoney} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="actual" name="Actual" fill="#1d4ed8" radius={[3, 3, 0, 0]} />
          <Bar dataKey="estimated" name="Estimated" fill="#93c5fd" radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  )
}

export function SavingsTrendChart({ data }: { data: DashboardTrendPoint[] }) {
  if (!data || data.length === 0) {
    return (
      <ChartFrame title="Savings trend">
        <div className="flex h-full items-center">
          <EmptyState
            title="No surplus history yet"
            message="Record income and expenses for at least one month to build a savings trend."
          />
        </div>
      </ChartFrame>
    )
  }
  return (
    <ChartFrame
      title="Savings trend"
      description="Actual surplus is income minus expenses that were recorded. Projected surplus includes estimated amounts."
    >
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="period" tick={AXIS} />
          <YAxis tick={AXIS} tickFormatter={(value: number) => formatMoneyCompact(value)} width={80} />
          <Tooltip formatter={tooltipMoney} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line type="monotone" dataKey="surplus_actual" name="Surplus (actual)" stroke="#047857" strokeWidth={2} />
          <Line
            type="monotone"
            dataKey="surplus_projected"
            name="Surplus (projected)"
            stroke="#6ee7b7"
            strokeDasharray="5 3"
            strokeWidth={2}
          />
        </LineChart>
      </ResponsiveContainer>
    </ChartFrame>
  )
}

export function GoalFundingChart({ data }: { data: DashboardFundingPoint[] }) {
  if (!data || data.length === 0) {
    return (
      <ChartFrame title="Goal funding">
        <div className="flex h-full items-center">
          <EmptyState
            title="No goals yet"
            message="Create a goal to see its inflation-adjusted target against the funding already allocated to it."
          />
        </div>
      </ChartFrame>
    )
  }
  return (
    <ChartFrame
      title="Goal funding"
      description="Future target is the goal cost compounded at the stated inflation assumption (projected). Existing funding is the amount already recorded against the goal (actual)."
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="name" tick={AXIS} interval={0} angle={-20} textAnchor="end" height={60} />
          <YAxis tick={AXIS} tickFormatter={(value: number) => formatMoneyCompact(value)} width={80} />
          <Tooltip formatter={tooltipMoney} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="future_target" name="Future target (projected)" fill="#93c5fd" radius={[3, 3, 0, 0]} />
          <Bar dataKey="existing_funding" name="Funded so far (actual)" fill="#1d4ed8" radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  )
}

export function ForecastErrorChart({
  data,
}: {
  data: Array<{ period: string; forecast: number; actual: number; abs_error: number }>
}) {
  if (!data || data.length === 0) {
    return (
      <ChartFrame title="Forecast error trend">
        <div className="flex h-full items-center">
          <EmptyState
            title="Nothing reconciled yet"
            message="Forecast error is only reported for months that have been reconciled. Generate estimates, record actuals and reconcile a month."
          />
        </div>
      </ChartFrame>
    )
  }
  return (
    <ChartFrame
      title="Forecast error trend"
      description="Forecasted versus recorded spending for reconciled months, with the absolute error."
    >
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="period" tick={AXIS} />
          <YAxis tick={AXIS} tickFormatter={(value: number) => formatMoneyCompact(value)} width={80} />
          <Tooltip formatter={tooltipMoney} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line type="monotone" dataKey="forecast" name="Forecast (estimated)" stroke="#93c5fd" strokeWidth={2} />
          <Line type="monotone" dataKey="actual" name="Actual" stroke="#1d4ed8" strokeWidth={2} />
          <Line type="monotone" dataKey="abs_error" name="Absolute error" stroke="#b45309" strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </ChartFrame>
  )
}

export interface ComparisonBarRow {
  label: string
  weighted_goal_achievement: number | null
  pct_goals_met_by_deadline: number | null
}

export function ComparisonBars({ data }: { data: ComparisonBarRow[] }) {
  const usable = data.filter(
    (row) => row.weighted_goal_achievement !== null || row.pct_goals_met_by_deadline !== null,
  )
  if (usable.length === 0) {
    return (
      <EmptyState
        title="No arm produced a metric"
        message="An arm can only be scored if it actually ran and returned a feasible result. Unavailable arms are listed below with the reason no metric exists."
      />
    )
  }
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={usable} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="label" tick={AXIS} interval={0} angle={-15} textAnchor="end" height={70} />
          <YAxis tick={AXIS} tickFormatter={(value: number) => `${(value * 100).toFixed(0)}%`} width={60} />
          <Tooltip formatter={tooltipPercent} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar
            dataKey="weighted_goal_achievement"
            name="Weighted goal achievement"
            fill="#1d4ed8"
            radius={[3, 3, 0, 0]}
          />
          <Bar
            dataKey="pct_goals_met_by_deadline"
            name="Goals met by deadline"
            fill="#93c5fd"
            radius={[3, 3, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export function AccuracyChart({
  data,
}: {
  data: Array<{ period: string; forecast: number; actual: number; abs_error: number }>
}) {
  return ForecastErrorChart({ data })
}
