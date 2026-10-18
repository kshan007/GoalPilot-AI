import { useState } from 'react'
import { Link } from 'react-router-dom'
import { errorMessage, optimizeApi } from '../api/client'
import type { Algorithm, PlanResponse } from '../api/types'
import { useAsync } from '../lib/useAsync'
import { formatMoney, formatPct, formatScore, humanise, valueText } from '../lib/format'
import {
  Badge,
  Button,
  Card,
  Checkbox,
  EmptyState,
  ErrorState,
  Field,
  InlineNotice,
  JsonBlock,
  KeyValueTable,
  LoadingState,
  PageHeader,
  Provenance,
  SelectInput,
  StatCard,
  TextInput,
  WarningList,
} from '../components/ui'

interface AssumptionForm {
  annual_inflation: string
  investment_return: string
  savings_return: string
  loan_annual_rate: string
  loan_tenure_months: string
  max_new_loan: string
  allow_financing: boolean
}

export default function Optimize() {
  const { data: algorithms, loading, error, reload } = useAsync(() => optimizeApi.algorithms(), [])

  const [algorithm, setAlgorithm] = useState('lp')
  const [label, setLabel] = useState('')
  const [rlCheckpoint, setRlCheckpoint] = useState('')
  const [assumptions, setAssumptions] = useState<AssumptionForm>({
    annual_inflation: '0.03',
    investment_return: '0.05',
    savings_return: '0.00',
    loan_annual_rate: '0.12',
    loan_tenure_months: '60',
    max_new_loan: '150000',
    allow_financing: true,
  })
  const [plan, setPlan] = useState<PlanResponse | null>(null)
  const [pending, setPending] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  if (loading) return <LoadingState label="Loading algorithm availability..." />
  if (error) return <ErrorState message={error} onRetry={reload} />

  const list = algorithms ?? []
  const planLoanTotal = plan
    ? plan.allocations.reduce((total, allocation) => total + allocation.loan_principal, 0)
    : 0

  async function runPlan() {
    setPending(true)
    setActionError(null)
    try {
      const response = await optimizeApi.plan({
        algorithm: algorithm as Algorithm,
        assumptions: {
          annual_inflation: Number(assumptions.annual_inflation),
          investment_return: Number(assumptions.investment_return),
          savings_return: Number(assumptions.savings_return),
          loan_annual_rate: Number(assumptions.loan_annual_rate),
          loan_tenure_months: Number(assumptions.loan_tenure_months),
          max_new_loan: Number(assumptions.max_new_loan),
          allow_financing: assumptions.allow_financing,
        },
        rl_checkpoint: rlCheckpoint.trim() === '' ? null : rlCheckpoint.trim(),
        label,
      })
      setPlan(response)
    } catch (caught) {
      setActionError(errorMessage(caught))
    } finally {
      setPending(false)
    }
  }

  // Held in a local binding so TypeScript keeps the null-narrowing inside callbacks below.
  const planDiff = plan ? plan.diff : null
  const diffGoalChanges = planDiff ? planDiff.goal_changes : []
  const diffColumnKeys = diffGoalChanges.length > 0 ? Object.keys(diffGoalChanges[0]) : []

  return (
    <div className="space-y-6">
      <PageHeader
        title="Algorithms"
        description="Run a plan with a specific method, change the assumptions it uses, and inspect exactly how the result was produced — allocations, alternatives, constraints and diagnostics. For the everyday summary, use My plan."
      />

      <Card
        title="Algorithms available now"
        description="Availability is evaluated at request time. An arm is never reported ready merely because a file exists."
      >
        {list.length === 0 ? (
          <EmptyState
            title="No algorithm information"
            message="The API returned no algorithm list, so no plan can be configured."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="gp-table">
              <thead>
                <tr>
                  <th>Algorithm</th>
                  <th>Label</th>
                  <th>Status</th>
                  <th>Ready</th>
                  <th>Reason when unavailable</th>
                </tr>
              </thead>
              <tbody>
                {list.map((item) => (
                  <tr key={item.algorithm}>
                    <td className="font-mono text-xs">{item.algorithm}</td>
                    <td>{item.label}</td>
                    <td>{item.status}</td>
                    <td>
                      <Badge tone={item.ready ? 'positive' : 'negative'}>
                        {item.ready ? 'ready' : 'unavailable'}
                      </Badge>
                    </td>
                    <td className="text-xs text-slate-500">{item.reason ?? '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card
        title="Plan configuration"
        description="Assumption values are decimals, not percentages, and are stored with the run."
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field
            label="Algorithm"
            hint="Unavailable algorithms are disabled. The uniform savings rule is a control used only by the comparison endpoint."
          >
            <select
              className="gp-input"
              value={algorithm}
              onChange={(event) => setAlgorithm(event.target.value)}
              disabled={pending}
            >
              {list.map((item) => (
                <option key={item.algorithm} value={item.algorithm} disabled={!item.ready}>
                  {item.label}
                  {item.ready ? '' : ` (unavailable: ${item.reason ?? 'no reason recorded'})`}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Run label" hint="Optional. Shown in the run history.">
            <TextInput value={label} onChange={setLabel} disabled={pending} />
          </Field>
          <Field label="RL checkpoint" hint="Optional. Only used by the RL and hybrid algorithms.">
            <TextInput value={rlCheckpoint} onChange={setRlCheckpoint} disabled={pending} />
          </Field>
          <Field label="Annual inflation">
            <TextInput
              type="number"
              step={0.005}
              value={assumptions.annual_inflation}
              onChange={(value) => setAssumptions({ ...assumptions, annual_inflation: value })}
              disabled={pending}
            />
          </Field>
          <Field label="Investment return">
            <TextInput
              type="number"
              step={0.005}
              value={assumptions.investment_return}
              onChange={(value) => setAssumptions({ ...assumptions, investment_return: value })}
              disabled={pending}
            />
          </Field>
          <Field label="Savings return">
            <TextInput
              type="number"
              step={0.005}
              value={assumptions.savings_return}
              onChange={(value) => setAssumptions({ ...assumptions, savings_return: value })}
              disabled={pending}
            />
          </Field>
          <Field label="Loan annual rate">
            <TextInput
              type="number"
              step={0.005}
              value={assumptions.loan_annual_rate}
              onChange={(value) => setAssumptions({ ...assumptions, loan_annual_rate: value })}
              disabled={pending}
            />
          </Field>
          <Field label="Loan tenure (months)">
            <TextInput
              type="number"
              value={assumptions.loan_tenure_months}
              onChange={(value) => setAssumptions({ ...assumptions, loan_tenure_months: value })}
              disabled={pending}
            />
          </Field>
          <Field label="Maximum new loan">
            <TextInput
              type="number"
              value={assumptions.max_new_loan}
              onChange={(value) => setAssumptions({ ...assumptions, max_new_loan: value })}
              disabled={pending}
            />
          </Field>
        </div>

        <div className="mt-4">
          <Checkbox
            label="Allow financing"
            hint="When enabled, the planner may propose a loan where the resulting EMI fits the configured share of income. Financing is never used merely to make a goal appear funded."
            checked={assumptions.allow_financing}
            disabled={pending}
            onChange={(value) => setAssumptions({ ...assumptions, allow_financing: value })}
          />
        </div>

        {actionError && (
          <div className="mt-4">
            <ErrorState message={actionError} />
          </div>
        )}

        <div className="mt-5">
          <Button pending={pending} onClick={runPlan}>
            Run plan
          </Button>
        </div>
      </Card>

      {!plan ? (
        <EmptyState
          title="No plan has been run in this session"
          message="Configure the assumptions and run a plan. Results appear here only when the API returns them."
        />
      ) : (
        <>
          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Run" value={`#${plan.run_id}`} hint={plan.algorithm_label} />
            <StatCard
              label="Plan valid"
              value={plan.feasible ? 'yes' : 'no'}
              tone={plan.feasible ? 'positive' : 'negative'}
              hint={`All hard constraints satisfied. Status: ${plan.status}`}
            />
            <StatCard
              label="All goals funded"
              value={plan.goals_funded ? 'yes' : 'no'}
              tone={plan.goals_funded ? 'positive' : 'negative'}
              hint={
                plan.goals_funded
                  ? 'Every goal reaches its target by its deadline.'
                  : `${plan.unfunded_goals.length} goal(s) fall short by ${formatMoney(plan.total_shortfall)} at their deadline.`
              }
            />
            <StatCard
              label="Objective score"
              value={plan.objective_value === null ? '--' : formatScore(plan.objective_value)}
              hint="Priority-weighted shortfall penalty. A score, not a rupee amount — see the definition below."
            />
            <StatCard label="Runtime" value={`${plan.runtime_ms} ms`} />
            <StatCard label="Model version" value={plan.model_version} />
            <StatCard label="Config version" value={plan.config_version} />
            <StatCard
              label="Allocations returned"
              value={String(plan.allocations.length)}
              hint={<Provenance kind="projected" />}
            />
            <StatCard label="Warnings" value={String(plan.warnings.length)} />
          </section>

          {plan.fallback_reason && (
            <InlineNotice tone="warning">
              This run fell back from the requested algorithm: {plan.fallback_reason}
            </InlineNotice>
          )}

          {!plan.goals_funded && (
            <InlineNotice tone="warning">
              This plan cannot meet every goal from the available budget. Per-goal routes — more
              time, a smaller target, existing cash, a loan inside your EMI ceiling, or investing
              the contribution — are worked out on the{' '}
              <Link className="font-medium underline" to="/goals">
                Goals
              </Link>{' '}
              page, and summarised on{' '}
              <Link className="font-medium underline" to="/recommendations">
                Recommendations
              </Link>
              .
            </InlineNotice>
          )}

          <WarningList warnings={plan.warnings} />

          <Card
            title="Run validation and summary"
            description="The arm's own status and feasibility flag, plus the summary block it returned."
          >
            <div className="overflow-x-auto">
              <table className="gp-table">
                <tbody>
                  <tr>
                    <td className="text-slate-500">Requested algorithm</td>
                    <td>{plan.algorithm_label}</td>
                  </tr>
                  <tr>
                    <td className="text-slate-500">Status</td>
                    <td>{plan.status}</td>
                  </tr>
                  <tr>
                    <td className="text-slate-500">Plan valid (constraints)</td>
                    <td>{plan.feasible ? 'yes' : 'no'}</td>
                  </tr>
                  <tr>
                    <td className="text-slate-500">All goals funded by deadline</td>
                    <td>
                      {plan.goals_funded
                        ? 'yes'
                        : `no — ${plan.unfunded_goals.join(', ')} short ${formatMoney(plan.total_shortfall)}`}
                    </td>
                  </tr>
                  <tr>
                    <td className="text-slate-500">Financial readiness</td>
                    <td>
                      {plan.readiness?.status ?? '--'}
                      {plan.readiness?.note ? (
                        <span className="block text-xs text-slate-500">{plan.readiness.note}</span>
                      ) : null}
                    </td>
                  </tr>
                  <tr>
                    <td className="text-slate-500">Objective score, defined</td>
                    <td className="text-sm text-slate-700">
                      {plan.objective_definition ?? 'No definition was recorded for this run.'}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div className="mt-4">
              <p className="mb-2 text-sm font-medium text-slate-700">Summary block</p>
              {(plan.algorithm === 'rl' || plan.algorithm === 'hybrid') && (
                <div className="mb-3">
                  <InlineNotice tone="info">
                    {plan.algorithm === 'hybrid' ? (
                      <>
                        The summary is this plan's own arithmetic: the LP allocation under the
                        investment capacity the RL stage proposed. The shared simulator allocates
                        the monthly budget to goals before it considers a new EMI, so it cannot
                        replay a plan that contributes and borrows in the same month; its metrics
                        are kept in diagnostics for comparison only.
                        {planLoanTotal > 0 && (
                          <> This plan borrows {formatMoney(planLoanTotal)} within your EMI ceiling.</>
                        )}
                      </>
                    ) : (
                      <>
                        The summary is the simulator replaying this plan to your last goal deadline.
                        Its achievement and shortfall figures are measured at each goal's deadline,
                        and new borrowing is disabled in the replay so every arm sits on one basis —
                        a loan therefore never appears here. The amounts the plan assigns are in the
                        allocation table below.
                      </>
                    )}
                  </InlineNotice>
                </div>
              )}
              {Object.keys(plan.summary).length === 0 ? (
                <EmptyState title="No summary returned" message="The plan returned an empty summary block." />
              ) : (
                <KeyValueTable
                  rows={Object.entries(plan.summary).map(([key, value]) => ({
                    key: humanise(key),
                    value: valueText(value),
                  }))}
                />
              )}
            </div>
          </Card>

          <Card title="Allocation" description="What the optimiser assigned to each goal, by funding source.">
            {plan.allocations.length === 0 ? (
              <EmptyState
                title="No allocations returned"
                message="The solver returned no allocation rows, so there is nothing to display. Check the warnings above."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="gp-table">
                  <thead>
                    <tr>
                      <th>Goal</th>
                      <th className="gp-num">Funding gap</th>
                      <th className="gp-num">Future cost</th>
                      <th className="gp-num" title="Savings and assets the plan uses right now, from this month's cash">From cash now</th>
                      <th className="gp-num">Existing assets</th>
                      <th className="gp-num">Monthly savings</th>
                      <th className="gp-num">Monthly investment</th>
                      <th className="gp-num">Loan principal</th>
                      <th className="gp-num">Estimated EMI</th>
                      <th className="gp-num">Shortfall</th>
                      <th className="gp-num">Achievement</th>
                      <th className="gp-num">Projected new funding</th>
                    </tr>
                  </thead>
                  <tbody>
                    {plan.allocations.map((allocation) => (
                      <tr key={allocation.goal_ref}>
                        <td>{allocation.goal_name || allocation.goal_ref}</td>
                        <td className="gp-num">{formatMoney(allocation.funding_gap)}</td>
                        <td className="gp-num">{formatMoney(allocation.future_goal_cost)}</td>
                        <td className="gp-num">{formatMoney(allocation.initial_savings_allocated)}</td>
                        <td className="gp-num">{formatMoney(allocation.existing_assets_allocated)}</td>
                        <td className="gp-num">{formatMoney(allocation.monthly_savings_contribution)}</td>
                        <td className="gp-num">{formatMoney(allocation.monthly_investment_contribution)}</td>
                        <td className="gp-num">{formatMoney(allocation.loan_principal)}</td>
                        <td className="gp-num">{formatMoney(allocation.estimated_loan_emi)}</td>
                        <td className="gp-num">{formatMoney(allocation.shortfall)}</td>
                        <td className="gp-num">{formatPct(allocation.achievement_ratio)}</td>
                        <td className="gp-num">{formatMoney(allocation.projected_new_funding)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          {plan.alternatives.length > 0 && (
            <Card
              title="Alternatives evaluated for this plan"
              description="Each row re-solves this plan's own constraints with exactly one change — a later deadline, a smaller target, or financing. Nothing here is applied to your goals; the numbers are what that change would achieve."
            >
              <div className="overflow-x-auto">
                <table className="gp-table">
                  <thead>
                    <tr>
                      <th>Option</th>
                      <th>Goal</th>
                      <th>Change</th>
                      <th>Result</th>
                      <th className="gp-num">Required monthly</th>
                      <th>What it achieves</th>
                    </tr>
                  </thead>
                  <tbody>
                    {plan.alternatives.map((alternative, index) => (
                      <tr key={`${alternative.option}-${alternative.goal_ref}-${index}`}>
                        <td className="capitalize">{humanise(alternative.option)}</td>
                        <td>{alternative.goal_name || '—'}</td>
                        <td>{alternative.change}</td>
                        <td>
                          <span
                            className={
                              alternative.feasible
                                ? 'rounded border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700'
                                : 'rounded border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800'
                            }
                          >
                            {alternative.feasible ? 'meets goal' : 'still short'}
                          </span>
                        </td>
                        <td className="gp-num">{formatMoney(alternative.required_monthly)}</td>
                        <td>{alternative.detail}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-3 text-xs text-slate-500">
                Measured with {plan.alternatives[0]?.evaluated_with}.
              </p>
            </Card>
          )}

          <Card title="Per-goal projections" description="Independently computed projections that the plan is measured against.">
            {plan.goal_projections.length === 0 ? (
              <EmptyState
                title="No projections returned"
                message="The plan did not include per-goal projections."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="gp-table">
                  <thead>
                    <tr>
                      <th>Goal</th>
                      <th>Months left</th>
                      <th className="gp-num">Future target</th>
                      <th className="gp-num" title="Money already set aside for this goal before the plan was run">Already set aside</th>
                      <th className="gp-num">Remaining gap</th>
                      <th className="gp-num">Required monthly</th>
                      <th className="gp-num">Planned monthly</th>
                      <th className="gp-num">Projected funding</th>
                      <th className="gp-num">Projected shortfall</th>
                      <th>Feasibility</th>
                      <th>Uncertainty</th>
                    </tr>
                  </thead>
                  <tbody>
                    {plan.goal_projections.map((projection) => (
                      <tr key={projection.goal_ref}>
                        <td>{projection.name}</td>
                        <td>{projection.months_remaining}</td>
                        <td className="gp-num">{formatMoney(projection.future_target)}</td>
                        <td className="gp-num">{formatMoney(projection.existing_funding)}</td>
                        <td className="gp-num">{formatMoney(projection.remaining_gap)}</td>
                        <td className="gp-num">{formatMoney(projection.required_monthly_contribution)}</td>
                        <td className="gp-num">
                          {projection.planned_monthly_contribution === null
                            ? '--'
                            : formatMoney(projection.planned_monthly_contribution)}
                        </td>
                        <td className="gp-num">
                          {projection.projected_funding === null
                            ? '--'
                            : formatMoney(projection.projected_funding)}
                        </td>
                        <td className="gp-num">
                          {projection.projected_shortfall === null
                            ? '--'
                            : formatMoney(projection.projected_shortfall)}
                        </td>
                        <td>
                          <Badge tone={projection.feasibility === 'feasible' ? 'positive' : 'warning'}>
                            {projection.feasibility}
                          </Badge>
                        </td>
                        <td className="text-xs text-slate-500">{projection.uncertainty}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <div className="grid gap-6 xl:grid-cols-2">
            <Card title="Constraint diagnostics" description="Which constraints the solver applied and how they behaved.">
              {Object.keys(plan.constraints).length === 0 ? (
                <EmptyState title="No constraints reported" message="The plan returned an empty constraints block." />
              ) : (
                <JsonBlock value={plan.constraints} label="constraints" />
              )}
            </Card>
            <Card title="Solver diagnostics">
              {Object.keys(plan.diagnostics).length === 0 ? (
                <EmptyState title="No diagnostics reported" message="The plan returned an empty diagnostics block." />
              ) : (
                <JsonBlock value={plan.diagnostics} label="diagnostics" />
              )}
            </Card>
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <Card title="Assumptions actually used" description="Copied from the run record, not from the form.">
              {Object.keys(plan.assumptions).length === 0 ? (
                <EmptyState title="No assumptions recorded" message="The run did not record its assumptions." />
              ) : (
                <JsonBlock value={plan.assumptions} label="assumptions" />
              )}
            </Card>
            <Card title="Cash flow at the time of the run">
              {Object.keys(plan.cashflow).length === 0 ? (
                <EmptyState title="No cash-flow snapshot" message="The plan returned no cash-flow snapshot." />
              ) : (
                <JsonBlock value={plan.cashflow} label="cash flow" />
              )}
            </Card>
          </div>

          <Card
            title="What changed since the previous plan"
            description="The diff is computed by the backend against the previous run of the same kind."
          >
            {!planDiff ? (
              <EmptyState
                title="No previous run to compare against"
                message="This is the first plan of its kind for this account, so there is nothing to diff."
              />
            ) : (
              <div className="space-y-4">
                <InlineNotice tone={planDiff.changed ? 'info' : 'success'}>
                  {planDiff.changed
                    ? planDiff.summary || 'The plan changed relative to the previous run.'
                    : 'No change relative to the previous run.'}
                </InlineNotice>
                <p className="text-sm text-slate-600">
                  {planDiff.previous_run_id === null
                    ? 'No previous run id was recorded.'
                    : `Previous run: #${planDiff.previous_run_id}.`}
                </p>
                {diffGoalChanges.length === 0 ? (
                  <EmptyState
                    title="No per-goal changes"
                    message="No goal-level change was reported between the two runs."
                  />
                ) : (
                  <div className="overflow-x-auto">
                    <table className="gp-table">
                      <thead>
                        <tr>
                          {diffColumnKeys.map((key) => (
                            <th key={key}>{key.replace(/_/g, ' ')}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {diffGoalChanges.map((change, index) => (
                          <tr key={index}>
                            {diffColumnKeys.map((key) => (
                              <td key={key}>{valueText((change as Record<string, unknown>)[key])}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {Object.keys(planDiff.totals).length > 0 && (
                  <div>
                    <p className="mb-2 text-sm font-medium text-slate-700">Totals</p>
                    <JsonBlock value={planDiff.totals} label="totals" />
                  </div>
                )}
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  )
}

