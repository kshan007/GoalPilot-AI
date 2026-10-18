import { useCallback, useEffect, useState } from 'react'
import { errorMessage } from '../api/client'
import {
  recommendationsApi,
  type AskResponse,
  type Recommendation,
  type RecommendationStatus,
} from '../api/market'

const inr = (value?: number | null) =>
  value === null || value === undefined
    ? '—'
    : `₹${new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(value)}`

const pct = (value?: number | null, digits = 0) =>
  value === null || value === undefined ? '—' : `${(value * 100).toFixed(digits)}%`

const num = (value: unknown): number | null =>
  typeof value === 'number' && Number.isFinite(value) ? value : null

function StatusBanner({ status }: { status: RecommendationStatus | null }) {
  if (!status) return null
  const live = status.llm.available
  return (
    <div
      className={`rounded-lg border p-4 text-sm ${
        live
          ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
          : 'border-amber-200 bg-amber-50 text-amber-900'
      }`}
    >
      <p className="font-medium">
        {live
          ? `Explanation layer: ${status.llm.provider} / ${status.llm.model}`
          : 'Explanation layer: deterministic fallback'}
      </p>
      <p className="mt-1">{status.fallback_note}</p>
      {!live && (
        <p className="mt-1 text-xs">
          {status.llm.configured
            ? 'A key is present but the SDK or service is unavailable.'
            : `Set ${status.llm.key_env_var} in the backend environment to enable model-written prose.`}
        </p>
      )}
    </div>
  )
}

