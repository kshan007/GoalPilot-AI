# GoalPilot AI Platform — Architecture

**Date:** 2026-10-14

---

## 1. Stack decision and rationale

The existing research system is **Python** (SciPy LP, Gymnasium, SB3/torch). The existing application
prototype is FastAPI + Vite/React. Therefore:

| Layer | Choice | Rationale |
|---|---|---|
| Backend | **FastAPI + Pydantic v2** | Reuses the existing prototype's stack; the models are Python and must run in-process (no cross-language bridge) |
| Models | **Existing research modules, imported not rewritten** | Section 3 |
| Database | **PostgreSQL 17** (verified running on this host) with SQLite fallback via `DATABASE_URL` | Production-grade; SQLite keeps a zero-setup local/demo path |
| ORM / migrations | **SQLAlchemy 2.0 + Alembic** | Explicit, versioned schema |
| Auth | **Self-hosted JWT (PyJWT) + bcrypt password hashing** | Supabase Auth would add an external hosted dependency and credentials for no benefit here; the brief permits "another secure approach justified by the existing code". Everything stays local and testable. |
| Frontend | **React 18 + TypeScript + Vite + Tailwind CSS** | Matches the existing prototype's React core while adding types; Tailwind gives a real design system |
| Charts | **Recharts** | Lightweight, composable, no canvas wrapper needed |
| Optimisation | `scipy.optimize.linprog(method="highs")` | Reused as-is |
| RL | **stable-baselines3 PPO** + Gymnasium env | Reused as-is |
| Background jobs | **None** | The heaviest request (a 3-arm comparison) is bounded at seconds; the brief says use jobs "only when justified". Training is offline. |

**Rejected:** microservices, a Node backend, a separate Python optimisation service (all would add
process/serialisation boundaries around an in-process model that already works), and any rewrite of
`goalpilot_env.py`.

---

## 2. Component diagram

```
┌───────────────────────────────────────────────────────────────────────────────┐
│  React + TS + Vite + Tailwind  (frontend/)                                    │
│  public: landing · login · register · forgot · reset · privacy                 │
│  app: dashboard · onboarding · profile · monthly · reconciliation · budgets    │
│       assets · liabilities · goals · goal detail · optimise · compare          │
│       scenarios · forecast history · reports · settings · account              │
└───────────────────────────────┬───────────────────────────────────────────────┘
                                │ HTTPS/JSON, Bearer JWT, /api/*
┌───────────────────────────────▼───────────────────────────────────────────────┐
│  FastAPI  (backend/app)                                                       │
│  api/       auth · profile · onboarding · income · assets · liabilities        │
│             goals · monthly · budgets · forecast · optimize · scenarios        │
│             dashboard · settings · account · models · meta                     │
│  core/      security(jwt,bcrypt) · deps(auth,session) · ratelimit · errors     │
│  services/  cashflow · goals · forecasting · reconciliation · plan_diff        │
│  engines/   research_loader · lp_engine · rl_engine · hybrid_engine · selector │
└──────┬──────────────────────────────────────┬─────────────────────────────────┘
       │ SQLAlchemy 2.0                       │ in-process import
┌──────▼──────────────┐              ┌────────▼──────────────────────────────────┐
│ PostgreSQL 17       │              │ GoalPilot_AI_Completed  (read-only)        │
│ (or SQLite)         │              │  multi_goal_optimizer · constrained_lp     │
│ users · profiles    │              │  goalpilot_env · goalpilot_config          │
│ income_sources      │              │  PPO checkpoints (best_model.zip)          │
│ assets · liabilities│              │  market path · population (benchmarks)     │
│ goals · contributions│             └───────────────────────────────────────────┘
│ months · transactions│
│ budgets · forecasts  │
│ forecast_evaluations │
│ optimization_runs    │
│ scenarios · model_versions
│ preferences · audit_events
└─────────────────────┘
```

**Model boundary.** `engines/research_loader.py` resolves the research root
(`GOALPILOT_RESEARCH_PATH` env var → explicit arg → walk-up detection) and imports the modules by
path. **No research file is ever modified.** The platform is a *consumer*.

---

## 3. How the models are reused

| Research module | Imported symbol | Used by |
|---|---|---|
| `GoalPilot_MultiGoal_Extension/src/multi_goal_optimizer.py` | `optimize_multi_goal`, `prepare_goals`, `FinancialState`, `monthly_emi_per_rupee`, `fv_monthly_contribution_factor` | `engines/lp_engine.py` |
| `…/rl_prototype/goalpilot_constrained_lp.py` | `solve_constrained_lp` | `engines/lp_engine.py` (the default LP arm) |
| `…/rl_prototype/goalpilot_config.py` | `GoalPilotConfig` | `engines/rl_engine.py` |
| `…/rl_prototype/goalpilot_env.py` | `GoalPilotEnv` | `engines/rl_engine.py` |
| `training_logs/experiments/ppo_recommended_v1/**/best/best_model.zip` | SB3 `PPO.load` | `engines/rl_engine.py` |
| `simulation/05_simulation_runs/rl_prototype/rl_market_credit_validated.csv` | monthly market path | every arm (shared assumption set) |
| `…/rl_sample_financial_profiles.csv` | benchmark population | `api/models_api.py` (benchmarks page) |

