import { useState } from 'react'
import { Link } from 'react-router-dom'
import { goalsApi, errorMessage } from '../api/client'
import type { GoalInput } from '../api/types'
import { useAsync } from '../lib/useAsync'
import { formatDate, formatMoney, formatPct } from '../lib/format'
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
  SelectInput,
  TextInput,
} from '../components/ui'

const GOAL_TYPES = [
  'education',
  'higher_studies',
  'vehicle',
  'home',
  'wedding',
  'retirement',
  'travel',
  'emergency',
  'custom',
]

const LIQUIDITY = ['low', 'medium', 'high']
const STATUSES = ['active', 'paused', 'completed', 'archived']

function emptyGoal(): GoalInput {
  const nextYear = new Date()
  nextYear.setFullYear(nextYear.getFullYear() + 1)
  return {
    name: '',
    purpose: '',
    goal_type: 'custom',
    current_cost: 100000,
    target_date: nextYear.toISOString().slice(0, 10),
    current_funded_amount: 0,
    priority: 3,
    criticality: 3,
    date_flexible: false,
    amount_flexible: false,
    liquidity_requirement: 'medium',
    risk_constraint: 0.5,
    status: 'active',
  }
}

export default function Goals() {
  const { data, loading, error, reload } = useAsync(() => goalsApi.list(), [])
  const [form, setForm] = useState<GoalInput>(emptyGoal())
  const [editingId, setEditingId] = useState<number | null>(null)
  const [pending, setPending] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  if (loading) return <LoadingState label="Loading your goals..." />
  if (error) return <ErrorState message={error} onRetry={reload} />

  const goals = data ?? []

  async function submit() {
    setPending(true)
    setActionError(null)
    setNotice(null)
    try {
      if (editingId === null) {
        await goalsApi.create(form)
        setNotice('Goal created.')
      } else {
        await goalsApi.update(editingId, form)
        setNotice('Goal updated.')
      }
      setForm(emptyGoal())
      setEditingId(null)
      reload()
    } catch (caught) {
      setActionError(errorMessage(caught))
    } finally {
      setPending(false)
    }
  }

  async function remove(id: number) {
    setPending(true)
    setActionError(null)
    setNotice(null)
    try {
      await goalsApi.remove(id)
      setNotice('Goal deleted.')
      if (editingId === id) {
        setEditingId(null)
        setForm(emptyGoal())
      }
      reload()
    } catch (caught) {
      setActionError(errorMessage(caught))
    } finally {
      setPending(false)
    }
  }

  function startEdit(goal: (typeof goals)[number]) {
    const { id, created_at, ...rest } = goal
    setForm(rest)
    setEditingId(id)
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="My goals"
        description="A goal is something you are saving towards — a bike, a course, a deposit. Give it what it costs today, when you want it, and how much it matters to you. We work out what it will cost by then and what you need to put aside."
      />

      <Card
        title={editingId === null ? 'Add a goal' : `Edit goal #${editingId}`}
        description="Enter today's price — we allow for rising prices between now and the target date."
        actions={
          editingId !== null ? (
            <Button
              tone="secondary"
              size="sm"
              onClick={() => {
                setEditingId(null)
                setForm(emptyGoal())
              }}
            >
              Cancel edit
            </Button>
          ) : undefined
        }
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Name">
            <TextInput value={form.name} onChange={(value) => setForm({ ...form, name: value })} disabled={pending} />
          </Field>
          <Field label="Purpose" hint="Optional free text.">
            <TextInput value={form.purpose} onChange={(value) => setForm({ ...form, purpose: value })} disabled={pending} />
          </Field>
          <Field label="Goal type">
            <SelectInput
              value={form.goal_type}
              onChange={(value) => setForm({ ...form, goal_type: value })}
              options={GOAL_TYPES.map((type) => ({ value: type, label: type }))}
              disabled={pending}
            />
          </Field>
          <Field label="Current cost">
            <TextInput
              type="number"
              value={String(form.current_cost)}
              onChange={(value) => setForm({ ...form, current_cost: value === '' ? 0 : Number(value) })}
              disabled={pending}
            />
          </Field>
          <Field label="Target date">
            <TextInput
              type="date"
              value={form.target_date}
              onChange={(value) => setForm({ ...form, target_date: value })}
              disabled={pending}
            />
          </Field>
          <Field label="Already funded">
            <TextInput
              type="number"
              value={String(form.current_funded_amount)}
              onChange={(value) =>
                setForm({ ...form, current_funded_amount: value === '' ? 0 : Number(value) })
              }
              disabled={pending}
            />
          </Field>
          <Field label="Priority" hint="1 is highest, 5 is lowest.">
            <SelectInput
              value={String(form.priority)}
              onChange={(value) => setForm({ ...form, priority: Number(value) })}
              options={[1, 2, 3, 4, 5].map((value) => ({ value: String(value), label: String(value) }))}
              disabled={pending}
            />
          </Field>
          <Field label="Criticality" hint="1 is most critical, 5 is least.">
            <SelectInput
              value={String(form.criticality)}
              onChange={(value) => setForm({ ...form, criticality: Number(value) })}
              options={[1, 2, 3, 4, 5].map((value) => ({ value: String(value), label: String(value) }))}
              disabled={pending}
            />
          </Field>
          <Field label="Liquidity requirement">
            <SelectInput
              value={form.liquidity_requirement}
              onChange={(value) => setForm({ ...form, liquidity_requirement: value })}
              options={LIQUIDITY.map((value) => ({ value, label: value }))}
              disabled={pending}
            />
          </Field>
          <Field
            label="How cautious should we be with this goal?"
            hint="0 means you are happy to take some risk to get there sooner; 1 means keep it safe. Most people leave this at 0.5."
          >
            <TextInput
              type="number"
              step={0.05}
              value={String(form.risk_constraint)}
              onChange={(value) => setForm({ ...form, risk_constraint: value === '' ? 0 : Number(value) })}
              disabled={pending}
            />
          </Field>
          <Field label="Status">
            <SelectInput
              value={form.status}
              onChange={(value) => setForm({ ...form, status: value })}
              options={STATUSES.map((value) => ({ value, label: value }))}
              disabled={pending}
            />
          </Field>
        </div>

        <div className="mt-4 flex flex-wrap gap-5">
          <Checkbox
            label="The target date is flexible"
            checked={form.date_flexible}
            disabled={pending}
            onChange={(value) => setForm({ ...form, date_flexible: value })}
          />
          <Checkbox
            label="The target amount is flexible"
            checked={form.amount_flexible}
            disabled={pending}
            onChange={(value) => setForm({ ...form, amount_flexible: value })}
          />
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

        <div className="mt-5">
          <Button pending={pending} onClick={submit}>
            {editingId === null ? 'Create goal' : 'Save changes'}
          </Button>
        </div>
      </Card>

      <Card title={`Your goals (${goals.length})`}>
        {goals.length === 0 ? (
          <EmptyState
            title="No goals yet"
            message="Add your first goal above. Without at least one active goal the optimiser and the comparison have nothing to solve."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="gp-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Target date</th>
                  <th className="gp-num">Current cost</th>
                  <th className="gp-num">Funded</th>
                  <th>Priority</th>
                  <th>Flexible</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {goals.map((goal) => (
                  <tr key={goal.id}>
                    <td>
                      <Link to={`/goals/${goal.id}`} className="font-medium text-accent-700 hover:underline">
                        {goal.name}
                      </Link>
                    </td>
                    <td>{goal.goal_type}</td>
                    <td>
                      <Badge tone={goal.status === 'active' ? 'positive' : 'neutral'}>{goal.status}</Badge>
                    </td>
                    <td>{formatDate(goal.target_date)}</td>
                    <td className="gp-num">{formatMoney(goal.current_cost)}</td>
                    <td className="gp-num">
                      {formatMoney(goal.current_funded_amount)}
                      <span className="ml-1 text-xs text-slate-500">
                        ({formatPct(goal.current_cost > 0 ? goal.current_funded_amount / goal.current_cost : 0)})
                      </span>
                    </td>
                    <td>
                      P{goal.priority} / C{goal.criticality}
                    </td>
                    <td className="text-xs text-slate-500">
                      {[goal.date_flexible ? 'date' : null, goal.amount_flexible ? 'amount' : null]
                        .filter(Boolean)
                        .join(', ') || 'none'}
                    </td>
                    <td>
                      <div className="flex gap-2">
                        <Button tone="secondary" size="sm" onClick={() => startEdit(goal)} disabled={pending}>
                          Edit
                        </Button>
                        <Button tone="danger" size="sm" onClick={() => remove(goal.id)} disabled={pending}>
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
      </Card>
    </div>
  )
}
