/**
 * Typed fetch wrapper for the GoalPilot AI Platform API.
 *
 * Responsibilities:
 *  - one place that knows the base URL and the bearer token
 *  - one place that converts the backend error envelope into a typed ApiError
 *  - one place that reacts to 401 by clearing the token and sending the user to /login
 */
import type {
  AccountExport,
  AdminAuditPage,
  AdminData,
  AdminHealth,
  AdminOverview,
  AdminRunDetail,
  AdminRunsPage,
  AdminUserRow,
  AdminUsersPage,
  Algorithm,
  AlgorithmAvailability,
  Asset,
  AssetInput,
  AssumptionsMetaResponse,
  Budget,
  BudgetInput,
  BudgetStatusResponse,
  CashFlow,
  ComparisonResponse,
  Dashboard,
  DataProvenanceResponse,
  EducationResponse,
  EstimateResponse,
  FinancialProfile,
  ForecastAccuracyResponse,
  ForecastHistoryResponse,
  ForgotPasswordResponse,
  Goal,
  GoalContribution,
  GoalDetail,
  GoalInput,
  GoalProjection,
  HealthResponse,
  IncomeSource,
  IncomeSourceInput,
  Liability,
  LiabilityInput,
  MessageResponse,
  ModelRegistryResponse,
  MonthDetail,
  MonthRecord,
  OptimizationRunsResponse,
  PlanResponse,
  Preferences,
  PreferencesInput,
  ProfileInput,
  ProfileResponse,
  ReconcileResponse,
  ReconciliationResponse,
  ScenarioPreset,
  ScenarioRun,
  ScenarioRunRequest,
  ScenarioRunsResponse,
  TokenResponse,
  Transaction,
  TransactionInput,
  User,
} from './types'

export const TOKEN_KEY = 'gp_token'

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api'
).replace(/\/+$/, '')

export interface ApiErrorBody {
  code: string
  message: string
  details: Record<string, unknown>
}

export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly details: Record<string, unknown>

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

export function getToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string): void {
  try {
    window.localStorage.setItem(TOKEN_KEY, token)
  } catch {
    /* storage unavailable: the session simply will not persist */
  }
}

export function clearToken(): void {
  try {
    window.localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* nothing to do */
  }
}

/**
 * Human-readable message for any thrown value, preferring the API's own message.
 *
 * A 422 arrives as the generic "Request validation failed" with the actual reasons in
 * ``details`` (one entry per offending field). Without appending those, the UI told the user
 * nothing they could act on.
 */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const reasons = Object.entries(error.details ?? {}).map(([field, detail]) => {
      const text = typeof detail === 'string' ? detail : JSON.stringify(detail)
      return field === 'body' ? text : `${field}: ${text}`
    })
    if (reasons.length === 0) return error.message
    return `${error.message} — ${reasons.join('; ')}`
  }
  if (error instanceof Error) return error.message
  return 'An unexpected error occurred.'
}

function redirectToLogin(): void {
  if (typeof window === 'undefined') return
  const { pathname, hash, search } = window.location
  if (pathname === '/login') return
  const next = encodeURIComponent(`${pathname}${search}${hash}`)
  window.location.assign(`/login?next=${next}`)
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH'
  body?: unknown
  /** Skip the Authorization header (register / login / password recovery only). */
  anonymous?: boolean
  signal?: AbortSignal
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, anonymous = false, signal } = options
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (!anonymous) {
    const token = getToken()
    if (token) headers.Authorization = `Bearer ${token}`
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    })
  } catch (networkError) {
    throw new ApiError(
      0,
      'network_error',
      `Could not reach the GoalPilot API at ${API_BASE_URL}. Check that the backend is running.`,
    )
  }

  if (response.status === 401) {
    clearToken()
    redirectToLogin()
    throw new ApiError(401, 'unauthenticated', 'Your session has expired. Please sign in again.')
  }

  const text = await response.text()
  let payload: unknown = null
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      payload = null
    }
  }

  if (!response.ok) {
    const envelope = (payload as { error?: Partial<ApiErrorBody> } | null)?.error
    throw new ApiError(
      response.status,
      envelope?.code ?? `http_${response.status}`,
      envelope?.message ?? `Request failed with status ${response.status}.`,
      (envelope?.details as Record<string, unknown>) ?? {},
    )
  }

  return payload as T
}

/* ------------------------------------------------------------------- auth */