The research import is **lazy and cached**, so startup never pays for torch unless an RL request is
actually made.

---

## 4. Data flow of a plan request

```
1. Load user profile + goals + liabilities  (Postgres, ownership-scoped)
2. cashflow.build_state(...)
      monthly_income, essential, discretionary, existing_emi,
      liquid_savings, emergency_months, risk_capacity
   → explicit surplus = income − essential − discretionary − existing_emi  (F-06 fix)
3. goals.prepare(user_goals) → goal frame with the 12 required columns
      future_goal_cost = current_cost × (1+inflation)^(m/12)
4. Choose arm:
      LP  → solve_constrained_lp(goals, state, **assumptions)
      RL  → build population-schema row + goals frame → GoalPilotEnv → policy.predict → encode
      HYB → RL proposes preferences θ → LP solves under θ → simulator evaluates → validate
5. Validate EVERY arm: non-negativity, pool conservation, capacity, EMI cap, no double allocation
      violation → reject the arm and say why
6. selector.compare(arms, held_out_scenarios) → recommendation + reason + honest fallback
7. Persist to optimization_runs (inputs, assumptions, allocations, diagnostics, runtime, versions)
8. Return plan + explanation of the difference from the previous run
```

---

## 5. Database schema

Normalised, all monetary values `NUMERIC(18,2)`, all user-owned tables carry `user_id` with an FK to
`users.id` and a `ON DELETE CASCADE`. Every user-owned table is queried through an ownership-scoped
helper — never by primary key alone.

| Table | Purpose | Key columns |
|---|---|---|
| `users` | identity | `id`, `email` (unique, citext-lower), `password_hash`, `full_name`, `is_active`, `created_at`, `last_login_at` |
| `password_reset_tokens` | reset flow | `token_hash`, `user_id`, `expires_at`, `used_at` |
| `user_preferences` | settings | `currency`, `locale`, `risk_tolerance`, `loss_ability`, `liquidity_requirement`, `emergency_months`, `assumptions_json`, `onboarding_step`, `onboarding_completed` |
| `financial_profiles` | onboarding core | `monthly_income`, `essential_expenses`, `discretionary_expenses`, `monthly_savings_target`, `savings_target_is_mandatory`, `cash_buffer`, `adjust_discretionary`, `emi_income_ratio_cap`, `risk_capacity`, `emergency_months`, `inflation_assumption`, `investment_return_assumption`, `savings_return_assumption`, `loan_interest_assumption` |
| `income_sources` | income entries | `source_type`, `label`, `amount`, `frequency`, `stability`, `is_recurring`, `expected_day` |
| `assets` | savings & assets | `asset_type`, `label`, `current_value`, `is_liquid`, `usable_for_goals`, `earmarked_goal_id`, `annual_return` |
| `liabilities` | debt | `liability_type`, `label`, `outstanding_principal`, `annual_interest_rate`, `emi_amount`, `remaining_tenure_months` |
| `goals` | goals | `name`, `purpose`, `goal_type`, `current_cost`, `target_date`, `current_funded_amount`, `priority`, `criticality`, `date_flexible`, `amount_flexible`, `liquidity_requirement`, `risk_constraint`, `status` |
| `goal_contributions` | goal funding events | `goal_id`, `amount`, `contribution_date`, `source` |
| `goal_allocations` | plan output per goal | `optimization_run_id`, `goal_id`, `initial_savings_allocated`, `existing_assets_allocated`, `monthly_savings_contribution`, `monthly_investment_contribution`, `loan_principal`, `shortfall`, `achievement_ratio` |
| `monthly_records` | one row per user per month | `period` (YYYY-MM), `status` (open/estimated/reconciled), `total_income_actual`, `total_income_expected`, `total_expense_actual`, `total_expense_estimated`, `surplus_actual`, `surplus_projected`, `reconciled_at` |
| `transactions` | income & expense lines | `month_id`, `kind` (income/expense), `category`, `label`, `amount`, `txn_date`, `classification` (essential/discretionary/income), `status` (estimated/actual), `is_recurring` |
| `budgets` | category budgets | `category`, `monthly_limit`, `is_active` |
| `expense_forecasts` | forecast history | `month_id`, `category`, `forecast_amount`, `method`, `method_version`, `input_cutoff`, `is_provisional`, `created_at` |
| `forecast_evaluations` | forecast vs actual | `forecast_id`, `actual_amount`, `abs_error`, `pct_error`, `evaluated_at` |
| `optimization_runs` | plan history | `algorithm`, `status`, `assumptions_json`, `input_snapshot_json`, `result_json`, `objective_value`, `runtime_ms`, `model_version`, `config_version`, `created_at` |
| `scenarios` | scenario definitions | `name`, `preset`, `parameters_json` |
| `scenario_runs` | scenario results | `scenario_id`, `optimization_run_id`, `result_json`, `deltas_json` |
| `model_versions` | registry mirror | `name`, `version`, `kind`, `status`, `artifact_path`, `metadata_json`, `evaluated_at` |
| `audit_events` | security trail | `user_id`, `event_type`, `detail_json`, `ip`, `created_at` |

