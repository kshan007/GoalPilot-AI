/**
 * TypeScript mirror of the GoalPilot AI Platform API contract.
 *
 * Every shape here is taken from the backend's actual Pydantic response models. Nothing is
 * invented and nothing is optional "just in case" unless the backend really can omit it.
 */

export type RiskLevel = 'low' | 'moderate' | 'high'
export type LiquidityLevel = 'low' | 'medium' | 'high'
export type Frequency = 'monthly' | 'annual' | 'quarterly' | 'weekly' | 'one_time'
export type AssetType = 'liquid_savings' | 'emergency_savings' | 'investment' | 'fixed_deposit' | 'other'
export type LiabilityType =
  | 'home_loan'
  | 'vehicle_loan'
  | 'personal_loan'
  | 'education_loan'
  | 'credit_card'
  | 'other'
export type GoalType =
  | 'education'
  | 'higher_studies'
  | 'vehicle'
  | 'home'
  | 'wedding'
  | 'retirement'
  | 'travel'
  | 'emergency'
  | 'custom'
export type GoalStatus = 'active' | 'paused' | 'completed' | 'archived'
export type TxnKind = 'income' | 'expense'
export type TxnStatus = 'estimated' | 'actual'
export type TxnClass = 'essential' | 'discretionary' | 'income'
export type Algorithm = 'lp' | 'rl' | 'hybrid' | 'rule_baseline' | 'lp_unconstrained'

export interface MessageResponse {
  message: string
}

/* ------------------------------------------------------------------ auth */

export interface User {
  id: number
  email: string
  full_name: string
  created_at: string
  last_login_at: string | null
  is_admin: boolean
}

export interface TokenResponse {
  user: User
  access_token: string
  token_type: string
}

export interface ForgotPasswordResponse {
  message: string
  reset_token: string | null
}

/* -------------------------------------------------------------- profile */

export interface Preferences {
  currency: string
  locale: string
  risk_tolerance: string
  loss_ability: string
  liquidity_requirement: string
  assumptions: Record<string, unknown>
  onboarding_step: number
  onboarding_completed: boolean
}

export interface PreferencesInput {
  currency: string
  locale: string
  risk_tolerance: RiskLevel
  loss_ability: RiskLevel
  liquidity_requirement: LiquidityLevel
  assumptions: Record<string, number>
}

export interface FinancialProfile {
  id: number
  monthly_income: number
  essential_expenses: number
  discretionary_expenses: number
  monthly_savings_target: number
  savings_target_is_mandatory: boolean
  preferred_cash_buffer: number
  willing_to_adjust_discretionary: boolean
  emergency_months: number
  emi_income_ratio_cap: number
  risk_capacity: number
  inflation_assumption: number
  investment_return_assumption: number
  savings_return_assumption: number
  loan_interest_assumption: number
}

export interface ProfileInput {
  monthly_income: number
  essential_expenses: number
  discretionary_expenses: number
  monthly_savings_target: number
  savings_target_is_mandatory: boolean
  preferred_cash_buffer: number
  willing_to_adjust_discretionary: boolean
  emergency_months: number
  emi_income_ratio_cap: number
  risk_capacity: number
  inflation_assumption: number
  investment_return_assumption: number
  savings_return_assumption: number
  loan_interest_assumption: number
}

export interface CashFlow {
  monthly_income: number
  essential_expenses: number
  discretionary_expenses: number
  existing_emi: number
  monthly_surplus: number
  liquid_savings: number
  emergency_savings: number
  total_assets: number
  usable_existing_investments: number
  non_liquid_assets: number
  outstanding_debt: number
  emergency_months: number
  emergency_fund_target: number
  emergency_fund_gap: number
  emergency_fund_progress: number
  emi_income_ratio: number
  emi_income_ratio_cap: number
  risk_capacity: number
  savings_target: number
  savings_target_is_mandatory: boolean
  savings_target_attainment: number
  earmarked_goal_funding: number
  available_cash_for_goals: number
  is_deficit: boolean
  situation_tier: string
  warnings: string[]
}