export const authApi = {
  register: (input: { email: string; password: string; full_name: string }) =>
    request<TokenResponse>('/auth/register', { method: 'POST', body: input, anonymous: true }),

  login: (input: { email: string; password: string }) =>
    request<TokenResponse>('/auth/login', { method: 'POST', body: input, anonymous: true }),

  /** Separate door for administrators; ordinary accounts are refused by the API. */
  adminLogin: (input: { email: string; password: string }) =>
    request<TokenResponse>('/auth/admin/login', { method: 'POST', body: input, anonymous: true }),

  logout: () => request<MessageResponse>('/auth/logout', { method: 'POST' }),

  me: () => request<User>('/auth/me'),

  forgotPassword: (input: { email: string }) =>
    request<ForgotPasswordResponse>('/auth/forgot-password', {
      method: 'POST',
      body: input,
      anonymous: true,
    }),

  resetPassword: (input: { token: string; new_password: string }) =>
    request<MessageResponse>('/auth/reset-password', {
      method: 'POST',
      body: input,
      anonymous: true,
    }),

  changePassword: (input: { current_password: string; new_password: string }) =>
    request<MessageResponse>('/auth/change-password', { method: 'POST', body: input }),
}

/* ---------------------------------------------------------------- profile */

export const profileApi = {
  read: () => request<ProfileResponse>('/profile'),

  update: (input: ProfileInput) => request<FinancialProfile>('/profile', { method: 'PUT', body: input }),

  summary: () => request<CashFlow>('/profile/summary'),
}

export const preferencesApi = {
  read: () => request<Preferences>('/settings/preferences'),

  update: (input: PreferencesInput) =>
    request<Preferences>('/settings/preferences', { method: 'PUT', body: input }),
}

/* -------------------------------------------------------------- onboarding */

export const onboardingApi = {
  read: () => request<import('./types').OnboardingState>('/onboarding'),

  setStep: (step: number) =>
    request<import('./types').OnboardingState>('/onboarding', { method: 'PUT', body: { step } }),

  complete: () => request<MessageResponse>('/onboarding/complete', { method: 'POST' }),
}

/* --------------------------------------------- income / assets / liabilities */

export const incomeApi = {
  list: () => request<IncomeSource[]>('/income-sources'),

  create: (input: IncomeSourceInput) =>
    request<IncomeSource>('/income-sources', { method: 'POST', body: input }),

  update: (id: number, input: IncomeSourceInput) =>
    request<IncomeSource>(`/income-sources/${id}`, { method: 'PUT', body: input }),

  remove: (id: number) => request<MessageResponse>(`/income-sources/${id}`, { method: 'DELETE' }),
}

export const assetsApi = {
  list: () => request<Asset[]>('/assets'),

  create: (input: AssetInput) => request<Asset>('/assets', { method: 'POST', body: input }),

  update: (id: number, input: AssetInput) =>
    request<Asset>(`/assets/${id}`, { method: 'PUT', body: input }),

  remove: (id: number) => request<MessageResponse>(`/assets/${id}`, { method: 'DELETE' }),
}

export const liabilitiesApi = {
  list: () => request<Liability[]>('/liabilities'),

  create: (input: LiabilityInput) => request<Liability>('/liabilities', { method: 'POST', body: input }),

  update: (id: number, input: LiabilityInput) =>
    request<Liability>(`/liabilities/${id}`, { method: 'PUT', body: input }),

  remove: (id: number) => request<MessageResponse>(`/liabilities/${id}`, { method: 'DELETE' }),
}

/* ------------------------------------------------------------------ goals */

export const goalsApi = {
  list: () => request<Goal[]>('/goals'),

  create: (input: GoalInput) => request<Goal>('/goals', { method: 'POST', body: input }),

  read: (id: number) => request<Goal>(`/goals/${id}`),

  update: (id: number, input: Partial<GoalInput>) =>
    request<Goal>(`/goals/${id}`, { method: 'PUT', body: input }),

  remove: (id: number) => request<MessageResponse>(`/goals/${id}`, { method: 'DELETE' }),

  detail: (id: number) => request<GoalDetail>(`/goals/${id}/detail`),

  plan: () => request<GoalProjection[]>('/goals/plan'),

  contributions: (id: number) => request<GoalContribution[]>(`/goals/${id}/contributions`),

  addContribution: (
    id: number,
    input: { amount: number; contribution_date: string; source: string; note: string },
  ) => request<GoalContribution>(`/goals/${id}/contributions`, { method: 'POST', body: input }),
}

/* ---------------------------------------------------------------- monthly */

export const monthlyApi = {
  list: () => request<MonthRecord[]>('/months'),

  open: (period: string) => request<MonthDetail>(`/months/${period}/open`, { method: 'POST' }),

  read: (period: string) => request<MonthDetail>(`/months/${period}`),

  transactions: (period: string) => request<Transaction[]>(`/months/${period}/transactions`),

  addTransaction: (period: string, input: TransactionInput) =>
    request<Transaction>(`/months/${period}/transactions`, { method: 'POST', body: input }),

  updateTransaction: (period: string, id: number, input: Partial<TransactionInput>) =>
    request<Transaction>(`/months/${period}/transactions/${id}`, { method: 'PUT', body: input }),

  removeTransaction: (period: string, id: number) =>
    request<MessageResponse>(`/months/${period}/transactions/${id}`, { method: 'DELETE' }),

  estimateExpenses: (
    period: string,
    input: {
      category_estimates: Record<string, number>
      recurring_categories: Record<string, number>
      persist: boolean
    },
  ) => request<EstimateResponse>(`/months/${period}/estimate-expenses`, { method: 'POST', body: input }),

  reconcile: (period: string, input: { mark_actuals: boolean; update_future_forecast: boolean }) =>
    request<ReconcileResponse>(`/months/${period}/reconcile`, { method: 'POST', body: input }),

  reconciliation: (period: string) => request<ReconciliationResponse>(`/months/${period}/reconciliation`),

  budgetStatus: (period: string) => request<BudgetStatusResponse>(`/months/${period}/budget-status`),
}

