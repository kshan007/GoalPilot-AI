import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  assetsApi,
  errorMessage,
  incomeApi,
  liabilitiesApi,
  onboardingApi,
  preferencesApi,
  profileApi,
} from '../api/client'
import type { AssetInput, LiabilityInput, PreferencesInput, ProfileInput } from '../api/types'
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
  KeyValueTable,
  LoadingState,
  PageHeader,
  SelectInput,
  TextInput,
} from '../components/ui'

const STEPS = [
  'Welcome',
  'Income',
  'Savings and assets',
  'Liabilities',
  'Savings preferences',
  'Risk and planning preferences',
  'Summary',
]

const INCOME_TYPES = ['salary', 'freelance', 'business', 'rental', 'other']
const FREQUENCIES = ['monthly', 'annual', 'quarterly', 'weekly', 'one_time']
const STABILITIES = ['stable', 'variable', 'uncertain']
const ASSET_TYPES = ['liquid_savings', 'emergency_savings', 'investment', 'fixed_deposit', 'other']
const LIABILITY_TYPES = [
  'home_loan',
  'vehicle_loan',
  'personal_loan',
  'education_loan',
  'credit_card',
  'other',
]

interface IncomeDraft {
  source_type: string
  label: string
  amount: string
  frequency: string
  stability: string
  is_recurring: boolean
}

interface AssetDraft {
  asset_type: string
  label: string
  current_value: string
  is_liquid: boolean
  usable_for_goals: boolean
  annual_return: string
  risk_score: string
}

interface LiabilityDraft {
  liability_type: string
  label: string
  outstanding_principal: string
  annual_interest_rate: string
  emi_amount: string
  remaining_tenure_months: string
}

/**
 * Documented defaults, mirroring the backend's own defaults (3% inflation, 5% investment
 * return, 0% savings return, 12% loan interest, 6-month emergency guideline, 0.35 EMI cap).
 * Used only until the user has saved a financial profile of their own — they are assumptions,
 * and every one of them is editable on this page.
 */