export interface OnboardingState {
  step: number
  completed: boolean
  income_count: number
  asset_count: number
  liability_count: number
  goal_count: number
  has_profile: boolean
  next_step_hint: string
}

export interface ProfileResponse {
  profile: FinancialProfile | null
  summary: CashFlow | null
}

/* ------------------------------------------- income / assets / liabilities */

export interface IncomeSource {
  id: number
  source_type: string
  label: string
  amount: number
  frequency: Frequency
  stability: string
  is_recurring: boolean
  expected_day: number | null
  is_active: boolean
  monthly_equivalent: number
  annual_equivalent: number
}

export interface IncomeSourceInput {
  source_type: string
  label: string
  amount: number
  frequency: Frequency
  stability: string
  is_recurring: boolean
  expected_day: number | null
  is_active: boolean
}

export interface Asset {
  id: number
  asset_type: AssetType
  label: string
  current_value: number
  is_liquid: boolean
  usable_for_goals: boolean
  annual_return: number
  risk_score: number
  earmarked_goal_id: number | null
}

export type AssetInput = Omit<Asset, 'id'>

export interface Liability {
  id: number
  liability_type: LiabilityType
  label: string
  outstanding_principal: number
  annual_interest_rate: number
  emi_amount: number
  remaining_tenure_months: number
  total_repayment_if_held_to_tenure: number
  total_interest_if_held_to_tenure: number
}

export type LiabilityInput = Omit<
  Liability,
  'id' | 'total_repayment_if_held_to_tenure' | 'total_interest_if_held_to_tenure'
>

/* ----------------------------------------------------------------- goals */

export interface Goal {
  id: number
  name: string
  purpose: string
  goal_type: string
  current_cost: number
  target_date: string
  current_funded_amount: number
  priority: number
  criticality: number
  date_flexible: boolean
  amount_flexible: boolean
  liquidity_requirement: string
  risk_constraint: number
  status: string
  created_at: string
}

export type GoalInput = Omit<Goal, 'id' | 'created_at'>

export interface GoalProjection {
  goal_ref: string
  goal_id: number | null
  name: string
  goal_type: string
  priority: number
  criticality: number
  target_date: string
  months_remaining: number
  current_cost: number
  future_target: number
  existing_funding: number
  remaining_gap: number
  required_monthly_contribution: number
  planned_monthly_contribution: number | null
  projected_funding: number | null
  projected_shortfall: number | null
  achievement_ratio: number | null
  feasibility: string
  date_flexible: boolean
  amount_flexible: boolean
  inflation_assumption: number
  investment_return_assumption: number
  uncertainty: string
  notes: string[]
}

export interface GoalContribution {
  id: number
  goal_id: number
  amount: number
  contribution_date: string
  source: string
  note: string
  created_at: string
}

export interface GoalDetail {
  goal: Goal
  projection: GoalProjection
  alternatives: Array<Record<string, string>>
  contributions: GoalContribution[]
  assumptions: {
    inflation: number
    investment_return: number
    note: string
  }
}

/* --------------------------------------------------------------- monthly */

export interface MonthRecord {
  period: string
  status: string
  total_income_expected: number
  total_income_actual: number
  total_expense_estimated: number
  total_expense_actual: number
  surplus_projected: number
  surplus_actual: number
  reconciled_at: string | null
  transaction_count: number
}

export interface Transaction {
  id: number
  kind: string
  category: string
  label: string
  amount: number
  txn_date: string
  classification: string
  status: string
  is_recurring: boolean
  goal_id: number | null
  note: string
}

export interface TransactionInput {
  kind: TxnKind
  category: string
  label: string
  amount: number
  txn_date: string
  classification?: TxnClass | null
  status: TxnStatus
  is_recurring: boolean
  goal_id?: number | null
  note: string
  client_ref?: string | null
}

export interface CategoryTotals {
  actual: number
  estimated: number
  budget: number
}

