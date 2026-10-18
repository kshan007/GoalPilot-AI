import { useState } from 'react'
import { budgetsApi, errorMessage, metaApi } from '../api/client'
import type { BudgetInput } from '../api/types'
import { useAsync } from '../lib/useAsync'
import { formatMoney, formatPct } from '../lib/format'
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

function emptyBudget(): BudgetInput {
  return { category: '', monthly_limit: 0, classification: 'discretionary', is_active: true }
}

export default function Budgets() {
  const { data, loading, error, reload } = useAsync(
    () => Promise.all([budgetsApi.list(), metaApi.assumptions()]),
    [],
  )
  const [form, setForm] = useState<BudgetInput>(emptyBudget())
  const [editingId, setEditingId] = useState<number | null>(null)
  const [pending, setPending] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  if (loading) return <LoadingState label="Loading your budgets..." />
  if (error) return <ErrorState message={error} onRetry={reload} />

  const budgets = data ? data[0] : []
  const meta = data ? data[1] : null
  const totalLimits = budgets
    .filter((budget) => budget.is_active)
    .reduce((sum, budget) => sum + budget.monthly_limit, 0)

  async function submit() {
    setPending(true)
    setActionError(null)
    setNotice(null)
    try {
      if (editingId === null) {
        await budgetsApi.create(form)
        setNotice('Budget created.')
      } else {
        await budgetsApi.update(editingId, form)
        setNotice('Budget updated.')
      }
      setForm(emptyBudget())
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
      await budgetsApi.remove(id)
      setNotice('Budget removed.')
      if (editingId === id) {
        setEditingId(null)
        setForm(emptyBudget())
      }
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
        title="Budgets"
        description="A budget is a per-category monthly limit. Budgets are compared against recorded actuals in the reconciliation and budget-status views."
      />

      <Card
        title={editingId === null ? 'Add a budget' : `Edit budget #${editingId}`}
        description="Category names must match the categories used on your transactions, for example loan_payments or groceries."
        actions={
          editingId !== null ? (
            <Button
              tone="secondary"
              size="sm"
              onClick={() => {
                setEditingId(null)
                setForm(emptyBudget())
              }}
            >
              Cancel edit
            </Button>
          ) : undefined
        }
      >
        <div className="grid gap-4 sm:grid-cols-3">
          <Field
            label="Category"
            hint={meta ? `Known essential categories: ${meta.essential_categories.join(', ')}` : undefined}
          >
            <TextInput
              value={form.category}
              onChange={(value) => setForm({ ...form, category: value })}
              disabled={pending}
              placeholder="groceries"
            />
          </Field>
          <Field label="Monthly limit">
            <TextInput
              type="number"
              value={String(form.monthly_limit)}
              onChange={(value) => setForm({ ...form, monthly_limit: value === '' ? 0 : Number(value) })}
              disabled={pending}
            />
          </Field>
          <Field label="Classification">
            <SelectInput
              value={form.classification}
              onChange={(value) =>
                setForm({ ...form, classification: value as BudgetInput['classification'] })
              }
              options={[
                { value: 'essential', label: 'essential' },
                { value: 'discretionary', label: 'discretionary' },
              ]}
              disabled={pending}
            />
          </Field>
        </div>

        <div className="mt-4">
          <Checkbox
            label="Active"
            hint="Only active budgets are used by the reconciliation views."
            checked={form.is_active}
            disabled={pending}
            onChange={(value) => setForm({ ...form, is_active: value })}
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
          <Button pending={pending} disabled={form.category.trim() === ''} onClick={submit}>
            {editingId === null ? 'Add budget' : 'Save changes'}
          </Button>
        </div>
      </Card>

      <Card
        title={`Your budgets (${budgets.length})`}
        description={`Active monthly limits total ${formatMoney(totalLimits)}.`}
      >
        {budgets.length === 0 ? (
          <EmptyState
            title="No budgets set"
            message="Create a budget for a category to have reconciliation compare spending against a limit you defined."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="gp-table">
              <thead>
                <tr>
                  <th>Category</th>
                  <th className="gp-num">Monthly limit</th>
                  <th>Classification</th>
                  <th>Active</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {budgets.map((budget) => (
                  <tr key={budget.id}>
                    <td>{budget.category}</td>
                    <td className="gp-num">{formatMoney(budget.monthly_limit)}</td>
                    <td>{budget.classification}</td>
                    <td>
                      <Badge tone={budget.is_active ? 'positive' : 'neutral'}>
                        {budget.is_active ? 'active' : 'inactive'}
                      </Badge>
                    </td>
                    <td>
                      <div className="flex gap-2">
                        <Button
                          tone="secondary"
                          size="sm"
                          disabled={pending}
                          onClick={() => {
                            setForm({
                              category: budget.category,
                              monthly_limit: budget.monthly_limit,
                              classification: budget.classification,
                              is_active: budget.is_active,
                            })
                            setEditingId(budget.id)
                          }}
                        >
                          Edit
                        </Button>
                        <Button tone="danger" size="sm" disabled={pending} onClick={() => remove(budget.id)}>
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

      {meta && (
        <Card title="Assumption defaults in use" description={meta.note}>
          <div className="overflow-x-auto">
            <table className="gp-table">
              <tbody>
                {Object.entries(meta.defaults).map(([key, value]) => (
                  <tr key={key}>
                    <td className="text-slate-500">{key.replace(/_/g, ' ')}</td>
                    <td className="gp-num">
                      {typeof value === 'number' && value > 0 && value < 1
                        ? formatPct(value, 2)
                        : String(value)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-xs text-slate-500">
            Assumption fields below 1 are shown as percentages because they are stored as decimals.
          </p>
        </Card>
      )}
    </div>
  )
}
