import { useEffect, useState } from 'react'
import { profileApi, errorMessage } from '../api/client'
import type { ProfileInput } from '../api/types'
import { useAsync } from '../lib/useAsync'
import { formatMoney, formatPct } from '../lib/format'
import {
  Button,
  Card,
  Checkbox,
  EmptyState,
  ErrorState,
  Field,
  InlineNotice,
  KeyValueTable,
  LoadingState,
  PageHeader,
  TextInput,
} from '../components/ui'

const EMPTY_PROFILE: ProfileInput = {
  monthly_income: 0,
  essential_expenses: 0,
  discretionary_expenses: 0,
  monthly_savings_target: 0,
  savings_target_is_mandatory: false,
  preferred_cash_buffer: 0,
  willing_to_adjust_discretionary: true,
  emergency_months: 6,
  emi_income_ratio_cap: 0.35,
  risk_capacity: 0.5,
  inflation_assumption: 0.03,
  investment_return_assumption: 0.05,
  savings_return_assumption: 0.0,
  loan_interest_assumption: 0.12,
}

type NumericKey = {
  [K in keyof ProfileInput]: ProfileInput[K] extends number ? K : never
}[keyof ProfileInput]

const NUMERIC_FIELDS: Array<{ key: NumericKey; label: string; hint?: string; step?: number }> = [
  {
    key: 'monthly_income',
    label: 'Monthly income',
    hint: 'Fallback only: the planner reads your income sources, which are the source of truth.',
  },
  { key: 'essential_expenses', label: 'Essential expenses' },
  { key: 'discretionary_expenses', label: 'Discretionary expenses' },
  { key: 'monthly_savings_target', label: 'Monthly savings target' },
  { key: 'preferred_cash_buffer', label: 'Preferred cash buffer' },
  { key: 'emergency_months', label: 'Emergency fund months', hint: 'Between 0 and 36.' },
  { key: 'emi_income_ratio_cap', label: 'EMI to income cap', hint: 'As a decimal, e.g. 0.35 for 35 per cent.', step: 0.01 },
  { key: 'risk_capacity', label: 'Risk capacity', hint: 'Between 0 and 1. Distinct from your stated risk tolerance.', step: 0.01 },
  { key: 'inflation_assumption', label: 'Inflation assumption', hint: 'Decimal, e.g. 0.03.', step: 0.005 },
  { key: 'investment_return_assumption', label: 'Investment return assumption', step: 0.005 },
  { key: 'savings_return_assumption', label: 'Savings return assumption', step: 0.005 },
  { key: 'loan_interest_assumption', label: 'Loan interest assumption', step: 0.005 },
]

export default function ProfilePage() {
  const { data, loading, error, reload, setData } = useAsync(() => profileApi.read(), [])
  const [form, setForm] = useState<ProfileInput>(EMPTY_PROFILE)
  const [pending, setPending] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saved, setSaved] = useState<string | null>(null)

  useEffect(() => {
    if (data?.profile) {
      const { id, ...rest } = data.profile
      setForm(rest)
    }
  }, [data])

  if (loading) return <LoadingState label="Loading your financial profile..." />
  if (error) return <ErrorState message={error} onRetry={reload} />

  async function handleSave() {
    setPending(true)
    setSaveError(null)
    setSaved(null)
    try {
      await profileApi.update(form)
      setSaved('Profile saved. The cash-flow summary has been recalculated.')
      reload()
    } catch (caught) {
      setSaveError(errorMessage(caught))
    } finally {
      setPending(false)
    }
  }

  const summary = data?.summary ?? null

  return (
    <div className="space-y-6">
      <PageHeader
        title="Financial profile"
        description="These are the inputs the planner reads. Amounts are monthly. Assumption fields are decimals, not percentages."
      />

      {!data?.profile && (
        <EmptyState
          title="No financial profile has been saved yet"
          message="Fill in the form below and save. The cash-flow summary only appears once a profile and at least one income source exist."
        />
      )}

      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="Profile inputs" description="Saving replaces the stored profile with these values.">
          <div className="grid gap-4 sm:grid-cols-2">
            {NUMERIC_FIELDS.map((field) => (
              <Field key={field.key} label={field.label} hint={field.hint}>
                <TextInput
                  type="number"
                  step={field.step ?? 1}
                  value={String(form[field.key])}
                  disabled={pending}
                  onChange={(value) =>
                    setForm((current) => ({
                      ...current,
                      [field.key]: value === '' ? 0 : Number(value),
                    }))
                  }
                />
              </Field>
            ))}
          </div>

          <div className="mt-4 space-y-3">
            <Checkbox
              label="The monthly savings target is mandatory"
              hint="When enabled, the planner treats the target as a hard constraint rather than a preference."
              checked={form.savings_target_is_mandatory}
              disabled={pending}
              onChange={(value) => setForm((current) => ({ ...current, savings_target_is_mandatory: value }))}
            />
            <Checkbox
              label="I am willing to adjust discretionary spending"
              hint="When enabled, the planner may treat part of discretionary spending as flexible."
              checked={form.willing_to_adjust_discretionary}
              disabled={pending}
              onChange={(value) => setForm((current) => ({ ...current, willing_to_adjust_discretionary: value }))}
            />
          </div>

          {saveError && (
            <div className="mt-4">
              <ErrorState message={saveError} />
            </div>
          )}
          {saved && (
            <div className="mt-4">
              <InlineNotice tone="success">{saved}</InlineNotice>
            </div>
          )}

          <div className="mt-5">
            <Button pending={pending} onClick={handleSave}>
              Save profile
            </Button>
          </div>
        </Card>

        <Card
          title="Cash-flow summary"
          description="Derived by the backend from the profile, income sources, assets and liabilities."
        >
          {summary ? (
            <KeyValueTable
              rows={[
                { key: 'Monthly income', value: formatMoney(summary.monthly_income) },
                { key: 'Essential expenses', value: formatMoney(summary.essential_expenses) },
                { key: 'Discretionary expenses', value: formatMoney(summary.discretionary_expenses) },
                { key: 'Existing EMI', value: formatMoney(summary.existing_emi) },
                { key: 'Monthly surplus', value: formatMoney(summary.monthly_surplus) },
                { key: 'Emergency fund target', value: formatMoney(summary.emergency_fund_target) },
                { key: 'Emergency fund gap', value: formatMoney(summary.emergency_fund_gap) },
                { key: 'Emergency fund progress', value: formatPct(summary.emergency_fund_progress) },
                { key: 'Available cash for goals', value: formatMoney(summary.available_cash_for_goals) },
                { key: 'Situation tier', value: summary.situation_tier },
              ]}
            />
          ) : (
            <EmptyState
              title="Summary not available"
              message="A saved profile and at least one income source are required before the summary can be derived."
            />
          )}
          {summary && summary.warnings.length > 0 && (
            <div className="mt-4 space-y-2">
              {summary.warnings.map((warning) => (
                <InlineNotice key={warning} tone="warning">
                  {warning}
                </InlineNotice>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