export interface ForecastCategory {
  category: string
  amount: number
  method: string
  history_months_used: number
  is_provisional: boolean
  data_quality: string
  input_cutoff: string
}

export interface MonthForecastBlock {
  generated_at: string
  method_version: string
  total: number
  is_provisional: boolean
  categories: ForecastCategory[]
}

export interface ReconciliationRow {
  category: string
  forecast: number
  actual: number
  abs_error: number
  pct_error: number | null
  over_budget: boolean
}

export interface ReconciliationBlock {
  evaluated_at: string
  rows: ReconciliationRow[]
  totals: {
    forecast: number
    actual: number
    abs_error: number
    pct_error: number | null
  }
  over_budget_categories: string[]
  under_budget_categories: string[]
}

export interface MonthDetail {
  month: MonthRecord
  transactions: Transaction[]
  categories: Record<string, CategoryTotals>
  forecast: MonthForecastBlock | null
  reconciliation: ReconciliationBlock | null
}

export interface EstimateResponse {
  period: string
  forecast: {
    period: string
    months_of_history: number
    personalised: boolean
    total_forecast: number
    category_forecasts: Array<{
      category: string
      amount: number
      method: string
      history_months_used: number
      observations_used: number
      is_provisional: boolean
      data_quality: string
      note: string
    }>
  }
  persisted_count: number
  expected_month_end_spending: number
  projected_surplus: number
  history_months_available: number
  personalised: boolean
  estimation_method: string
  data_quality_note: string
}

export interface ReconcileResponse {
  period: string
  evaluations_created: number
  rows: Array<{
    category: string
    forecast: number
    actual: number
    abs_error: number
    pct_error: number | null
  }>
  totals: { forecast: number; actual: number; abs_error: number; pct_error: number | null }
  over_budget_categories: string[]
  under_budget_categories: string[]
  financial_impact: {
    income_actual: number
    expense_actual: number
    surplus_actual: number
    surplus_projected_at_estimation: number
    note: string
  }
  forecast_preserved: boolean
  next_forecast_note: string | null
}

export interface ReconciliationResponse {
  period: string
  reconciled: boolean
  message?: string
  category_actuals?: Record<string, number>
  evaluated_at?: string
  rows?: ReconciliationRow[]
  totals?: { forecast: number; actual: number; abs_error: number; pct_error: number | null }
  over_budget_categories?: string[]
  under_budget_categories?: string[]
}

export interface BudgetStatusRow {
  category: string
  monthly_limit: number
  spent: number
  remaining: number
  utilisation: number | null
  over_budget: boolean
}

export interface BudgetStatusResponse {
  period: string
  budgets: BudgetStatusRow[]
  persistent_overspend: Array<Record<string, unknown>>
  recurring_categories: Array<Record<string, unknown>>
}

export interface Budget {
  id: number
  category: string
  monthly_limit: number
  classification: 'essential' | 'discretionary'
  is_active: boolean
}

export type BudgetInput = Omit<Budget, 'id'>

export interface ForecastHistoryItem {
  period: string
  category: string
  amount: number
  method: string
  method_version: string
  history_months_used: number
  is_provisional: boolean
  data_quality: string
  input_cutoff: string
  created_at: string
}

export interface ForecastHistoryResponse {
  count: number
  forecasts: ForecastHistoryItem[]
  note: string
}

export interface ForecastAccuracyResponse {
  periods_evaluated: number
  periods: Array<{
    period: string
    forecast: number
    actual: number
    abs_error: number
    pct_error: number | null
  }>
  mae_per_period: number | null
  walk_forward_backtest: Record<string, unknown>
  evidence_note: string
}

/* ---------------------------------------------------------- optimization */

export interface Assumptions {
  annual_inflation: number
  investment_return: number
  savings_return: number
  loan_annual_rate: number
  loan_tenure_months: number
  max_loan_per_goal: number
  max_new_loan: number
  investment_capacity_ratio: number | null
  emergency_months: number | null
  allow_financing: boolean
  enforce_investment_capacity: boolean
}

