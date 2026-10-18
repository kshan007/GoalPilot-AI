import { useState } from 'react'
import { Link } from 'react-router-dom'
import { errorMessage, metaApi, optimizeApi } from '../api/client'
import type { PlanAlternative, PlanResponse, ReadinessBlock } from '../api/types'
import { Explain } from '../components/Explain'
import { useAsync } from '../lib/useAsync'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  InlineNotice,
  PageHeader,
  StatCard,
  WarningList,
} from '../components/ui'
import { formatMoney, formatPct } from '../lib/format'

/** Option keys mean nothing to a person; these are the words they would use. */
const FRIENDLY_OPTION: Record<string, string> = {
  extend_deadline_12m: 'Take a little more time (+12 months)',
  extend_deadline_24m: 'Take more time (+24 months)',
  reduce_target: 'Aim for a smaller amount',
  enable_financing: 'Use a loan',
  financing: 'Use a loan',
  invest_for_goal: 'Put the money in an investment instead',
  increase_contribution: 'Save more each month',
  use_existing_savings: 'Use money you already have',
  reprioritise: 'Change how important this goal is',
}

function friendlyOption(option: string): string {
  return FRIENDLY_OPTION[option] ?? option.replace(/_/g, ' ')
}

function money(value: number): string {
  return formatMoney(value)
}

const READINESS_TONE: Record<string, 'positive' | 'warning' | 'negative'> = {
  ready: 'positive',
  emergency_fund_incomplete: 'warning',
  buffer_shortfall: 'warning',
  debt_stressed: 'negative',
  deficit: 'negative',
}

const READINESS_LABEL: Record<string, string> = {
  ready: 'Safety net in place',
  emergency_fund_incomplete: 'Emergency fund below guideline',
  buffer_shortfall: 'Monthly buffer cannot be met',
  debt_stressed: 'Debt repayments above your ceiling',
  deficit: 'Spending exceeds income',
}

function ReadinessCard({ readiness }: { readiness: ReadinessBlock }) {
  const emergency = readiness.emergency_fund
  const progress = Math.max(0, Math.min(1, emergency.progress))
  return (
    <Card
      title="Your financial safety net"
      description="This is separate from whether your goals are funded. A plan can reach every goal and still leave you exposed to a shock."
    >
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Badge tone={READINESS_TONE[readiness.status] ?? 'neutral'}>
          {READINESS_LABEL[readiness.status] ?? readiness.status}
        </Badge>
        {readiness.flags.map((flag) => (
          <span key={flag} className="text-xs text-slate-500">
            {flag.replace(/_/g, ' ')}
          </span>
        ))}
      </div>

      <div className="mb-2 flex items-baseline justify-between text-sm">
        <span className="font-medium text-slate-800">Emergency fund</span>
        <span className="text-slate-600">
          {formatMoney(emergency.current)} of {formatMoney(emergency.target)} ({formatPct(progress)})
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded bg-slate-200" role="progressbar" aria-valuenow={Math.round(progress * 100)} aria-valuemin={0} aria-valuemax={100}>
        <div
          className={progress >= 1 ? 'h-full bg-emerald-500' : progress >= 0.5 ? 'h-full bg-amber-500' : 'h-full bg-rose-500'}
          style={{ width: `${Math.round(progress * 100)}%` }}
        />
      </div>
      <p className="mt-2 text-xs text-slate-500">
        {emergency.gap > 0
          ? `${formatMoney(emergency.gap)} short of the ${emergency.target_months}-month guideline. The guideline is a planning rule of thumb, not a universal requirement.`
          : `Target met: ${emergency.target_months} months of essential expenses held in liquid savings.`}
      </p>

      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-500">Monthly money for goals</dt>
          <dd className="font-medium text-slate-800">{formatMoney(readiness.cash.available_goal_budget)}</dd>
          <dd className="text-xs text-slate-500">After the protected buffer</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-500">Protected buffer</dt>
          <dd className="font-medium text-slate-800">{formatMoney(readiness.protected_buffer.protected)}</dd>
          <dd className="text-xs text-slate-500">
            {readiness.protected_buffer.sustained
              ? 'Held each month'
              : `${formatMoney(readiness.protected_buffer.deficit)} short of the requested amount`}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-500">Debt repayments</dt>
          <dd className="font-medium text-slate-800">
            {formatPct(readiness.debt.emi_income_ratio)} of income
          </dd>
          <dd className="text-xs text-slate-500">
            Ceiling {formatPct(readiness.debt.emi_income_ratio_cap)}; {formatMoney(readiness.debt.headroom)} spare
          </dd>
        </div>
      </dl>
    </Card>
  )
}

