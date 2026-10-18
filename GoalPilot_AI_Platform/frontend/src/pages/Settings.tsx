import { useEffect, useState } from 'react'
import { authApi, errorMessage, metaApi, preferencesApi } from '../api/client'
import type { LiquidityLevel, PreferencesInput, RiskLevel } from '../api/types'
import { useAsync } from '../lib/useAsync'
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

const RISK_LEVELS: RiskLevel[] = ['low', 'moderate', 'high']
const LIQUIDITY_LEVELS: LiquidityLevel[] = ['low', 'medium', 'high']

const ASSUMPTION_KEYS = [
  'annual_inflation',
  'investment_return',
  'savings_return',
  'loan_annual_rate',
  'loan_tenure_months',
  'emergency_months',
  'emi_income_ratio_cap',
] as const

type AssumptionKey = (typeof ASSUMPTION_KEYS)[number]

export default function Settings() {
  const { data, loading, error, reload } = useAsync(
    () => Promise.all([preferencesApi.read(), metaApi.assumptions()]),
    [],
  )

  const [form, setForm] = useState<PreferencesInput>({
    currency: 'INR',
    locale: 'en-IN',
    risk_tolerance: 'moderate',
    loss_ability: 'moderate',
    liquidity_requirement: 'medium',
    assumptions: {},
  })
  const [pending, setPending] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saved, setSaved] = useState<string | null>(null)

  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [passwordPending, setPasswordPending] = useState(false)
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [passwordNotice, setPasswordNotice] = useState<string | null>(null)

  useEffect(() => {
    if (!data) return
    const [preferences, meta] = data
    const assumptions: Record<string, number> = {}
    for (const key of ASSUMPTION_KEYS) {
      const stored = preferences.assumptions?.[key]
      const fallback = meta.defaults[key as keyof typeof meta.defaults]
      assumptions[key] = typeof stored === 'number' ? stored : typeof fallback === 'number' ? fallback : 0
    }
    setForm({
      currency: preferences.currency,
      locale: preferences.locale,
      risk_tolerance: preferences.risk_tolerance as RiskLevel,
      loss_ability: preferences.loss_ability as RiskLevel,
      liquidity_requirement: preferences.liquidity_requirement as LiquidityLevel,
      assumptions,
    })
  }, [data])

  if (loading) return <LoadingState label="Loading your preferences..." />
  if (error) return <ErrorState message={error} onRetry={reload} />

  const preferences = data ? data[0] : null
  const meta = data ? data[1] : null

  async function savePreferences() {
    setPending(true)
    setSaveError(null)
    setSaved(null)
    try {
      await preferencesApi.update(form)
      setSaved('Preferences saved.')
      reload()
    } catch (caught) {
      setSaveError(errorMessage(caught))
    } finally {
      setPending(false)
    }
  }

  async function changePassword() {
    setPasswordPending(true)
    setPasswordError(null)
    setPasswordNotice(null)
    try {
      const response = await authApi.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      })
      setPasswordNotice(response.message)
      setCurrentPassword('')
      setNewPassword('')
    } catch (caught) {
      setPasswordError(errorMessage(caught))
    } finally {
      setPasswordPending(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings"
        description="Preferences are stored on your account. Assumption defaults are the values the planner uses unless a plan request overrides them."
      />

      {!preferences ? (
        <EmptyState
          title="No preferences returned"
          message="The API returned no preference record for this account, so nothing can be edited here."
        />
      ) : (
        <Card
          title="Preferences"
          description="Currency and locale affect how values are displayed. Risk tolerance, loss ability and liquidity requirement are stored as separate fields."
        >
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Field label="Risk tolerance" hint="How much volatility you are willing to accept.">
              <SelectInput
                value={form.risk_tolerance}
                onChange={(value) => setForm({ ...form, risk_tolerance: value as RiskLevel })}
                options={RISK_LEVELS.map((value) => ({ value, label: value }))}
                disabled={pending}
              />
            </Field>
            <Field label="Loss ability" hint="How large a loss your finances can absorb.">
              <SelectInput
                value={form.loss_ability}
                onChange={(value) => setForm({ ...form, loss_ability: value as RiskLevel })}
                options={RISK_LEVELS.map((value) => ({ value, label: value }))}
                disabled={pending}
              />
            </Field>
            <Field label="Liquidity requirement">
              <SelectInput
                value={form.liquidity_requirement}
                onChange={(value) =>
                  setForm({ ...form, liquidity_requirement: value as LiquidityLevel })
                }
                options={LIQUIDITY_LEVELS.map((value) => ({ value, label: value }))}
                disabled={pending}
              />
            </Field>
            <Field label="Currency">
              <TextInput
                value={form.currency}
                onChange={(value) => setForm({ ...form, currency: value })}
                disabled={pending}
              />
            </Field>
            <Field label="Locale">
              <TextInput
                value={form.locale}
                onChange={(value) => setForm({ ...form, locale: value })}
                disabled={pending}
              />
            </Field>
          </div>

          <div className="mt-5">
            <InlineNotice tone="info">
              Risk tolerance and loss ability are stored separately on purpose. Neither is inferred
              from the other, and the platform never substitutes one for the other when a goal is
              assessed.
            </InlineNotice>
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
            <Button pending={pending} onClick={savePreferences}>
              Save preferences
            </Button>
          </div>
        </Card>
      )}

      <Card
        title="Assumption defaults"
        description={meta?.note ?? 'These are assumptions, not facts. Every plan reports the values it actually used.'}
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {ASSUMPTION_KEYS.map((key: AssumptionKey) => (
            <Field
              key={key}
              label={key.replace(/_/g, ' ')}
              hint={meta ? `Platform default: ${String(meta.defaults[key as keyof typeof meta.defaults])}` : undefined}
            >
              <TextInput
                type="number"
                step={0.005}
                value={String(form.assumptions[key] ?? 0)}
                onChange={(value) =>
                  setForm({
                    ...form,
                    assumptions: { ...form.assumptions, [key]: value === '' ? 0 : Number(value) },
                  })
                }
                disabled={pending}
              />
            </Field>
          ))}
        </div>
        <div className="mt-4">
          <Button pending={pending} onClick={savePreferences}>
            Save assumptions with preferences
          </Button>
        </div>
      </Card>

      {meta && (
        <Card
          title="Provenance rules"
          description="How the platform labels the origin of a number, as documented by the API."
        >
          <ul className="space-y-2 text-sm text-slate-700">
            {meta.provenance_rules.map((rule) => (
              <li key={rule} className="rounded border border-slate-200 bg-slate-50 px-3 py-2">
                {rule}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card
        title="Change password"
        description="Changing the password invalidates every existing session for the account, including this one."
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Current password">
            <TextInput
              type="password"
              value={currentPassword}
              onChange={setCurrentPassword}
              disabled={passwordPending}
            />
          </Field>
          <Field label="New password" hint="At least 8 characters and not only letters or only digits.">
            <TextInput
              type="password"
              value={newPassword}
              onChange={setNewPassword}
              disabled={passwordPending}
            />
          </Field>
        </div>

        {passwordError && (
          <div className="mt-4">
            <ErrorState message={passwordError} />
          </div>
        )}
        {passwordNotice && (
          <div className="mt-4">
            <InlineNotice tone="success">{passwordNotice}</InlineNotice>
          </div>
        )}

        <div className="mt-5">
          <Button pending={passwordPending} onClick={changePassword}>
            Change password
          </Button>
        </div>
      </Card>
    </div>
  )
}