export type AssumptionOverrides = Partial<Assumptions>

export interface AlgorithmAvailability {
  algorithm: string
  label: string
  ready: boolean
  status: string
  reason: string | null
  detail: Record<string, unknown>
}

export interface GoalAllocation {
  goal_ref: string
  goal_id: number | null
  goal_name: string
  funding_gap: number
  future_goal_cost: number
  initial_savings_allocated: number
  existing_assets_allocated: number
  monthly_savings_contribution: number
  monthly_investment_contribution: number
  loan_principal: number
  estimated_loan_emi: number
  shortfall: number
  achievement_ratio: number
  projected_new_funding: number
  target: number | null
  funded: number | null
}

export interface PlanDiff {
  previous_run_id: number | null
  changed: boolean
  summary: string
  goal_changes: Array<Record<string, unknown>>
  totals: Record<string, unknown>
}

/** One-change-at-a-time re-solve of a plan's own constraints. Never applied automatically. */
export interface PlanAlternative {
  option: string
  goal_ref: string
  goal_name: string
  change: string
  feasible: boolean
  achievement_ratio: number | null
  required_monthly: number
  shortfall_after: number
  loan_amount: number | null
  emi: number | null
  extra_interest: number | null
  detail: string
  evaluated_with: string
  applied_to_plan: boolean
}

/** Financial resilience, reported separately from whether the goals are funded. */
export interface ReadinessBlock {
  status: string
  flags: string[]
  goal_feasibility_is_separate: boolean
  note: string
  emergency_fund: {
    target: number
    target_months: number
    current: number
    gap: number
    progress: number
  }
  protected_buffer: {
    requested: number
    protected: number
    deficit: number
    sustained: boolean
  }
  debt: {
    existing_emi: number
    outstanding_principal: number
    emi_income_ratio: number
    emi_income_ratio_cap: number
    headroom: number
  }
  cash: {
    available_goal_budget: number
    available_cash_for_goals: number
    requested_buffer_is_mandatory: boolean
  }
  warnings: string[]
}

export interface PlanResponse {
  run_id: number
  algorithm: string
  algorithm_label: string
  status: string
  feasible: boolean
  objective_value: number | null
  /** What the objective measures. It is a penalty score, not a currency amount. */
  objective_definition: string | null
  /** Emergency fund, buffer and debt service — deliberately separate from goals_funded. */
  readiness: ReadinessBlock
  runtime_ms: number
  model_version: string
  config_version: string
  assumptions: Record<string, unknown>
  summary: Record<string, unknown>
  constraints: Record<string, unknown>
  diagnostics: Record<string, unknown>
  alternatives: PlanAlternative[]
  /** Constraints satisfied — not the same as every goal being affordable. */
  goals_funded: boolean
  unfunded_goals: string[]
  total_shortfall: number
  allocations: GoalAllocation[]
  goal_projections: GoalProjection[]
  cashflow: Record<string, unknown>
  warnings: string[]
  fallback_reason: string | null
  diff: PlanDiff | null
  created_at: string
}

export interface ComparisonArm {
  algorithm: string
  label: string
  status: string
  feasible: boolean
  available: boolean
  metric_basis: string
  metrics: Record<string, unknown>
  /** Same keys and units for every arm — the only block that may be compared across arms. */
  metrics_comparable: Record<string, unknown>
  /** False when the arm was scored on a different basis and must not be ranked. */
  ranked: boolean
  runtime_ms: number
  model_version: string
  warnings: string[]
  fallback_reason: string | null
}

export interface ComparisonResponse {
  run_id: number
  selector_version: string
  recommended_algorithm: string
  recommendation_reason: string
  sufficient_evidence_for_change: boolean
  decision_rule: Record<string, unknown>
  arms: ComparisonArm[]
  not_selected: Array<{ algorithm: string; label: string; reason: string }>
  /** What each comparison metric means, measured how, in what unit. */
  metric_definitions: Record<string, string>
  notes: string[]
  capacity_ratio: number
  capacity_derivation: string
  runtime_ms: number
  research_reference: Record<string, unknown>
  created_at: string
}