function GoalTable({ recommendation }: { recommendation: Recommendation }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[760px] text-left text-sm">
        <thead className="text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="pb-2">Goal</th>
            <th className="pb-2">Target</th>
            <th className="pb-2">Needed / month</th>
            <th className="pb-2">Planned / month</th>
            <th className="pb-2">Shortfall</th>
            <th className="pb-2">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {recommendation.goal_recommendations.map((goal) => {
            const planned =
              goal.planned_savings_contribution + goal.planned_investment_contribution
            const tone =
              goal.funding_status === 'fully_funded'
                ? 'text-emerald-700'
                : goal.funding_status === 'underfunded'
                  ? 'text-red-700'
                  : 'text-slate-600'
            return (
              <tr key={goal.goal_ref} className="align-top">
                <td className="py-3 pr-3">
                  <p className="font-medium text-slate-900">{goal.name}</p>
                  <p className="text-xs text-slate-500">
                    priority {goal.priority} · by {goal.target_date}
                  </p>
                  <p className="mt-1 max-w-md text-xs text-slate-600">{goal.reason}</p>
                </td>
                <td className="py-3 pr-3">{inr(goal.target_amount_future)}</td>
                <td className="py-3 pr-3">{inr(goal.recommended_monthly_contribution)}</td>
                <td className="py-3 pr-3 font-medium">{inr(planned)}</td>
                <td className="py-3 pr-3">{inr(goal.expected_shortfall)}</td>
                <td className={`py-3 font-medium ${tone}`}>
                  {goal.funding_status.replace(/_/g, ' ')}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default function Recommendations() {
  const [status, setStatus] = useState<RecommendationStatus | null>(null)
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<AskResponse | null>(null)
  const [asking, setAsking] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [statusBody, latest] = await Promise.all([
        recommendationsApi.status(),
        recommendationsApi.latest().catch(() => null),
      ])
      setStatus(statusBody)
      setRecommendation(latest)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function generate() {
    setGenerating(true)
    setError(null)
    try {
      setRecommendation(await recommendationsApi.generate({ include_investments: true, include_loans: true }))
      setAnswer(null)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setGenerating(false)
    }
  }

  async function ask() {
    if (question.trim().length < 3) return
    setAsking(true)
    try {
      setAnswer(await recommendationsApi.ask(question.trim()))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setAsking(false)
    }
  }

  const llmLabel = recommendation
    ? recommendation.llm.used
      ? `${recommendation.llm.provider} / ${recommendation.llm.model}`
      : `deterministic fallback (${recommendation.llm.reason ?? recommendation.llm.status})`
    : ''

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Your plan, explained</h1>
          <p className="mt-1 max-w-3xl text-sm text-slate-600">
            Every figure on this page comes from the calculation services. The explanation layer
            only writes prose about those figures and cannot change them.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void generate()}
          disabled={generating}
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
        >
          {generating ? 'Generating…' : recommendation ? 'Regenerate' : 'Generate recommendation'}
        </button>
      </header>

      <StatusBanner status={status} />
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {error}
        </div>
      )}

      {loading && <p className="text-sm text-slate-600">Loading…</p>}

      {!loading && !recommendation && (
        <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600">
          No recommendation yet. Add a financial profile and at least one goal, then generate one.
        </div>
      )}

      {recommendation && (
        <>
          <section className="rounded-xl border border-slate-200 bg-white p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-lg font-semibold text-slate-900">Summary</h2>
              <p className="text-xs text-slate-500">
                {recommendation.schema_version} · run {recommendation.run_id ?? '—'} ·{' '}
                {llmLabel}
              </p>
            </div>
            <p className="mt-3 text-sm leading-relaxed text-slate-800">
              {recommendation.financial_summary}
            </p>
            <p className="mt-2 text-sm leading-relaxed text-slate-700">
              {recommendation.explanation}
            </p>
          </section>

          <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[
              ['Monthly surplus', inr(recommendation.cash_flow_status.monthly_surplus)],
              ['Protected buffer', inr(recommendation.protected_buffer.protected_monthly_buffer)],
              ['Goal budget', inr(recommendation.available_goal_budget)],
              ['Planned contributions', inr(recommendation.recommended_plan.monthly_contributions_total)],
            ].map(([label, value]) => (
              <div key={label} className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
                <p className="mt-1 text-lg font-semibold text-slate-900">{value}</p>
              </div>
            ))}
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-5">
            <h2 className="text-sm font-semibold text-slate-900">Savings buffer</h2>
            <p className="mt-2 text-sm text-slate-700">
              {recommendation.protected_buffer.explanation}
            </p>
            <dl className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              {[
                ['Desired', inr(recommendation.protected_buffer.desired_monthly_buffer)],
                ['Protected', inr(recommendation.protected_buffer.protected_monthly_buffer)],
                ['Deficit', inr(recommendation.protected_buffer.buffer_deficit)],
                ['Emergency fund', pct(recommendation.cash_flow_status.emergency_fund_progress)],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="text-slate-500">{label}</dt>
                  <dd className="font-medium text-slate-900">{value}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-2 text-xs text-slate-500">
              {recommendation.protected_buffer.minimum_cash_reserve_rule}
            </p>
            <p className="mt-2 text-xs text-slate-500">
              Surplus basis: {recommendation.cash_flow_status.surplus_basis}
            </p>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-5">
            <h2 className="text-lg font-semibold text-slate-900">Goals</h2>
            <div className="mt-3">
              <GoalTable recommendation={recommendation} />
            </div>
          </section>

          {(recommendation.investment_options.length > 0 ||
            Object.keys(recommendation.investment_terms ?? {}).length > 0) && (
            <section className="rounded-xl border border-slate-200 bg-white p-5">
              <h2 className="text-lg font-semibold text-slate-900">Ways to invest</h2>
              {(() => {
                const terms = recommendation.investment_terms ?? {}
                const monthly = num(terms.monthly_amount)
                const months = num(terms.horizon_months)
                const rate = num(terms.assumed_annual_return)
                const projected = num(terms.projected_value)
                return (
                  <div className="mt-3 space-y-3">
                    {monthly !== null && months !== null && rate !== null && projected !== null && (
                      <p className="text-sm text-slate-800">
                        <span className="font-medium">
                          {inr(monthly)} a month for {months} month{months === 1 ? '' : 's'}
                        </span>{' '}
                        at an assumed {pct(rate, 1)} a year → about{' '}
                        <span className="font-medium">{inr(projected)}</span>.{' '}
                        <span className="text-xs text-slate-500">{String(terms.basis ?? '')}</span>
                      </p>
                    )}
                    {monthly === 0 && (
                      <p className="text-sm text-slate-600">
                        Your plan puts ₹0 a month into investments, so the products below are
                        informational only — nothing is being bought.
                      </p>
                    )}
                    <ul className="space-y-3 text-sm">
                      {recommendation.investment_options.slice(0, 5).map((option, index) => {
                        const rateValue = num(option.published_rate)
                        const lockIn = num(option.lock_in_months)
                        const minimum = num(option.min_investment)
                        return (
                          <li key={String(option.product_id ?? index)}>
                            <p className="font-medium text-slate-900">
                              {String(option.name ?? 'Investment option')}{' '}
                              <span className="text-xs font-normal text-slate-500">
                                ({String(option.category ?? '—')} · {String(option.provider ?? '—')})
                              </span>
                            </p>
                            <p className="text-xs text-slate-600">
                              {rateValue !== null
                                ? `Published rate ${pct(rateValue, 2)} a year`
                                : 'No published rate'}
                              {lockIn !== null && lockIn > 0
                                ? ` · locked in for ${lockIn} month${lockIn === 1 ? '' : 's'}`
                                : ' · no lock-in stated'}
                              {minimum !== null ? ` · minimum ${inr(minimum)}` : ''}
                            </p>
                            {option.commentary ? (
                              <p className="mt-1 text-slate-700">{String(option.commentary)}</p>
                            ) : null}
                          </li>
                        )
                      })}
                    </ul>
                  </div>
                )
              })()}
            </section>
          )}

          {(recommendation.loan_options.length > 0 ||
            Object.keys(recommendation.loan_terms ?? {}).length > 0) && (
            <section className="rounded-xl border border-slate-200 bg-white p-5">
              <h2 className="text-lg font-semibold text-slate-900">Borrowing</h2>
              {(() => {
                const terms = recommendation.loan_terms ?? {}
                const principal = num(terms.principal)
                const tenure = num(terms.tenure_months)
                const rate = num(terms.annual_rate)
                const emi = num(terms.monthly_emi)
                const interest = num(terms.total_interest)
                return (
                  <div className="mt-3 space-y-3">
                    {principal !== null && principal > 0 && tenure !== null && rate !== null && (
                      <p className="text-sm text-slate-800">
                        <span className="font-medium">
                          {inr(principal)} over {tenure} month{tenure === 1 ? '' : 's'} at{' '}
                          {pct(rate, 2)} a year
                        </span>
                        {emi !== null ? ` → EMI ${inr(emi)}` : ''}
                        {interest !== null ? `; total interest ${inr(interest)}` : ''}.{' '}
                        <span className="text-xs text-slate-500">{String(terms.basis ?? '')}</span>
                      </p>
                    )}
                    <ul className="space-y-3 text-sm">
                      {recommendation.loan_options.slice(0, 5).map((option, index) => {
                        const optionPrincipal = num(option.principal)
                        const optionTenure = num(option.tenure_months)
                        const optionRate = num(option.published_rate)
                        const optionEmi = num(option.indicative_emi)
                        const optionInterest = num(option.total_interest)
                        return (
                          <li key={String(option.product_id ?? index)}>
                            <p className="font-medium text-slate-900">
                              {String(option.lender ?? 'Lender')} —{' '}
                              {String(option.product_name ?? 'loan product')}
                            </p>
                            <p className="text-xs text-slate-600">
                              {optionPrincipal !== null && optionTenure !== null
                                ? `${inr(optionPrincipal)} over ${optionTenure} month${optionTenure === 1 ? '' : 's'}`
                                : 'Amount and term not stated'}
                              {optionRate !== null
                                ? ` at ${pct(optionRate, 2)} a year`
                                : ' at an unpublished rate'}
                              {optionEmi !== null ? ` → EMI ${inr(optionEmi)}` : ''}
                              {optionInterest !== null
                                ? `; total interest ${inr(optionInterest)}`
                                : ''}
                            </p>
                            {option.affordability_verdict ? (
                              <p className="text-xs text-slate-500">
                                Affordability: {String(option.affordability_verdict)}
                              </p>
                            ) : null}
                          </li>
                        )
                      })}
                    </ul>
                  </div>
                )
              })()}
            </section>
          )}

          <section className="rounded-xl border border-slate-200 bg-white p-5">
            <h2 className="text-sm font-semibold text-slate-900">Do this month</h2>
            <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-slate-700">
              {recommendation.monthly_actions.map((action) => (
                <li key={action}>{action}</li>
              ))}
            </ol>
          </section>

          {recommendation.risks_and_warnings.length > 0 && (
            <section className="rounded-xl border border-amber-200 bg-amber-50 p-5">
              <h2 className="text-sm font-semibold text-amber-900">Risks and warnings</h2>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-amber-900">
                {recommendation.risks_and_warnings.map((risk) => (
                  <li key={risk}>{risk}</li>
                ))}
              </ul>
            </section>
          )}

          {recommendation.alternative_scenarios.length > 0 && (
            <section className="rounded-xl border border-slate-200 bg-white p-5">
              <h2 className="text-sm font-semibold text-slate-900">Alternatives</h2>
              <ul className="mt-2 space-y-2 text-sm text-slate-700">
                {recommendation.alternative_scenarios.map((scenario) => (
                  <li key={scenario.scenario}>
                    <span className="font-medium">{scenario.scenario}</span> — {scenario.description}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="rounded-xl border border-slate-200 bg-white p-5">
            <h2 className="text-sm font-semibold text-slate-900">Ask about this plan</h2>
            <div className="mt-2 flex flex-wrap gap-2">
              <input
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="e.g. What is my buffer?"
                className="min-w-[260px] flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
              <button
                type="button"
                onClick={() => void ask()}
                disabled={asking}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-60"
              >
                {asking ? 'Asking…' : 'Ask'}
              </button>
            </div>
            {answer && (
              <div className="mt-3 rounded-lg bg-slate-50 p-4 text-sm text-slate-800">
                <p>{answer.answer}</p>
                <p className="mt-2 text-xs text-slate-500">
                  Answered from the stored plan only ·{' '}
                  {answer.llm && (answer.llm as { used?: boolean }).used
                    ? 'model-written'
                    : 'deterministic'}
                </p>
              </div>
            )}
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-5 text-sm">
            <h2 className="text-sm font-semibold text-slate-900">Sources, assumptions, gaps</h2>
            <ul className="mt-2 space-y-1 text-slate-700">
              {recommendation.data_sources.map((source) => (
                <li key={`${source.provider}-${source.name}`}>
                  <span className="font-medium">{source.provider}</span> — {source.name}{' '}
                  <span className="text-xs text-slate-500">({source.data_quality})</span>
                </li>
              ))}
            </ul>
            {recommendation.missing_information.length > 0 && (
              <>
                <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Missing information
                </h3>
                <ul className="mt-1 list-disc space-y-1 pl-5 text-slate-700">
                  {recommendation.missing_information.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </>
            )}
            {(recommendation.technical_notes ?? []).length > 0 && (
              <>
                <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Technical notes
                </h3>
                <ul className="mt-1 list-disc space-y-1 pl-5 text-slate-600">
                  {(recommendation.technical_notes ?? []).map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              </>
            )}
          </section>

          <p className="text-xs text-slate-500">{recommendation.disclaimer}</p>
        </>
      )}
    </div>
  )
}