export default function Plan() {
  const [plan, setPlan] = useState<PlanResponse | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { data: education } = useAsync(() => metaApi.education(), [])

  const monthlyTotal = plan
    ? plan.allocations.reduce(
        (total, row) => total + row.monthly_savings_contribution + row.monthly_investment_contribution,
        0,
      )
    : 0
  const loanTotal = plan
    ? plan.allocations.reduce((total, row) => total + row.loan_principal, 0)
    : 0
  const emiTotal = plan
    ? plan.allocations.reduce((total, row) => total + row.estimated_loan_emi, 0)
    : 0

  const helpFirst = (alternatives: PlanAlternative[]) => [
    ...alternatives.filter((option) => option.feasible),
    ...alternatives.filter((option) => !option.feasible),
  ]

  async function buildPlan() {
    setPending(true)
    setError(null)
    try {
      const result = await optimizeApi.plan({ algorithm: 'hybrid' })
      setPlan(result)
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Your plan"
        description="We look at the money coming in, the money going out and the goals you have set, then show you the simplest way to reach them. Nothing is paid, transferred or borrowed for you."
        actions={
          <Button onClick={() => void buildPlan()} disabled={pending}>
            {pending ? 'Working it out…' : plan ? 'Rebuild my plan' : 'Build my plan'}
          </Button>
        }
      />

      {!plan && !pending && (
        <EmptyState
          title="Let's work out your plan"
          message="Press Build my plan and we'll show how much to set aside each month, which goals you'll reach, and what to do about any that fall short. It takes a few seconds."
          action={
            <Button onClick={() => void buildPlan()}>Build my plan</Button>
          }
        />
      )}

      {pending && (
        <InlineNotice tone="info">
          Working out your plan. This usually takes a few seconds — longer the first time.
        </InlineNotice>
      )}

      {error && (
        <InlineNotice tone="warning">
          We could not build a plan: {error} You can try again, or check that your income and goals
          are filled in.
        </InlineNotice>
      )}

      {plan && (
        <>
          {plan.goals_funded ? (
            <InlineNotice tone="success">
              Good news — this plan covers every goal by its date. You need to set aside{' '}
              {money(monthlyTotal)} a month
              {loanTotal > 0 ? `, plus a loan repayment of ${money(emiTotal)} a month` : ''}.
            </InlineNotice>
          ) : (
            <InlineNotice tone="warning">
              This plan does not cover everything yet.{' '}
              {plan.unfunded_goals.length > 0
                ? `${plan.unfunded_goals.join(', ')} fall short by ${money(plan.total_shortfall)} by the target date.`
                : `The goals fall short by ${money(plan.total_shortfall)}.`}{' '}
              Scroll down for ways to close the gap.
            </InlineNotice>
          )}

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <StatCard
              label="Set aside each month"
              value={money(monthlyTotal)}
              hint="What you would put towards your goals every month."
            />
            <StatCard
              label="Borrowing"
              value={loanTotal > 0 ? money(loanTotal) : 'None'}
              hint={
                loanTotal > 0
                  ? `Repaid at about ${money(emiTotal)} a month.`
                  : 'This plan does not need a loan.'
              }
            />
            <StatCard
              label="Still short"
              value={plan.total_shortfall > 0 ? money(plan.total_shortfall) : 'Nothing'}
              tone={plan.total_shortfall > 0 ? 'negative' : 'positive'}
              hint="The amount your goals are short by on their dates."
            />
          </div>

          {plan.readiness && <ReadinessCard readiness={plan.readiness} />}

          {plan.warnings.length > 0 && <WarningList warnings={plan.warnings} />}

          <Card
            title="Goal by goal"
            description="What each goal costs, what this plan puts towards it, and whether it gets there in time."
          >
            <div className="overflow-x-auto">
              <table className="gp-table">
                <thead>
                  <tr>
                    <th>Goal</th>
                    <th className="gp-num">Cost by the target date</th>
                    <th className="gp-num">This plan provides</th>
                    <th>On track?</th>
                  </tr>
                </thead>
                <tbody>
                  {plan.allocations.map((row) => {
                    const funded = row.shortfall <= Math.max(1, row.future_goal_cost * 0.001)
                    return (
                      <tr key={row.goal_ref}>
                        <td>
                          {row.goal_id ? (
                            <Link className="font-medium text-accent-700 hover:underline" to={`/goals/${row.goal_id}`}>
                              {row.goal_name}
                            </Link>
                          ) : (
                            row.goal_name
                          )}
                        </td>
                        <td className="gp-num">{money(row.future_goal_cost)}</td>
                        <td className="gp-num">{money(row.projected_new_funding)}</td>
                        <td>
                          <span
                            className={
                              funded
                                ? 'rounded border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700'
                                : 'rounded border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800'
                            }
                          >
                            {funded ? 'Yes' : `Short by ${money(row.shortfall)}`}
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </Card>

          {plan.alternatives.length > 0 && (
            <Card
              title="Ways to close the gap"
              description="Each row is a single change to your goal, worked out against your own numbers. Nothing changes unless you decide to change it."
            >
              <ul className="space-y-3">
                {helpFirst(plan.alternatives).map((option, index) => (
                  <li
                    key={`${option.option}-${option.goal_ref}-${index}`}
                    className="rounded-lg border border-slate-200 p-4"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-slate-900">{friendlyOption(option.option)}</span>
                      {option.goal_name && (
                        <span className="text-xs text-slate-500">for {option.goal_name}</span>
                      )}
                      <span
                        className={
                          option.feasible
                            ? 'rounded border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700'
                            : 'rounded border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs font-medium text-slate-600'
                        }
                      >
                        {option.feasible ? 'would work' : 'not enough on its own'}
                      </span>
                    </div>
                    <p className="mt-1 text-sm text-slate-600">{option.change}</p>
                    <p className="mt-2 text-sm text-slate-700">{option.detail}</p>
                  </li>
                ))}
              </ul>
              <p className="mt-4 text-sm text-slate-600">
                To accept one of these, edit the goal on the{' '}
                <Link className="font-medium text-accent-700 hover:underline" to="/goals">
                  Goals
                </Link>{' '}
                page. Ask about a loan separately — nothing is applied for here.
              </p>
            </Card>
          )}

          <Card title="What this means">
            <div className="space-y-3">
              <Explain question="How is the monthly amount worked out?">
                <p>
                  We take the money left over after your essential spending, emergency savings and
                  any existing loan repayments, then spread it across your goals in order of
                  importance and urgency. Anything already saved for a goal counts towards it.
                </p>
              </Explain>
              <Explain question="Why is a loan sometimes suggested?">
                <p>
                  A loan only appears when it would genuinely close a gap and the repayment fits
                  inside a sensible share of your income. It always costs more overall because of
                  interest, and we never apply for credit on your behalf.
                </p>
              </Explain>
              <Explain question="Why does a goal fall short?">
                <p>
                  Either there is not enough time before the target date, or the monthly money
                  available is not enough for everything at once. Extending the date, trimming the
                  target or spreading goals out are the usual fixes.
                </p>
              </Explain>
              <Explain question="Is this financial advice?">
                <p>
                  No. This is a planning tool: it does the arithmetic and explains the trade-offs so
                  you can decide. It does not recommend a specific product, lender, fund or policy.
                </p>
              </Explain>
            </div>
          </Card>

          {education && education.items.length > 0 && (
            <Card
              title="Learn the ideas behind this plan"
              description="General financial principles, not personalised advice. Each item says where it comes from."
            >
              <dl className="space-y-3">
                {education.items.map((item) => (
                  <div key={item.topic} className="rounded-lg border border-slate-200 p-3">
                    <dt className="text-sm font-medium text-slate-900">{item.topic}</dt>
                    <dd className="mt-1 text-sm text-slate-700">{item.principle}</dd>
                    <dd className="mt-1 text-xs text-slate-500">{item.source}</dd>
                  </div>
                ))}
              </dl>
              <p className="mt-3 text-xs text-slate-500">{education.citation_policy}</p>
            </Card>
          )}

          <p className="text-xs text-slate-500">
            The detailed calculation and technical settings live in the{' '}
            <Link className="underline" to="/algorithms">
              admin area
            </Link>
            .
          </p>
        </>
      )}
    </div>
  )
}