export interface OptimizationRunSummary {
  id: number
  kind: string
  algorithm: string
  status: string
  feasible: boolean
  objective_value: number | null
  weighted_achievement: number | null
  total_shortfall: number | null
  runtime_ms: number
  model_version: string
  created_at: string
  warnings: string[]
}

export interface OptimizationRunsResponse {
  limit: number
  offset: number
  items: OptimizationRunSummary[]
}

/* ------------------------------------------------------------- scenarios */

export interface ScenarioPreset {
  preset: string
  name: string
  description: string
  parameters: Record<string, number>
  assumption_note: string
}

export interface ScenarioRun {
  id: number
  preset: string | null
  name: string | null
  parameters: Record<string, unknown>
  baseline: Record<string, unknown>
  stressed: Record<string, unknown>
  deltas: Record<string, unknown>
  narrative: string[]
  created_at: string
}

export interface ScenarioRunListItem {
  id: number
  preset: string | null
  baseline_run_id: number | null
  stressed_run_id: number | null
  narrative: string[]
  created_at: string
}

export interface ScenarioRunsResponse {
  limit: number
  items: ScenarioRunListItem[]
}

export interface ScenarioRunRequest {
  preset: string
  parameters: Record<string, number>
  algorithm: Algorithm
  name: string
}

/* ------------------------------------------------------------- dashboard */

export interface DashboardTrendPoint {
  period: string
  income_actual: number
  income_expected: number
  expense_actual: number
  expense_estimated: number
  surplus_actual: number
  surplus_projected: number
  status: string
}

export interface DashboardCategoryPoint {
  category: string
  actual: number
  estimated: number
}

export interface DashboardFundingPoint {
  name: string
  future_target: number
  existing_funding: number
  remaining_gap: number
  feasibility: string
}

export interface Dashboard {
  as_of: string
  cashflow: CashFlow
  goals: {
    active_count: number
    total_goals: number
    on_track: number
    at_risk: number
    total_remaining_gap: number
    total_required_monthly: number
    items: GoalProjection[]
    funding_chart: DashboardFundingPoint[]
  }
  monthly: {
    current_period: string
    current: DashboardTrendPoint | null
    trend: DashboardTrendPoint[]
    category_breakdown: DashboardCategoryPoint[]
  }
  forecasts: {
    latest_count: number
    latest: Array<{
      period: string
      category: string
      amount: number
      method: string
      is_provisional: boolean
      data_quality: string
    }>
    error_trend: Array<{ period: string; forecast: number; actual: number; abs_error: number }>
    persistent_overspend: Array<Record<string, unknown>>
  }
  debt: {
    outstanding_principal: number
    monthly_emi: number
    emi_income_ratio: number
    emi_income_ratio_cap: number
    within_cap: boolean
  }
  optimization: {
    last_plan: {
      run_id: number
      algorithm: string
      status: string
      feasible: boolean
      weighted_achievement: number | null
      total_shortfall: number | null
      created_at: string
      summary: Record<string, unknown>
    } | null
    last_comparison: {
      run_id: number
      recommended_algorithm: string
      created_at: string
      arms: Array<{
        algorithm: string | null
        label: string | null
        weighted_goal_achievement: number | null
        pct_goals_met_by_deadline: number | null
        available: boolean | null
      }>
    } | null
  }
  labels_note: string
}

/* ------------------------------------------------------------- models/meta */

export interface ModelRegistryEntry {
  name: string
  version: string
  kind: string
  status: string
  artifact_path: string
  metadata: Record<string, unknown>
  evaluated_at: string | null
}

export interface ModelRegistryResponse {
  research: Record<string, unknown>
  entries: ModelRegistryEntry[]
  note: string
}

