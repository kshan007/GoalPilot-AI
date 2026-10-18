/**
 * Types and calls for the external-product and recommendation surfaces.
 *
 * Kept separate from `types.ts` and `client.ts` so the financial core types stay untouched by
 * provider churn. Every field marked optional is optional because the *source* may not publish
 * it — the UI must render "not published", never a guess.
 */
import { request } from './client'

/* ------------------------------------------------------------------ provenance */

export type DataQuality =
  | 'official_live'
  | 'official_snapshot'
  | 'historical'
  | 'unofficial_mirror'
  | 'category_scenario'

export type RateClass =
  | 'historical_benchmark'
  | 'published_lender_rate'
  | 'estimated_scenario'
  | 'personalised_offer'

export interface ProviderStatus {
  provider: string
  kind: string
  status: string
  count?: number
  data_quality?: string | null
  data_quality_label?: string | null
  source_url?: string
  retrieved_at?: string | null
  reason?: string | null
  runtime_ms?: number
  metadata?: Record<string, unknown>
}

export interface HistoricalReturn {
  window: string
  cagr: number
  period_start: string
  period_end: string
  days: number
  basis: string
  source: string
}

/* ----------------------------------------------------------------- investments */

export interface Suitability {
  score: number
  risk_score_used: number
  eligibility_status: 'established' | 'not_established'
  reasons: string[]
  cautions: string[]
}

export interface InvestmentOption {
  product_id: string
  name: string
  category: string
  sub_category?: string
  issuer?: string | null
  provider: string
  data_quality: DataQuality
  data_quality_label?: string
  source_url: string
  retrieved_at?: string | null
  effective_date?: string | null
  nav?: number | null
  published_rate?: number | null
  rate_basis?: string | null
  min_investment?: number | null
  lock_in_months?: number | null
  liquidity: string
  risk_level: string
  risk_score?: number | null
  historical_returns: HistoricalReturn[]
  suitability: Suitability
  rank: number
  completeness: number
  freshness: 'fresh' | 'stale' | 'unknown'
  notes: string[]
}

export interface MarketHistory {
  available: boolean
  reason?: string
  observations?: number
  period_start?: string
  period_end?: string
  last_close?: number
  annualised_volatility?: number
  max_drawdown?: number
  trailing?: Record<string, { cagr: number | null; period_start: string; period_end: string }>
  caveat?: string
}

export interface InvestmentDiscovery {
  generated_at: string
  user_context: {
    risk_capacity: number
    liquidity_requirement: string
    horizon_months: number
    monthly_contribution_capacity: number
    emergency_fund_progress: number
    existing_bucket_shares: Record<string, number>
  }
  providers: ProviderStatus[]
  market_context: { historical: MarketHistory; live: ProviderStatus[] }
  options: InvestmentOption[]
  option_count: number
  options_matched: number
  category_scenarios_used: boolean
  tie_note: string
  history_enrichment: Record<string, unknown>
  missing_information: string[]
  selection_rule: string
  disclosure: string
  not_advice: boolean
  cash_flow_available?: boolean
}

/* ----------------------------------------------------------------------- loans */

export interface LoanIndicative {
  assumed_principal: number
  assumed_tenure_months: number
  monthly_emi: number
  total_repayment: number
  total_interest: number
  apr_including_known_fees: number | null
  basis: string
}

export interface Affordability {
  proposed_emi: number
  available_goal_budget: number
  goal_budget_after_emi: number
  emi_headroom_under_income_ceiling: number
  emi_share_of_income: number | null
  checks: Record<string, boolean>
  blocking_checks: string[]
  cautions: string[]
  verdict: 'affordable' | 'affordable_with_caution' | 'not_affordable'
  notes: string[]
}

export interface LoanOption {
  product_id: string
  lender: string
  product_name: string
  category: string
  published_rate: number | null
  scenario_rate?: number | null
  rate_type: string
  rate_basis: string
  rate_class: RateClass
  rate_class_label?: string
  configurable?: boolean
  assumption_source?: string
  data_quality: DataQuality
  source_url: string
  retrieved_at?: string | null
  effective_date?: string | null
  is_personalised_offer: boolean
  quoted_text?: string | null
  indicative: LoanIndicative | null
  affordability: Affordability
  suitability_notes: string[]
  eligibility: string[]
}