const DEFAULT_PROFILE_DRAFT: ProfileInput = {
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

export default function Onboarding() {
  const navigate = useNavigate()
  const { data, loading, error, reload } = useAsync(
    () =>
      Promise.all([
        onboardingApi.read(),
        profileApi.read(),
        preferencesApi.read(),
        incomeApi.list(),
        assetsApi.list(),
        liabilitiesApi.list(),
      ]),
    [],
  )

  const [step, setStep] = useState(0)
  const [pending, setPending] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const [editingIncomeId, setEditingIncomeId] = useState<number | null>(null)
  const [incomeDraft, setIncomeDraft] = useState<IncomeDraft>({
    source_type: 'salary',
    label: '',
    amount: '',
    frequency: 'monthly',
    stability: 'stable',
    is_recurring: true,
  })
  const [assetDraft, setAssetDraft] = useState<AssetDraft>({
    asset_type: 'liquid_savings',
    label: '',
    current_value: '',
    is_liquid: true,
    usable_for_goals: true,
    annual_return: '0',
    risk_score: '0.2',
  })
  const [liabilityDraft, setLiabilityDraft] = useState<LiabilityDraft>({
    liability_type: 'home_loan',
    label: '',
    outstanding_principal: '',
    annual_interest_rate: '0.09',
    emi_amount: '',
    remaining_tenure_months: '0',
  })
  // Non-nullable from the start. A brand-new user has no saved profile, so a nullable draft used
  // to stay null forever and the page reported "Onboarding data could not be loaded" on a
  // perfectly successful 200 response. Seeding documented defaults removes that failure mode.
  const [profileDraft, setProfileDraft] = useState<ProfileInput>(DEFAULT_PROFILE_DRAFT)
  const [prefsDraft, setPrefsDraft] = useState<PreferencesInput | null>(null)

  // Documented defaults, mirroring the backend's own defaults. Used only when the user has not
  // saved a financial profile yet, so the wizard can open for a first-time user.
  useEffect(() => {
    if (!data) return
    const [onboarding, profile] = data
    setStep(onboarding.step)
    if (profile.profile) {
      const { id, ...rest } = profile.profile
      setProfileDraft(rest)
    } else {
      setProfileDraft(DEFAULT_PROFILE_DRAFT)
    }
  }, [data])

  useEffect(() => {
    if (!data) return
    const preferences = data[2]
    setPrefsDraft({
      currency: preferences.currency,
      locale: preferences.locale,
      risk_tolerance: preferences.risk_tolerance as PreferencesInput['risk_tolerance'],
      loss_ability: preferences.loss_ability as PreferencesInput['loss_ability'],
      liquidity_requirement:
        preferences.liquidity_requirement as PreferencesInput['liquidity_requirement'],
      assumptions: {},
    })
  }, [data])

  if (loading) return <LoadingState label="Loading your onboarding progress..." />
  if (error) return <ErrorState message={error} onRetry={reload} />

  // A brand-new user has no saved financial profile, so the draft used to stay null forever and
  // this branch reported "Onboarding data could not be loaded" on a perfectly successful 200
  // response (and Retry could never recover). The drafts are now always seeded — from the saved
  // profile when one exists, otherwise from the documented defaults — so this branch is a
  // one-frame loading state, never a false error.
  if (!data || !profileDraft || !prefsDraft) {
    return <LoadingState label="Preparing your onboarding steps..." />
  }

  const [onboarding, profileResponse, , income, assets, liabilities] = data
  const summary = profileResponse.summary

  // The planner derives income from the income sources, not from profile.monthly_income. This
  // step has no income input of its own, so the saved profile used to carry 0 and the backend
  // (rightly) refused expenses against zero income. Show the figure that is actually used, and
  // send it with the profile so the stored aggregate agrees with the sources.
  const monthlyIncomeFromSources = income
    .filter((source) => source.is_active)
    .reduce((total, source) => total + source.monthly_equivalent, 0)

  const profilePayload: ProfileInput = {
    ...profileDraft,
    monthly_income:
      monthlyIncomeFromSources > 0 ? monthlyIncomeFromSources : profileDraft.monthly_income,
  }

  async function run<T>(action: () => Promise<T>, message?: string): Promise<T | null> {
    setPending(true)
    setActionError(null)
    setNotice(null)
    try {
      const result = await action()
      if (message) setNotice(message)
      setPending(false)
      return result
    } catch (caught) {
      setActionError(errorMessage(caught))
      setPending(false)
      return null
    }
  }

  async function goTo(nextStep: number) {
    const clamped = Math.max(0, Math.min(STEPS.length - 1, nextStep))
    const result = await run(() => onboardingApi.setStep(clamped))
    setStep(clamped)
    if (result || true) reload()
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Onboarding"
        description="Your progress is saved after every step, so you can leave and come back. The API stores the step number against your account."
      />

      <nav aria-label="Onboarding steps">
        <ol className="flex flex-wrap gap-2">
          {STEPS.map((label, index) => (
            <li key={label}>
              <button
                type="button"
                disabled={pending}
                onClick={() => goTo(index)}
                className={`rounded-md px-3 py-1.5 text-xs font-medium ${
                  index === step
                    ? 'bg-accent-600 text-white'
                    : 'border border-slate-300 bg-white text-slate-600 hover:bg-slate-50'
                }`}
              >
                {index + 1}. {label}
              </button>
            </li>
          ))}
        </ol>
      </nav>

      {onboarding.next_step_hint && (
        <InlineNotice tone={onboarding.completed ? 'success' : 'info'}>
          {onboarding.next_step_hint}
        </InlineNotice>
      )}

      {actionError && <ErrorState message={actionError} />}
      {notice && <InlineNotice tone="success">{notice}</InlineNotice>}

      {step === 0 && (
        <Card title="What onboarding collects" description="Each section writes to the real API; nothing is stored only in the browser.">
          <ul className="space-y-2 text-sm text-slate-700">
            <li className="rounded border border-slate-200 bg-slate-50 px-3 py-2">
              Income sources, normalised to a monthly equivalent so mixed frequencies compare correctly.
            </li>
            <li className="rounded border border-slate-200 bg-slate-50 px-3 py-2">
              Assets, with the liquid and usable-for-goals flags that decide what the planner may allocate.
            </li>
            <li className="rounded border border-slate-200 bg-slate-50 px-3 py-2">
              Liabilities, recorded as EMI obligations rather than as balance-sheet totals.
            </li>
            <li className="rounded border border-slate-200 bg-slate-50 px-3 py-2">
              Savings preferences and planning assumptions, which stay editable in settings afterwards.
            </li>
          </ul>
          <div className="mt-5">
            <Button pending={pending} onClick={() => goTo(1)}>
              Start with income
            </Button>
          </div>
        </Card>
      )}

      {step === 1 && (
        <Card
          title="Income sources"
          description="Amounts are entered at their own frequency and converted to a monthly equivalent by the backend."
        >
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Field label="Type">
              <SelectInput
                value={incomeDraft.source_type}
                onChange={(value) => setIncomeDraft({ ...incomeDraft, source_type: value })}
                options={INCOME_TYPES.map((value) => ({ value, label: value }))}
                disabled={pending}
              />
            </Field>
            <Field label="Label">
              <TextInput
                value={incomeDraft.label}
                onChange={(value) => setIncomeDraft({ ...incomeDraft, label: value })}
                disabled={pending}
              />
            </Field>
            <Field label="Amount">
              <TextInput
                type="number"
                value={incomeDraft.amount}
                onChange={(value) => setIncomeDraft({ ...incomeDraft, amount: value })}
                disabled={pending}
              />
            </Field>
            <Field label="Frequency">
              <SelectInput
                value={incomeDraft.frequency}
                onChange={(value) => setIncomeDraft({ ...incomeDraft, frequency: value })}
                options={FREQUENCIES.map((value) => ({ value, label: value }))}
                disabled={pending}
              />
            </Field>
            <Field label="Stability">
              <SelectInput
                value={incomeDraft.stability}
                onChange={(value) => setIncomeDraft({ ...incomeDraft, stability: value })}
                options={STABILITIES.map((value) => ({ value, label: value }))}
                disabled={pending}
              />
            </Field>
            <div className="flex items-end">
              <Checkbox
                label="Recurring income"
                hint="Recurring income is seeded as an expected line when a month is opened."
                checked={incomeDraft.is_recurring}
                disabled={pending}
                onChange={(value) => setIncomeDraft({ ...incomeDraft, is_recurring: value })}
              />
            </div>
          </div>

          <div className="mt-5">
            <div className="flex flex-wrap gap-2">
              <Button
                pending={pending}
                disabled={incomeDraft.amount === ''}
                onClick={async () => {
                  const payload = {
                    source_type: incomeDraft.source_type,
                    label: incomeDraft.label,
                    amount: Number(incomeDraft.amount),
                    frequency: incomeDraft.frequency as 'monthly',
                    stability: incomeDraft.stability,
                    is_recurring: incomeDraft.is_recurring,
                    expected_day: null,
                    is_active: true,
                  }
                  const saved = await run(
                    () =>
                      editingIncomeId === null
                        ? incomeApi.create(payload)
                        : incomeApi.update(editingIncomeId, payload),
                    editingIncomeId === null ? 'Income source added.' : 'Income source updated.',
                  )
                  if (saved) {
                    setIncomeDraft({ ...incomeDraft, label: '', amount: '' })
                    setEditingIncomeId(null)
                    reload()
                  }
                }}
              >
                {editingIncomeId === null ? 'Add income source' : 'Save changes'}
              </Button>
              {editingIncomeId !== null && (
                <Button
                  tone="secondary"
                  disabled={pending}
                  onClick={() => {
                    setEditingIncomeId(null)
                    setIncomeDraft({ ...incomeDraft, label: '', amount: '' })
                  }}
                >
                  Cancel edit
                </Button>
              )}
            </div>
          </div>

          <div className="mt-5">
            {income.length === 0 ? (
              <EmptyState
                title="No income sources yet"
                message="At least one income source is required before onboarding can be completed, because the surplus cannot be derived without it."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="gp-table">
                  <thead>
                    <tr>
                      <th>Type</th>
                      <th>Label</th>
                      <th className="gp-num">Amount</th>
                      <th>Frequency</th>
                      <th className="gp-num">Monthly equivalent</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {income.map((source) => (
                      <tr key={source.id}>
                        <td>{source.source_type}</td>
                        <td>{source.label || '--'}</td>
                        <td className="gp-num">{formatMoney(source.amount)}</td>
                        <td>{source.frequency}</td>
                        <td className="gp-num">{formatMoney(source.monthly_equivalent)}</td>
                        <td>
                          <div className="flex gap-2">
                            <Button
                              tone="secondary"
                              size="sm"
                              disabled={pending}
                              onClick={() => {
                                setEditingIncomeId(source.id)
                                setIncomeDraft({
                                  source_type: source.source_type,
                                  label: source.label ?? '',
                                  amount: String(source.amount),
                                  frequency: source.frequency,
                                  stability: source.stability,
                                  is_recurring: source.is_recurring,
                                })
                              }}
                            >
                              Edit
                            </Button>
                            <Button
                              tone="danger"
                              size="sm"
                              disabled={pending}
                              onClick={async () => {
                                const removed = await run(
                                  () => incomeApi.remove(source.id),
                                  'Income source removed.',
                                )
                                if (removed) {
                                  if (editingIncomeId === source.id) setEditingIncomeId(null)
                                  reload()
                                }
                              }}
                            >
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
          </div>
        </Card>
      )}

      {step === 2 && (
        <Card
          title="Savings and assets"
          description="The liquid and usable-for-goals flags decide what the planner may allocate. Emergency savings are normally excluded from the goal pool."
        >
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Field label="Type">
              <SelectInput
                value={assetDraft.asset_type}
                onChange={(value) => setAssetDraft({ ...assetDraft, asset_type: value })}
                options={ASSET_TYPES.map((value) => ({ value, label: value.replace(/_/g, ' ') }))}
                disabled={pending}
              />
            </Field>
            <Field label="Label">
              <TextInput
                value={assetDraft.label}
                onChange={(value) => setAssetDraft({ ...assetDraft, label: value })}
                disabled={pending}
              />
            </Field>
            <Field label="Current value">
              <TextInput
                type="number"
                value={assetDraft.current_value}
                onChange={(value) => setAssetDraft({ ...assetDraft, current_value: value })}
                disabled={pending}
              />
            </Field>
            <Field label="Annual return" hint="Decimal, e.g. 0.07.">
              <TextInput
                type="number"
                step={0.005}
                value={assetDraft.annual_return}
                onChange={(value) => setAssetDraft({ ...assetDraft, annual_return: value })}
                disabled={pending}
              />
            </Field>
            <Field label="Risk score" hint="Between 0 and 1.">
              <TextInput
                type="number"
                step={0.05}
                value={assetDraft.risk_score}
                onChange={(value) => setAssetDraft({ ...assetDraft, risk_score: value })}
                disabled={pending}
              />
            </Field>
            <div className="flex flex-col justify-end gap-2">
              <Checkbox
                label="Liquid"
                checked={assetDraft.is_liquid}
                disabled={pending}
                onChange={(value) => setAssetDraft({ ...assetDraft, is_liquid: value })}
              />
              <Checkbox
                label="Usable for goals"
                checked={assetDraft.usable_for_goals}
                disabled={pending}
                onChange={(value) => setAssetDraft({ ...assetDraft, usable_for_goals: value })}
              />
            </div>
          </div>

          <div className="mt-5">
            <Button
              pending={pending}
              disabled={assetDraft.current_value === ''}
              onClick={async () => {
                const payload: AssetInput = {
                  asset_type: assetDraft.asset_type as AssetInput['asset_type'],
                  label: assetDraft.label,
                  current_value: Number(assetDraft.current_value),
                  is_liquid: assetDraft.is_liquid,
                  usable_for_goals: assetDraft.usable_for_goals,
                  annual_return: Number(assetDraft.annual_return || 0),
                  risk_score: Number(assetDraft.risk_score || 0),
                  earmarked_goal_id: null,
                }
                const created = await run(() => assetsApi.create(payload), 'Asset added.')
                if (created) {
                  setAssetDraft({ ...assetDraft, label: '', current_value: '' })
                  reload()
                }
              }}
            >
              Add asset
            </Button>
          </div>

          <div className="mt-5">
            {assets.length === 0 ? (
              <EmptyState
                title="No assets recorded"
                message="Adding your liquid savings lets the planner use existing funding. Without it, each goal starts from a gap equal to its full future cost."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="gp-table">
                  <thead>
                    <tr>
                      <th>Type</th>
                      <th>Label</th>
                      <th className="gp-num">Value</th>
                      <th>Usable for goals</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {assets.map((asset) => (
                      <tr key={asset.id}>
                        <td>{asset.asset_type.replace(/_/g, ' ')}</td>
                        <td>{asset.label || '--'}</td>
                        <td className="gp-num">{formatMoney(asset.current_value)}</td>
                        <td>
                          <Badge tone={asset.usable_for_goals ? 'positive' : 'neutral'}>
                            {asset.usable_for_goals ? 'yes' : 'no'}
                          </Badge>
                        </td>
                        <td>
                          <Button
                            tone="danger"
                            size="sm"
                            disabled={pending}
                            onClick={async () => {
                              const removed = await run(() => assetsApi.remove(asset.id), 'Asset removed.')
                              if (removed) reload()
                            }}
                          >
                            Delete
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Card>
      )}

      {step === 3 && (
        <Card
          title="Liabilities"
          description="The EMI is the monthly obligation. The outstanding principal is a balance-sheet figure and is never added to it."
        >
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Field label="Type">
              <SelectInput
                value={liabilityDraft.liability_type}
                onChange={(value) => setLiabilityDraft({ ...liabilityDraft, liability_type: value })}
                options={LIABILITY_TYPES.map((value) => ({ value, label: value.replace(/_/g, ' ') }))}
                disabled={pending}
              />
            </Field>
            <Field label="Label">
              <TextInput
                value={liabilityDraft.label}
                onChange={(value) => setLiabilityDraft({ ...liabilityDraft, label: value })}
                disabled={pending}
              />
            </Field>
            <Field label="Outstanding principal">
              <TextInput
                type="number"
                value={liabilityDraft.outstanding_principal}
                onChange={(value) => setLiabilityDraft({ ...liabilityDraft, outstanding_principal: value })}
                disabled={pending}
              />
            </Field>
            <Field label="Annual interest rate" hint="Decimal, e.g. 0.09.">
              <TextInput
                type="number"
                step={0.005}
                value={liabilityDraft.annual_interest_rate}
                onChange={(value) => setLiabilityDraft({ ...liabilityDraft, annual_interest_rate: value })}
                disabled={pending}
              />
            </Field>
            <Field label="EMI amount" hint="Required for an outstanding balance with a remaining tenure.">
              <TextInput
                type="number"
                value={liabilityDraft.emi_amount}
                onChange={(value) => setLiabilityDraft({ ...liabilityDraft, emi_amount: value })}
                disabled={pending}
              />
            </Field>
            <Field label="Remaining tenure (months)">
              <TextInput
                type="number"
                value={liabilityDraft.remaining_tenure_months}
                onChange={(value) =>
                  setLiabilityDraft({ ...liabilityDraft, remaining_tenure_months: value })
                }
                disabled={pending}
              />
            </Field>
          </div>

          <div className="mt-5">
            <Button
              pending={pending}
              disabled={liabilityDraft.outstanding_principal === ''}
              onClick={async () => {
                const payload: LiabilityInput = {
                  liability_type: liabilityDraft.liability_type as LiabilityInput['liability_type'],
                  label: liabilityDraft.label,
                  outstanding_principal: Number(liabilityDraft.outstanding_principal),
                  annual_interest_rate: Number(liabilityDraft.annual_interest_rate || 0),
                  emi_amount: Number(liabilityDraft.emi_amount || 0),
                  remaining_tenure_months: Number(liabilityDraft.remaining_tenure_months || 0),
                }
                const created = await run(() => liabilitiesApi.create(payload), 'Liability added.')
                if (created) {
                  setLiabilityDraft({ ...liabilityDraft, label: '', outstanding_principal: '', emi_amount: '' })
                  reload()
                }
              }}
            >
              Add liability
            </Button>
          </div>

          <div className="mt-5">
            {liabilities.length === 0 ? (
              <EmptyState
                title="No liabilities recorded"
                message="If you have no loans or card balances, continue to the next step. Otherwise record the EMI, because that is the cash-flow obligation."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="gp-table">
                  <thead>
                    <tr>
                      <th>Type</th>
                      <th>Label</th>
                      <th className="gp-num">Principal</th>
                      <th className="gp-num">EMI</th>
                      <th className="gp-num">Total interest if held</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {liabilities.map((liability) => (
                      <tr key={liability.id}>
                        <td>{liability.liability_type.replace(/_/g, ' ')}</td>
                        <td>{liability.label || '--'}</td>
                        <td className="gp-num">{formatMoney(liability.outstanding_principal)}</td>
                        <td className="gp-num">{formatMoney(liability.emi_amount)}</td>
                        <td className="gp-num">{formatMoney(liability.total_interest_if_held_to_tenure)}</td>
                        <td>
                          <Button
                            tone="danger"
                            size="sm"
                            disabled={pending}
                            onClick={async () => {
                              const removed = await run(
                                () => liabilitiesApi.remove(liability.id),
                                'Liability removed.',
                              )
                              if (removed) reload()
                            }}
                          >
                            Delete
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Card>
      )}

      {step === 4 && (
        <Card
          title="Savings preferences"
          description="These values are saved as your financial profile, which the planner reads on every run."
        >
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Field
              label="Monthly income"
              hint={
                monthlyIncomeFromSources > 0
                  ? 'Derived from your income sources; the planner always uses those.'
                  : 'No active income source yet. Add one on the Income step; it is required before a plan can be produced.'
              }
            >
              <TextInput
                value={formatMoney(monthlyIncomeFromSources)}
                disabled
                onChange={() => undefined}
              />
            </Field>
            <Field label="Essential expenses (monthly)">
              <TextInput
                type="number"
                value={String(profileDraft.essential_expenses)}
                onChange={(value) =>
                  setProfileDraft({ ...profileDraft, essential_expenses: Number(value || 0) })
                }
                disabled={pending}
              />
            </Field>
            <Field label="Discretionary expenses (monthly)">
              <TextInput
                type="number"
                value={String(profileDraft.discretionary_expenses)}
                onChange={(value) =>
                  setProfileDraft({ ...profileDraft, discretionary_expenses: Number(value || 0) })
                }
                disabled={pending}
              />
            </Field>
            <Field label="Savings target (monthly)">
              <TextInput
                type="number"
                value={String(profileDraft.monthly_savings_target)}
                onChange={(value) =>
                  setProfileDraft({ ...profileDraft, monthly_savings_target: Number(value || 0) })
                }
                disabled={pending}
              />
            </Field>
            <Field label="Preferred cash buffer">
              <TextInput
                type="number"
                value={String(profileDraft.preferred_cash_buffer)}
                onChange={(value) =>
                  setProfileDraft({ ...profileDraft, preferred_cash_buffer: Number(value || 0) })
                }
                disabled={pending}
              />
            </Field>
            <Field label="Emergency fund months">
              <TextInput
                type="number"
                value={String(profileDraft.emergency_months)}
                onChange={(value) => setProfileDraft({ ...profileDraft, emergency_months: Number(value || 0) })}
                disabled={pending}
              />
            </Field>
            <Field label="Currency">
              <TextInput
                value={prefsDraft.currency}
                onChange={(value) => setPrefsDraft({ ...prefsDraft, currency: value })}
                disabled={pending}
              />
            </Field>
            <Field label="Locale">
              <TextInput
                value={prefsDraft.locale}
                onChange={(value) => setPrefsDraft({ ...prefsDraft, locale: value })}
                disabled={pending}
              />
            </Field>
            <Field label="Liquidity requirement">
              <SelectInput
                value={prefsDraft.liquidity_requirement}
                onChange={(value) =>
                  setPrefsDraft({
                    ...prefsDraft,
                    liquidity_requirement: value as PreferencesInput['liquidity_requirement'],
                  })
                }
                options={['low', 'medium', 'high'].map((value) => ({ value, label: value }))}
                disabled={pending}
              />
            </Field>
          </div>

          <div className="mt-4 flex flex-wrap gap-5">
            <Checkbox
              label="The savings target is mandatory"
              checked={profileDraft.savings_target_is_mandatory}
              disabled={pending}
              onChange={(value) => setProfileDraft({ ...profileDraft, savings_target_is_mandatory: value })}
            />
            <Checkbox
              label="I am willing to adjust discretionary spending"
              checked={profileDraft.willing_to_adjust_discretionary}
              disabled={pending}
              onChange={(value) =>
                setProfileDraft({ ...profileDraft, willing_to_adjust_discretionary: value })
              }
            />
          </div>

          <div className="mt-5">
            <Button
              pending={pending}
              onClick={async () => {
                const saved = await run(
                   () => Promise.all([profileApi.update(profilePayload), preferencesApi.update(prefsDraft)]),
                   'Savings preferences saved.',
                )
                if (saved) reload()
              }}
            >
              Save savings preferences
            </Button>
          </div>
        </Card>
      )}

      {step === 5 && (
        <Card
          title="Risk and planning preferences"
          description="Risk tolerance and loss ability are recorded separately. Neither is inferred from the other, and risk capacity is a separate numeric input the planner uses."
        >
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Field label="Risk tolerance" hint="What you are willing to accept.">
              <SelectInput
                value={prefsDraft.risk_tolerance}
                onChange={(value) =>
                  setPrefsDraft({ ...prefsDraft, risk_tolerance: value as PreferencesInput['risk_tolerance'] })
                }
                options={['low', 'moderate', 'high'].map((value) => ({ value, label: value }))}
                disabled={pending}
              />
            </Field>
            <Field label="Loss ability" hint="What your finances can absorb.">
              <SelectInput
                value={prefsDraft.loss_ability}
                onChange={(value) =>
                  setPrefsDraft({ ...prefsDraft, loss_ability: value as PreferencesInput['loss_ability'] })
                }
                options={['low', 'moderate', 'high'].map((value) => ({ value, label: value }))}
                disabled={pending}
              />
            </Field>
            <Field label="Risk capacity" hint="Between 0 and 1.">
              <TextInput
                type="number"
                step={0.05}
                value={String(profileDraft.risk_capacity)}
                onChange={(value) => setProfileDraft({ ...profileDraft, risk_capacity: Number(value || 0) })}
                disabled={pending}
              />
            </Field>
            <Field label="EMI to income cap" hint="Decimal, e.g. 0.35.">
              <TextInput
                type="number"
                step={0.01}
                value={String(profileDraft.emi_income_ratio_cap)}
                onChange={(value) =>
                  setProfileDraft({ ...profileDraft, emi_income_ratio_cap: Number(value || 0) })
                }
                disabled={pending}
              />
            </Field>
            <Field label="Inflation assumption" hint="Decimal, e.g. 0.03.">
              <TextInput
                type="number"
                step={0.005}
                value={String(profileDraft.inflation_assumption)}
                onChange={(value) =>
                  setProfileDraft({ ...profileDraft, inflation_assumption: Number(value || 0) })
                }
                disabled={pending}
              />
            </Field>
            <Field label="Investment return assumption">
              <TextInput
                type="number"
                step={0.005}
                value={String(profileDraft.investment_return_assumption)}
                onChange={(value) =>
                  setProfileDraft({ ...profileDraft, investment_return_assumption: Number(value || 0) })
                }
                disabled={pending}
              />
            </Field>
            <Field label="Savings return assumption">
              <TextInput
                type="number"
                step={0.005}
                value={String(profileDraft.savings_return_assumption)}
                onChange={(value) =>
                  setProfileDraft({ ...profileDraft, savings_return_assumption: Number(value || 0) })
                }
                disabled={pending}
              />
            </Field>
            <Field label="Loan interest assumption">
              <TextInput
                type="number"
                step={0.005}
                value={String(profileDraft.loan_interest_assumption)}
                onChange={(value) =>
                  setProfileDraft({ ...profileDraft, loan_interest_assumption: Number(value || 0) })
                }
                disabled={pending}
              />
            </Field>
          </div>

          <div className="mt-4">
            <InlineNotice tone="info">
              Risk tolerance is what you say you can accept. Loss ability is what your finances can
              absorb. They are stored as separate fields on purpose and are never substituted for one
              another.
            </InlineNotice>
          </div>

          <div className="mt-5">
            <Button
              pending={pending}
              onClick={async () => {
                const saved = await run(
                   () => Promise.all([profileApi.update(profilePayload), preferencesApi.update(prefsDraft)]),
                   'Risk and planning preferences saved.',
                )
                if (saved) reload()
              }}
            >
              Save risk and planning preferences
            </Button>
          </div>
        </Card>
      )}

      {step === 6 && (
        <div className="space-y-6">
          <Card title="Profile summary" description="Derived by the backend from what you have recorded so far.">
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <div className="gp-card p-3">
                <p className="text-xs uppercase tracking-wide text-slate-500">Income sources</p>
                <p className="mt-1 font-mono text-lg">{onboarding.income_count}</p>
              </div>
              <div className="gp-card p-3">
                <p className="text-xs uppercase tracking-wide text-slate-500">Assets</p>
                <p className="mt-1 font-mono text-lg">{onboarding.asset_count}</p>
              </div>
              <div className="gp-card p-3">
                <p className="text-xs uppercase tracking-wide text-slate-500">Liabilities</p>
                <p className="mt-1 font-mono text-lg">{onboarding.liability_count}</p>
              </div>
              <div className="gp-card p-3">
                <p className="text-xs uppercase tracking-wide text-slate-500">Goals</p>
                <p className="mt-1 font-mono text-lg">{onboarding.goal_count}</p>
              </div>
            </div>

            <div className="mt-5">
              {summary ? (
                <KeyValueTable
                  rows={[
                    { key: 'Monthly income', value: formatMoney(summary.monthly_income) },
                    { key: 'Essential expenses', value: formatMoney(summary.essential_expenses) },
                    { key: 'Discretionary expenses', value: formatMoney(summary.discretionary_expenses) },
                    { key: 'Existing EMI', value: formatMoney(summary.existing_emi) },
                    { key: 'Monthly surplus', value: formatMoney(summary.monthly_surplus) },
                    { key: 'Emergency fund target', value: formatMoney(summary.emergency_fund_target) },
                    { key: 'Emergency fund progress', value: formatPct(summary.emergency_fund_progress) },
                    { key: 'Available cash for goals', value: formatMoney(summary.available_cash_for_goals) },
                    { key: 'Situation tier', value: summary.situation_tier },
                  ]}
                />
              ) : (
                <EmptyState
                  title="Summary not available yet"
                  message="A saved financial profile and at least one income source are required before the summary can be derived."
                />
              )}
            </div>
          </Card>

          <Card
            title="Finish onboarding"
            description="Completing onboarding marks the account as set up. A goal is still required before a plan can be generated."
          >
            <div className="flex flex-wrap gap-3">
              <Button
                pending={pending}
                onClick={async () => {
                  const result = await run(() => onboardingApi.complete(), undefined)
                  if (result) {
                    setNotice(result.message)
                    reload()
                  }
                }}
              >
                Complete onboarding
              </Button>
              <Button tone="secondary" disabled={pending} onClick={() => navigate('/goals')}>
                Create a goal
              </Button>
              <Button tone="secondary" disabled={pending} onClick={() => navigate('/dashboard')}>
                Go to dashboard
              </Button>
            </div>
            {onboarding.completed && (
              <div className="mt-4">
                <InlineNotice tone="success">Onboarding is marked complete for this account.</InlineNotice>
              </div>
            )}
          </Card>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-4">
        <Button tone="secondary" disabled={pending || step === 0} onClick={() => goTo(step - 1)}>
          Back
        </Button>
        <p className="text-xs text-slate-500">
          Step {step + 1} of {STEPS.length}. Progress is saved to your account after each step.
        </p>
        <Button disabled={pending || step === STEPS.length - 1} onClick={() => goTo(step + 1)}>
          Next
        </Button>
      </div>
    </div>
  )
}