export interface HealthResponse {
  status: string
  app_name: string
  version: string
  environment: string
  research_source: Record<string, unknown>
  supported_features: Record<string, unknown>
  disclaimer: string
}

export interface AssumptionsMetaResponse {
  defaults: {
    annual_inflation: number
    investment_return: number
    savings_return: number
    loan_annual_rate: number
    loan_tenure_months: number
    emergency_months: number
    emi_income_ratio_cap: number
  }
  note: string
  provenance_rules: string[]
  cashflow_definition: Record<string, string>
  essential_categories: string[]
  scenario_presets: ScenarioPreset[]
  algorithm_labels: Record<string, string>
  forecast: Record<string, unknown>
}

export interface EducationResponse {
  items: Array<{ topic: string; principle: string; source: string }>
  citation_policy: string
  separation_note: string
}

export interface DataProvenanceResponse {
  research_available: boolean
  research_root: string
  datasets: Array<{
    name: string
    kind: string
    rows?: number
    goal_rows?: number
    period?: string
    used_for: string
    caveat: string
  }>
  note: string
}

export type AccountExport = Record<string, unknown>


/* ------------------------------------------------------------------ admin */
export interface AdminOverview {
  generated_at: string
  users: { total: number; active: number; admins: number; new_last_7_days: number }
  runs: {
    total: number
    last_7_days: number
    failed: number
    by_status: Record<string, number>
    by_algorithm: Record<string, number>
    by_kind: Record<string, number>
    avg_runtime_ms_by_algorithm: Record<string, number>
  }
  activity: { date: string; runs: number }[]
  recent_failures: {
    id: number
    created_at: string
    algorithm: string
    status: string
    runtime_ms: number
    warnings: string[]
  }[]
  recent_audit: AdminAuditEntry[]
  models: { name: string; kind: string; status: string; detail?: string }[]
  data_sources: { name: string; kind: string; used_for: string; caveat: string }[]
}

export interface AdminRunRow {
  id: number
  created_at: string
  user_email: string
  algorithm: string
  kind: string
  status: string
  feasible: boolean
  runtime_ms: number
  weighted_achievement: number
  total_shortfall: number
  model_version: string
}

export interface AdminRunsPage {
  items: AdminRunRow[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface AdminRunDetail extends AdminRunRow {
  objective_value: number | null
  config_version: string
  label: string
  summary: Record<string, unknown>
  constraints: Record<string, unknown>
  diagnostics: Record<string, unknown>
  alternatives: Record<string, unknown>[]
  warnings: string[]
  assumptions: Record<string, unknown>
  allocations: {
    goal_ref: string
    goal_name: string
    future_goal_cost: number
    funding_gap: number
    monthly_savings_contribution: number
    monthly_investment_contribution: number
    loan_principal: number
    estimated_loan_emi: number
    projected_new_funding: number
    shortfall: number
    achievement_ratio: number
  }[]
}

export interface AdminUserRow {
  id: number
  email: string
  full_name: string
  is_active: boolean
  is_admin: boolean
  created_at: string
  last_login_at: string | null
  runs: number
}

export interface AdminUsersPage {
  items: AdminUserRow[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface AdminAuditEntry {
  id: number
  created_at: string
  actor_email: string
  action: string
  target_type: string
  target_id: string
  details: Record<string, unknown>
}

export interface AdminAuditPage {
  items: AdminAuditEntry[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface AdminHealth {
  database: { reachable: boolean; error: string | null }
  research: Record<string, unknown>
  models: Record<string, unknown>
  optimization: { failed_runs: number; last_failure_at: string | null; last_failure_id: number | null }
  data_sources: { name: string; kind: string; used_for: string; caveat: string }[]
  assumptions: Record<string, number>
}

export interface AdminData {
  datasets: { name: string; kind: string; used_for: string; caveat: string; rows?: number; period?: string }[]
  note: string
  research_available: boolean
  defaults: Record<string, number>
  assumption_note: string
  provenance_rules: string[]
  editing: { supported: boolean; reason: string }
}