export interface LoanBenchmark {
  benchmark: string
  rate: number
  period: string
  observations: number
  series_start: string
  rate_class: RateClass
  rate_basis: string
  is_product_rate: boolean
  is_offer: boolean
}

export interface LoanDiscovery {
  generated_at: string
  assumed_principal: number
  assumed_tenure_months: number
  providers: ProviderStatus[]
  options: LoanOption[]
  option_count: number
  scenarios: LoanOption[]
  scenario_count: number
  category_coverage: {
    requested_categories: string[]
    covered_by_published_products: string[]
    scenario_only: string[]
    unavailable: string[]
    note: string
  }
  benchmarks: LoanBenchmark[]
  rate_classes: Record<RateClass, string>
  affordability_context: Record<string, number>
  missing_information: string[]
  disclosure: string
  not_advice: boolean
  does_not_originate_loans: boolean
}

export interface QuoteInput {
  label?: string
  lender?: string | null
  principal: number
  annual_rate: number
  tenure_months: number
  rate_type?: 'fixed' | 'floating' | 'hybrid' | 'unknown'
  processing_fee_pct?: number | null
  processing_fee_flat?: number
  other_fees?: number
  goal_gap?: number | null
  months_remaining?: number | null
  include_schedule?: boolean
  offer_is_personal?: boolean
}

export interface QuoteAnalysis {
  generated_at: string
  input: Record<string, unknown>
  repayment: {
    monthly_emi: number
    total_repayment: number
    total_interest: number
    total_fees: number
    total_cost_of_credit: number
    nominal_annual_rate: number
    apr_including_fees: number | null
    apr_note: string
  }
  affordability: Affordability
  rate_sensitivity: {
    base_rate: number
    rows: Array<{ rate: number; rate_bump_bp: number; emi: number; emi_increase: number; total_interest: number }>
    note: string
  }
  alternatives: Array<{
    option: string
    description: string
    months_needed?: number
    extra_months?: number
    interest_cost_avoided?: number
    affordable: boolean | null
  }>
  rate_class: RateClass
  rate_class_label: string
  offer_source: string | null
  proceeds_are_not_income: boolean
  disclosure: string
  schedule?: Array<{ month: number; payment: number; interest: number; principal: number; balance: number }>
}

/* ------------------------------------------------------------- recommendations */

export interface RecommendationGoal {
  goal_ref: string
  goal_id: number | null
  name: string
  priority: number
  target_date: string
  target_amount_future: number
  existing_funding: number
  funding_gap: number
  recommended_monthly_contribution: number
  planned_savings_contribution: number
  planned_investment_contribution: number
  projected_funding: number | null
  expected_shortfall: number
  funding_status: 'fully_funded' | 'underfunded' | 'already_funded'
  achievement_ratio: number
  reason: string
}