export const budgetsApi = {
  list: () => request<Budget[]>('/budgets'),

  create: (input: BudgetInput) => request<Budget>('/budgets', { method: 'POST', body: input }),

  update: (id: number, input: BudgetInput) =>
    request<Budget>(`/budgets/${id}`, { method: 'PUT', body: input }),

  remove: (id: number) => request<MessageResponse>(`/budgets/${id}`, { method: 'DELETE' }),
}

export const forecastApi = {
  history: () => request<ForecastHistoryResponse>('/forecast/history'),

  accuracy: () => request<ForecastAccuracyResponse>('/forecast/accuracy'),
}

/* ----------------------------------------------------------- optimization */

export const optimizeApi = {
  algorithms: () => request<AlgorithmAvailability[]>('/optimize/algorithms'),

  plan: (input: {
    algorithm: Algorithm
    assumptions?: Record<string, number | boolean>
    rl_checkpoint?: string | null
    label?: string
  }) => request<PlanResponse>('/optimize/plan', { method: 'POST', body: input }),

  compare: () => request<ComparisonResponse>('/optimize/compare', { method: 'POST' }),

  runs: (kind?: 'plan' | 'compare') =>
    request<OptimizationRunsResponse>(`/optimize/runs${kind ? `?kind=${kind}` : ''}`),

  run: (id: number) => request<Record<string, unknown>>(`/optimize/runs/${id}`),
}

/* -------------------------------------------------------------- scenarios */

export const scenariosApi = {
  presets: () => request<ScenarioPreset[]>('/scenarios/presets'),

  run: (input: ScenarioRunRequest) => request<ScenarioRun>('/scenarios/run', { method: 'POST', body: input }),

  runs: () => request<ScenarioRunsResponse>('/scenarios/runs'),

  run1: (id: number) => request<ScenarioRun>(`/scenarios/runs/${id}`),
}

/* -------------------------------------------------------------- dashboard */

export const dashboardApi = {
  read: () => request<Dashboard>('/dashboard'),
}

export const modelsApi = {
  registry: () => request<ModelRegistryResponse>('/models/registry'),
  benchmarks: () => request<Record<string, unknown>>('/models/benchmarks'),
  checkpoints: () => request<Record<string, unknown>>('/models/checkpoints'),
  researchEvaluation: () => request<Record<string, unknown>>('/models/research-evaluation'),
}

export const accountApi = {
  export: () => request<AccountExport>('/account/export'),

  remove: () => request<MessageResponse>('/account?confirm=DELETE', { method: 'DELETE' }),
}

export const metaApi = {
  health: () => request<HealthResponse>('/health'),
  assumptions: () => request<AssumptionsMetaResponse>('/meta/assumptions'),
  education: () => request<EducationResponse>('/meta/education'),
  dataProvenance: () => request<DataProvenanceResponse>('/meta/data-provenance'),
}

/** Trigger a browser download from any JSON payload returned by the API. */
export function downloadJson(filename: string, payload: unknown): void {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}



/* ------------------------------------------------------------------ admin */

function adminQuery(params: Record<string, string | number | undefined>): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && String(value) !== '') query.set(key, String(value))
  }
  const suffix = query.toString()
  return suffix ? `?${suffix}` : ''
}

export const adminApi = {
  overview: () => request<AdminOverview>('/admin/overview'),

  runs: (params: {
    page?: number
    page_size?: number
    algorithm?: string
    status?: string
    kind?: string
    search?: string
  }) => request<AdminRunsPage>(`/admin/runs${adminQuery(params)}`),

  run: (id: number) => request<AdminRunDetail>(`/admin/runs/${id}`),

  users: (params: {
    page?: number
    page_size?: number
    search?: string
    role?: string
    status?: string
  }) => request<AdminUsersPage>(`/admin/users${adminQuery(params)}`),

  updateUser: (id: number, body: { is_admin?: boolean; is_active?: boolean }) =>
    request<AdminUserRow>(`/admin/users/${id}`, { method: 'PATCH', body }),

  audit: (params: { page?: number; page_size?: number; action?: string }) =>
    request<AdminAuditPage>(`/admin/audit${adminQuery(params)}`),

  health: () => request<AdminHealth>('/admin/health'),

  data: () => request<AdminData>('/admin/data'),
}
