import { useState } from 'react'
import { assetsApi, errorMessage, goalsApi } from '../api/client'
import type { AssetInput } from '../api/types'
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

const ASSET_TYPES = ['liquid_savings', 'emergency_savings', 'investment', 'fixed_deposit', 'other']

function emptyAsset(): AssetInput {
  return {
    asset_type: 'liquid_savings',
    label: '',
    current_value: 0,
    is_liquid: true,
    usable_for_goals: true,
    annual_return: 0,
    risk_score: 0.2,
    earmarked_goal_id: null,
  }
}

export default function Assets() {
  const { data, loading, error, reload } = useAsync(
    () => Promise.all([assetsApi.list(), goalsApi.list()]),
    [],
  )
  const [form, setForm] = useState<AssetInput>(emptyAsset())
  const [editingId, setEditingId] = useState<number | null>(null)
  const [pending, setPending] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  if (loading) return <LoadingState label="Loading your assets..." />
  if (error) return <ErrorState message={error} onRetry={reload} />

  const assets = data ? data[0] : []
  const goals = data ? data[1] : []

  async function submit() {
    setPending(true)
    setActionError(null)
    setNotice(null)
    try {
      if (editingId === null) {
        await assetsApi.create(form)
        setNotice('Asset created.')
      } else {
        await assetsApi.update(editingId, form)
        setNotice('Asset updated.')
      }
      setForm(emptyAsset())
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
      await assetsApi.remove(id)
      setNotice('Asset removed.')
      if (editingId === id) {
        setEditingId(null)
        setForm(emptyAsset())
      }
      reload()
    } catch (caught) {
      setActionError(errorMessage(caught))
    } finally {
      setPending(false)
    }
  }

  const totalValue = assets.reduce((sum, asset) => sum + asset.current_value, 0)
  const usableValue = assets
    .filter((asset) => asset.usable_for_goals)
    .reduce((sum, asset) => sum + asset.current_value, 0)

  return (
    <div className="space-y-6">
      <PageHeader
        title="Assets"
        description="Only assets marked as usable for goals can be allocated by the planner. Emergency savings and non-liquid assets are excluded from the goal pool."
      />

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="gp-card p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Total asset value</p>
          <p className="mt-2 font-mono text-lg font-semibold tabular-nums text-slate-900">
            {formatMoney(totalValue)}
          </p>
        </div>
        <div className="gp-card p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
            Usable for goals
          </p>
          <p className="mt-2 font-mono text-lg font-semibold tabular-nums text-accent-700">
            {formatMoney(usableValue)}
          </p>
        </div>
      </div>

      <Card
        title={editingId === null ? 'Add an asset' : `Edit asset #${editingId}`}
        actions={
          editingId !== null ? (
            <Button
              tone="secondary"
              size="sm"
              onClick={() => {
                setEditingId(null)
                setForm(emptyAsset())
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
              value={form.asset_type}
              onChange={(value) => setForm({ ...form, asset_type: value as AssetInput['asset_type'] })}
              options={ASSET_TYPES.map((value) => ({ value, label: value.replace(/_/g, ' ') }))}
              disabled={pending}
            />
          </Field>
          <Field label="Label">
            <TextInput value={form.label} onChange={(value) => setForm({ ...form, label: value })} disabled={pending} />
          </Field>
          <Field label="Current value">
            <TextInput
              type="number"
              value={String(form.current_value)}
              onChange={(value) => setForm({ ...form, current_value: value === '' ? 0 : Number(value) })}
              disabled={pending}
            />
          </Field>
          <Field label="Annual return" hint="Decimal, e.g. 0.07.">
            <TextInput
              type="number"
              step={0.005}
              value={String(form.annual_return)}
              onChange={(value) => setForm({ ...form, annual_return: value === '' ? 0 : Number(value) })}
              disabled={pending}
            />
          </Field>
          <Field label="Risk score" hint="Between 0 and 1.">
            <TextInput
              type="number"
              step={0.05}
              value={String(form.risk_score)}
              onChange={(value) => setForm({ ...form, risk_score: value === '' ? 0 : Number(value) })}
              disabled={pending}
            />
          </Field>
          <Field label="Earmarked for goal" hint="Optional. An earmarked asset is excluded from the shared pool.">
            <SelectInput
              value={form.earmarked_goal_id === null ? '' : String(form.earmarked_goal_id)}
              onChange={(value) =>
                setForm({ ...form, earmarked_goal_id: value === '' ? null : Number(value) })
              }
              options={[
                { value: '', label: 'Not earmarked' },
                ...goals.map((goal) => ({ value: String(goal.id), label: goal.name })),
              ]}
              disabled={pending}
            />
          </Field>
        </div>

        <div className="mt-4 flex flex-wrap gap-5">
          <Checkbox
            label="Counts as liquid"
            checked={form.is_liquid}
            disabled={pending}
            onChange={(value) => setForm({ ...form, is_liquid: value })}
          />
          <Checkbox
            label="Usable for goals"
            checked={form.usable_for_goals}
            disabled={pending}
            onChange={(value) => setForm({ ...form, usable_for_goals: value })}
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
            {editingId === null ? 'Add asset' : 'Save changes'}
          </Button>
        </div>
      </Card>

      <Card title={`Your assets (${assets.length})`}>
        {assets.length === 0 ? (
          <EmptyState
            title="No assets recorded"
            message="Add at least one asset so the planner knows what funding already exists. Otherwise every goal starts from a gap equal to its full future cost."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="gp-table">
              <thead>
                <tr>
                  <th>Label</th>
                  <th>Type</th>
                  <th className="gp-num">Value</th>
                  <th>Liquid</th>
                  <th>Usable for goals</th>
                  <th className="gp-num">Return</th>
                  <th className="gp-num">Risk</th>
                  <th>Earmarked</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {assets.map((asset) => (
                  <tr key={asset.id}>
                    <td>{asset.label || '--'}</td>
                    <td>{asset.asset_type.replace(/_/g, ' ')}</td>
                    <td className="gp-num">{formatMoney(asset.current_value)}</td>
                    <td>
                      <Badge tone={asset.is_liquid ? 'positive' : 'neutral'}>
                        {asset.is_liquid ? 'yes' : 'no'}
                      </Badge>
                    </td>
                    <td>
                      <Badge tone={asset.usable_for_goals ? 'positive' : 'neutral'}>
                        {asset.usable_for_goals ? 'yes' : 'no'}
                      </Badge>
                    </td>
                    <td className="gp-num">{formatPct(asset.annual_return, 2)}</td>
                    <td className="gp-num">{asset.risk_score.toFixed(2)}</td>
                    <td>
                      {asset.earmarked_goal_id === null
                        ? '--'
                        : goals.find((goal) => goal.id === asset.earmarked_goal_id)?.name ??
                          `Goal #${asset.earmarked_goal_id}`}
                    </td>
                    <td>
                      <div className="flex gap-2">
                        <Button
                          tone="secondary"
                          size="sm"
                          disabled={pending}
                          onClick={() => {
                            const { id, ...rest } = asset
                            setForm(rest)
                            setEditingId(id)
                          }}
                        >
                          Edit
                        </Button>
                        <Button tone="danger" size="sm" disabled={pending} onClick={() => remove(asset.id)}>
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
