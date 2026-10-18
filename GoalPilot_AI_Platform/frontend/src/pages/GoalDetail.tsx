import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { errorMessage, goalsApi } from '../api/client'
import { useAsync } from '../lib/useAsync'
import { formatDate, formatMoney, formatPct, humanise } from '../lib/format'

/** Alternative rows mix option keys, booleans and prose; render each in its natural voice. */
function alternativeText(key: string, value: unknown): string {
  if (key === 'option') return humanise(String(value ?? ''))
  if (key === 'affordable') return value === true ? 'yes' : value === false ? 'no' : '--'
  return String(value ?? '--')
}
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  InlineNotice,
  KeyValueTable,
  LoadingState,
  PageHeader,
  TextInput,
  WarningList,
} from '../components/ui'

export default function GoalDetailPage() {
  const { id } = useParams<{ id: string }>()
  const goalId = Number(id)
  const { data, loading, error, reload } = useAsync(() => goalsApi.detail(goalId), [goalId])

  const [amount, setAmount] = useState('')
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10))
  const [note, setNote] = useState('')
  const [source, setSource] = useState('manual')
  const [pending, setPending] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  if (!Number.isFinite(goalId)) {
    return <ErrorState message="This goal id is not a number." />
  }
  if (loading) return <LoadingState label="Loading the goal..." />
  if (error) return <ErrorState message={error} onRetry={reload} />
  if (!data) return <EmptyState title="Goal not found" message="The API returned no detail for this goal." />

  const { goal, projection, alternatives, contributions, assumptions } = data

  async function addContribution() {
    setPending(true)
    setActionError(null)
    setNotice(null)
    try {
      await goalsApi.addContribution(goalId, {
        amount: Number(amount),
        contribution_date: date,
        source,
        note,
      })
      setAmount('')
      setNote('')
      setNotice('Contribution recorded. The funded amount increased by the contributed amount.')
      reload()
    } catch (caught) {
      setActionError(errorMessage(caught))
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={goal.name}
        description={
          <>
            {goal.goal_type} goal, target {formatDate(goal.target_date)}. Priority {goal.priority},
            criticality {goal.criticality}.
          </>
        }
        actions={
          <Link
            to="/goals"
            className="rounded-md border border-slate-300 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Back to goals
          </Link>
        }
      />

      <div className="grid gap-6 xl:grid-cols-2">
        <Card
          title="Projection"
          description={assumptions.note}
        >
          <KeyValueTable
            rows={[
              { key: 'Current cost (today)', value: formatMoney(projection.current_cost) },
              {
                key: 'Future target (projected)',
                value: formatMoney(projection.future_target),
              },
              { key: 'Existing funding (actual)', value: formatMoney(projection.existing_funding) },
              { key: 'Remaining gap', value: formatMoney(projection.remaining_gap) },
              { key: 'Months remaining', value: String(projection.months_remaining) },
              {
                key: 'Required monthly contribution',
                value: formatMoney(projection.required_monthly_contribution),
              },
              {
                key: 'Planned monthly contribution',
                value:
                  projection.planned_monthly_contribution === null
                    ? 'No optimisation run exists yet'
                    : formatMoney(projection.planned_monthly_contribution),
              },
              {
                key: 'Projected funding at deadline',
                value:
                  projection.projected_funding === null
                    ? '--'
                    : formatMoney(projection.projected_funding),
              },
              {
                key: 'Projected shortfall',
                value:
                  projection.projected_shortfall === null
                    ? '--'
                    : formatMoney(projection.projected_shortfall),
              },
              {
                key: 'Achievement ratio',
                value:
                  projection.achievement_ratio === null
                    ? '--'
                    : formatPct(projection.achievement_ratio),
              },
              {
                key: 'Feasibility',
                value: (
                  <Badge tone={projection.feasibility === 'feasible' ? 'positive' : 'warning'}>
                    {projection.feasibility}
                  </Badge>
                ),
              },
              { key: 'Uncertainty', value: projection.uncertainty },
              { key: 'Inflation assumption', value: formatPct(projection.inflation_assumption, 2) },
              {
                key: 'Investment return assumption',
                value: formatPct(projection.investment_return_assumption, 2),
              },
            ]}
          />
          <div className="mt-4">
            <WarningList warnings={projection.notes} />
          </div>
        </Card>

        <Card
          title="Contributions"
          description="Recording a contribution adds to the funded amount. It never replaces it."
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Amount">
              <TextInput
                type="number"
                value={amount}
                onChange={setAmount}
                disabled={pending}
                placeholder="0.00"
              />
            </Field>
            <Field label="Date">
              <TextInput type="date" value={date} onChange={setDate} disabled={pending} />
            </Field>
            <Field label="Source">
              <TextInput value={source} onChange={setSource} disabled={pending} placeholder="manual" />
            </Field>
            <Field label="Note">
              <TextInput value={note} onChange={setNote} disabled={pending} />
            </Field>
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

          <div className="mt-4">
            <Button pending={pending} disabled={amount === ''} onClick={addContribution}>
              Record contribution
            </Button>
          </div>

          <div className="mt-5">
            {contributions.length === 0 ? (
              <EmptyState
                title="No contributions recorded"
                message="Record a contribution above. Each one is stored with its date, source and note."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="gp-table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th className="gp-num">Amount</th>
                      <th>Source</th>
                      <th>Note</th>
                    </tr>
                  </thead>
                  <tbody>
                    {contributions.map((contribution) => (
                      <tr key={contribution.id}>
                        <td>{formatDate(contribution.contribution_date)}</td>
                        <td className="gp-num">{formatMoney(contribution.amount)}</td>
                        <td>{contribution.source}</td>
                        <td className="text-xs text-slate-500">{contribution.note || '--'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Card>
      </div>

      <Card
        title="Suggested alternatives"
        description="Arithmetic options derived from your own surplus and available cash. These are options, not advice."
      >
        {alternatives.length === 0 ? (
          <EmptyState
            title="No alternatives suggested"
            message="The backend returned no alternative for this goal, which means the current structure is already workable or there is nothing to flex."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="gp-table">
              <thead>
                <tr>
                  {Object.keys(alternatives[0]).map((key) => (
                    <th key={key}>{humanise(key)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {alternatives.map((alternative, index) => (
                  <tr key={index}>
                    {Object.keys(alternatives[0]).map((key) => (
                      <td key={key}>{alternativeText(key, alternative[key])}</td>
                    ))}
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