**Rounding rule.** Money is stored `NUMERIC(18,2)` and rounded with `ROUND_HALF_UP` at the
persistence boundary only; all internal arithmetic is float64 so the model behaviour matches the
research exactly. Rates are stored `NUMERIC(9,6)`.

---

## 6. API contract

Base path `/api`. All authenticated routes require `Authorization: Bearer <jwt>`. Errors use a
single shape: `{"error": {"code": "...", "message": "...", "details": {...}}}`.

### Auth
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/auth/register` | `{email, password, full_name}` | `{user, access_token, token_type}` |
| POST | `/auth/login` | `{email, password}` | `{user, access_token, token_type}` |
| POST | `/auth/logout` | — | `{ok: true}` |
| GET | `/auth/me` | — | `user` |
| POST | `/auth/forgot-password` | `{email}` | `{message, reset_token?}` (token only when `EXPOSE_RESET_TOKEN=true`, dev) |
| POST | `/auth/reset-password` | `{token, new_password}` | `{message}` |
| POST | `/auth/change-password` | `{current_password, new_password}` | `{message}` |

### Financial profile & onboarding
| Method | Path | Notes |
|---|---|---|
| GET | `/profile` | full profile incl. `summary` or `null` |
| PUT | `/profile` | upsert base profile fields |
| GET | `/profile/summary` | derived surplus, emergency metrics, situation tier |
| GET | `/onboarding` | `{step, completed, income_count, asset_count, liability_count, goal_count}` |
| PUT | `/onboarding` | `{step}` saved progress |
| POST | `/onboarding/complete` | marks complete after validation |

### Income / assets / liabilities
`GET|POST /income-sources`, `PUT|DELETE /income-sources/{id}` (same shape for `/assets`, `/liabilities`).

### Goals
`GET|POST /goals`, `GET|PUT|DELETE /goals/{id}`, `GET|POST /goals/{id}/contributions`,
`GET /goals/plan` → per-goal projection table.

### Monthly workflow
| Method | Path | Notes |
|---|---|---|
| GET | `/months` | list of periods |
| POST | `/months/{period}/open` | open/refresh a month, seeds recurring items |
| GET | `/months/{period}` | month detail + transactions + reconciliation state |
| GET\|POST | `/months/{period}/transactions` | add income/expense line |
| PUT\|DELETE | `/months/{period}/transactions/{id}` | edit/remove |
| POST | `/months/{period}/estimate-expenses` | generate + persist estimates (marked estimated) |
| POST | `/months/{period}/reconcile` | reconcile estimates vs actuals, preserve forecasts |
| GET | `/months/{period}/reconciliation` | category-wise error table |
| GET\|POST | `/budgets` | category budgets |
| PUT\|DELETE | `/budgets/{id}` | |

### Forecasting
`POST /forecast/run` · `GET /forecast/history` · `GET /forecast/accuracy`

### Optimisation
| Method | Path | Notes |
|---|---|---|
| GET | `/optimize/algorithms` | available arms, readiness, why |
| POST | `/optimize/plan` | `{algorithm, assumptions?}` → plan (persists a run) |
| POST | `/optimize/compare` | all arms on the same inputs → comparison + selection |
| GET | `/optimize/runs` | run history |
| GET | `/optimize/runs/{id}` | one run + plan diff vs previous |

### Scenarios
`GET /scenarios/presets` · `POST /scenarios/run` · `GET /scenarios/runs`

### Dashboard / models / account / meta
`GET /dashboard` · `GET /models/registry` · `GET /models/benchmarks` ·
`GET|PUT /settings/preferences` · `GET /account/export` · `DELETE /account` ·
`GET /health` · `GET /meta/assumptions`

---

## 7. Security boundaries

1. Every user-owned query is scoped by `user_id` from the verified JWT — never by client-supplied id.
2. Cross-user access returns **404**, not 403 (no existence disclosure).
3. bcrypt password hashing; JWT HS256 with a required `SECRET_KEY` (startup fails if unset in prod).
4. Rate limiting on `/auth/*` and `/optimize/*`.
5. CORS restricted to an explicit origin allow-list.
6. No stack traces in responses; internal errors are logged server-side only.
7. No secrets in frontend code or committed files; `.env` is git-ignored, `.env.example` documents
   every variable.
8. No uploaded code is ever executed. The platform never executes user-submitted Python.
9. No real trades, transfers, or loan origination — the product is decision support only.
10. Account deletion cascades; data export is JSON.

---

## 8. Why this is not a "second backend"

The prior application prototype exposed a *single-goal* LP with no state. This platform exposes the
*multi-goal, capacity-constrained* LP, the trained RL policy, a genuine hybrid, forecasting and
persistence. The old prototype's contract is not extended; it remains a separate, untouched artefact.
The research system remains the single source of model truth and is consumed read-only.