export interface Recommendation {
  schema_version: string
  generated_at: string
  run_id: number | null
  optimization_run_id: number | null
  financial_summary: string
  cash_flow_status: {
    monthly_income: number
    essential_expenses: number
    discretionary_expenses: number
    existing_emi: number
    monthly_surplus: number
    surplus_basis: string
    is_deficit: boolean
    protected_buffer: number
    buffer_deficit: number
    buffer_sustained: boolean
    available_goal_budget: number
    emergency_fund_target: number
    emergency_fund_progress: number
    emi_income_ratio: number
    emi_income_ratio_cap: number
    situation_tier: string
  }
  protected_buffer: {
    protected_monthly_buffer: number
    desired_monthly_buffer: number
    buffer_deficit: number
    buffer_sustained: boolean
    emergency_fund_months_held: number
    minimum_cash_reserve_rule: string
    explanation: string
  }
  available_goal_budget: number
  goal_recommendations: RecommendationGoal[]
  investment_options: Array<Record<string, unknown>>
  /** Amount, horizon, assumed return and projected value for the investment sleeve. */
  investment_terms?: Record<string, unknown>
  loan_options: Array<Record<string, unknown>>
  /** Principal, rate, tenure, EMI and total interest for the plan's borrowing. */
  loan_terms?: Record<string, unknown>
  recommended_plan: {
    algorithm: string
    algorithm_label: string
    status: string
    feasible: boolean
    monthly_contributions_total: number
    monthly_savings_total: number
    monthly_investment_total: number
    new_loan_principal_total: number
    new_loan_emi_total: number
    total_shortfall: number
    weighted_goal_achievement: number | null
    model_version: string
    config_version: string
    run_id: number | null
  }
  alternative_scenarios: Array<{ scenario: string; description: string }>
  risks_and_warnings: string[]
  data_sources: Array<{
    name: string
    provider: string
    data_quality: string
    source_url?: string
    retrieved_at?: string | null
    note?: string
  }>
  assumptions: Record<string, unknown>
  missing_information: string[]
  monthly_actions: string[]
  explanation: string
  disclaimer: string
  technical_notes?: string[]
  llm: {
    provider: string
    model: string
    configured: boolean
    used: boolean
    status: string
    reason?: string | null
    message?: string
    latency_ms?: number
    validation?: Record<string, unknown>
  }
  validation: Record<string, unknown>
  stored_status?: string
  stored_model?: string
}

export interface RecommendationStatus {
  llm: {
    provider: string
    configured: boolean
    enabled: boolean
    sdk_installed: boolean
    model: string
    available: boolean
    key_env_var: string
    fallback: string
  }
  fallback_available: boolean
  fallback_note: string
  schema_version: string
}

export interface AskResponse {
  answer: string
  grounded_on: Record<string, unknown>
  llm: Record<string, unknown>
  disclaimer: string
}

/* ------------------------------------------------------------------------ APIs */

export const investmentsApi = {
  discover: (params: { horizon_months?: number; include_history?: boolean; limit?: number; category?: string[] } = {}) => {
    const query = new URLSearchParams()
    if (params.horizon_months) query.set('horizon_months', String(params.horizon_months))
    if (params.include_history) query.set('include_history', 'true')
    if (params.limit) query.set('limit', String(params.limit))
    for (const category of params.category ?? []) query.append('category', category)
    const suffix = query.toString() ? `?${query}` : ''
    return request<InvestmentDiscovery>(`/investments/discover${suffix}`)
  },
  providers: () => request<Record<string, unknown>>('/investments/providers'),
  refresh: () => request<{ ok: boolean; message: string }>('/investments/refresh', { method: 'POST' }),
  methodology: () => request<Record<string, unknown>>('/investments/methodology'),
}

export const loansApi = {
  discover: (params: { principal?: number; tenure_months?: number; category?: string[]; scenario_rate?: number } = {}) => {
    const query = new URLSearchParams()
    if (params.principal) query.set('principal', String(params.principal))
    if (params.tenure_months) query.set('tenure_months', String(params.tenure_months))
    if (params.scenario_rate !== undefined) query.set('scenario_rate', String(params.scenario_rate))
    for (const category of params.category ?? []) query.append('category', category)
    const suffix = query.toString() ? `?${query}` : ''
    return request<LoanDiscovery>(`/loans/discover${suffix}`)
  },
  analyse: (input: QuoteInput) => request<QuoteAnalysis>('/loans/analyse', { method: 'POST', body: input }),
  providers: () => request<Record<string, unknown>>('/loans/providers'),
  methodology: () => request<Record<string, unknown>>('/loans/methodology'),
}

export const recommendationsApi = {
  status: () => request<RecommendationStatus>('/recommendations/status'),
  generate: (input: { include_investments?: boolean; include_loans?: boolean; include_history?: boolean; loan_principal?: number; loan_tenure_months?: number } = {}) =>
    request<Recommendation>('/recommendations/generate', { method: 'POST', body: input }),
  latest: () => request<Recommendation>('/recommendations/latest'),
  read: (id: number) => request<Recommendation>(`/recommendations/${id}`),
  history: () => request<{ items: Array<Record<string, unknown>> }>('/recommendations/history'),
  ask: (question: string) => request<AskResponse>('/recommendations/ask', { method: 'POST', body: { question } }),
}

