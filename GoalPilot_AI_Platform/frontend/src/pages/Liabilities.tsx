import { useState } from 'react'
import { errorMessage, liabilitiesApi } from '../api/client'
import type { LiabilityInput } from '../api/types'
import { useAsync } from '../lib/useAsync'
import { formatMoney, formatPct } from '../lib/format'
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  InlineNotice,
  LoadingState,
  PageHeader,
  SelectInput,
  TextInput,
} from '../components/ui'

const LIABILITY_TYPES = [
  'home_loan',
  'vehicle_loan',
  'personal_loan',
  'education_loan',
  'credit_card',
  'other',
]

function emptyLiability(): LiabilityInput {
  return {
    liability_type: 'home_loan',
    label: '',
    outstanding_principal: 0,
    annual_interest_rate: 0.09,
    emi_amount: 0,
    remaining_tenure_months: 0,
  }
}

export default function Liabilities() {
  const { data, loading, error, reload } = useAsync(() => liabilitiesApi.list(), [])
  const [form, setForm] = useState<LiabilityInput>(emptyLiability())
  const [editingId, setEditingId] = useState<number | null>(null)
  const [pending, setPending] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  if (loading) return <LoadingState label="Loading your liabilities..." />
  if (error) return <ErrorState message={error} onRetry={reload} />

  const liabilities = data ?? []
  const totalPrincipal = liabilities.reduce((sum, item) => sum + item.outstanding_principal, 0)
  const totalEmi = liabilities.reduce((sum, item) => sum + item.emi_amount, 0)

  async function submit() {
    setPending(true)
    setActionError(null)
    setNotice(null)
    try {
      if (editingId === null) {
        await liabilitiesApi.create(form)
        setNotice('Liability created.')
      } else {
        await liabilitiesApi.update(editingId, form)
        setNotice('Liability updated.')
      }
      setForm(emptyLiability())
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
      await liabilitiesApi.remove(id)
      setNotice('Liability removed.')
      if (editingId === id) {
        setEditingId(null)
        setForm(emptyLiability())
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
        title="Liabilities"
        description="The monthly obligation is the EMI, because it already contains principal and interest. The outstanding principal is a balance-sheet figure and is never added to it."
      />

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="gp-card p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
            Outstanding principal
          </p>
          <p className="mt-2 font-mono text-lg font-semibold tabular-nums text-slate-900">
            {formatMoney(totalPrincipal)}
          </p>
        </div>
        <div className="gp-card p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
            Monthly EMI obligation
          </p>
          <p className="mt-2 font-mono text-lg font-semibold tabular-nums text-amber-700">
            {formatMoney(totalEmi)}
          </p>
        </div>
      </div>

      <Card
        title={editingId === null ? 'Add a liability' : `Edit liability #${editingId}`}
        actions={
          editingId !== null ? (
            <Button
              tone="secondary"
              size="sm"
              onClick={() => {
                setEditingId(null)
                setForm(emptyLiability())
              }}
            >
              Cancel edit
            </Button>
          ) : undefined
        }
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Type">
            <SelectInput
              value={form.liability_type}
              onChange={(value) =>
                setForm({ ...form, liability_type: value as LiabilityInput['liability_type'] })
              }
              options={LIABILITY_TYPES.map((value) => ({ value, label: value.replace(/_/g, ' ') }))}
              disabled={pending}
            />
          </Field>
          <Field label="Label">
            <TextInput value={form.label} onChange={(value) => setForm({ ...form, label: value })} disabled={pending} />
          </Field>
          <Field label="Outstanding principal">
            <TextInput
              type="number"
              value={String(form.outstanding_principal)}
              onChange={(value) =>
                setForm({ ...form, outstanding_principal: value === '' ? 0 : Number(value) })
              }
              disabled={pending}
            />
          </Field>
          <Field label="Annual interest rate" hint="Decimal, e.g. 0.09 for 9 per cent.">
            <TextInput
              type="number"
              step={0.005}
              value={String(form.annual_interest_rate)}
              onChange={(value) =>
                setForm({ ...form, annual_interest_rate: value === '' ? 0 : Number(value) })
              }
              disabled={pending}
            />
          </Field>
          <Field
            label="EMI amount"
            hint="Required whenever there is an outstanding balance with a remaining tenure."
          >
            <TextInput
              type="number"
              value={String(form.emi_amount)}
              onChange={(value) => setForm({ ...form, emi_amount: value === '' ? 0 : Number(value) })}
              disabled={pending}
            />
          </Field>
          <Field label="Remaining tenure (months)">
            <TextInput
              type="number"
              value={String(form.remaining_tenure_months)}
              onChange={(value) =>
                setForm({ ...form, remaining_tenure_months: value === '' ? 0 : Number(value) })
              }
              disabled={pending}
            />
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

        <div className="mt-5">
          <Button pending={pending} onClick={submit}>
            {editingId === null ? 'Add liability' : 'Save changes'}
          </Button>
        </div>
      </Card>

      <Card title={`Your liabilities (${liabilities.length})`}>
        {liabilities.length === 0 ? (
          <EmptyState
            title="No liabilities recorded"
            message="If you have no loans or credit-card balances, there is nothing to add here. Otherwise record the EMI, because that is the monthly cash-flow obligation."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="gp-table">
              <thead>
                <tr>
                  <th>Label</th>
                  <th>Type</th>
                  <th className="gp-num">Principal</th>
                  <th className="gp-num">Rate</th>
                  <th className="gp-num">EMI</th>
                  <th>Tenure</th>
                  <th className="gp-num">Total interest if held</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {liabilities.map((liability) => (
                  <tr key={liability.id}>
                    <td>{liability.label || '--'}</td>
                    <td>{liability.liability_type.replace(/_/g, ' ')}</td>
                    <td className="gp-num">{formatMoney(liability.outstanding_principal)}</td>
                    <td className="gp-num">{formatPct(liability.annual_interest_rate, 2)}</td>
                    <td className="gp-num">{formatMoney(liability.emi_amount)}</td>
                    <td>{liability.remaining_tenure_months} months</td>
                    <td className="gp-num">{formatMoney(liability.total_interest_if_held_to_tenure)}</td>
                    <td>
                      <div className="flex gap-2">
                        <Button
                          tone="secondary"
                          size="sm"
                          disabled={pending}
                          onClick={() => {
                            setForm({
                              liability_type: liability.liability_type,
                              label: liability.label,
                              outstanding_principal: liability.outstanding_principal,
                              annual_interest_rate: liability.annual_interest_rate,
                              emi_amount: liability.emi_amount,
                              remaining_tenure_months: liability.remaining_tenure_months,
                            })
                            setEditingId(liability.id)
                          }}
                        >
                          Edit
                        </Button>
                        <Button tone="danger" size="sm" disabled={pending} onClick={() => remove(liability.id)}>
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
