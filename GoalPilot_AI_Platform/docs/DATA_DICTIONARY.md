# GoalPilot AI Platform — Data Dictionary

**Date:** 2026-10-14

Two data domains exist and are kept strictly separate:

* **User data** — created by an authenticated user. Private, ownership-scoped, stored in the
  platform database.
* **Research data** — read-only research artefacts. Used for benchmarks, the shared market path
  and recorded evaluation results. Never written to, never mixed with user rows.

---

## 1. Conventions

| Convention | Rule |
|---|---|
| Money | `NUMERIC(18,2)`, rounded half-up to 2 decimals at the persistence boundary only. Internal arithmetic is float64 so model behaviour matches the research implementation exactly. |
| Rates | `NUMERIC(9,6)` as a decimal fraction (0.03 = 3 %). |
| Periods | `VARCHAR(7)` in `YYYY-MM`. |
| Timestamps | `TIMESTAMP WITH TIME ZONE`, stored UTC. |
| Ownership | Every user-owned table has `user_id` → `users.id` with `ON DELETE CASCADE`. Queries always add `user_id = <authenticated user>`. A mismatch returns **404**, never 403. |
| Deletion | Cascades from `users`. `assets.earmarked_goal_id` and `transactions.goal_id` use `SET NULL` so a deleted goal cannot orphan a row. |

### Provenance labels

Every value shown anywhere in the app is one of:

| Label | Meaning |
|---|---|
| **actual** | recorded by the user as a real transaction |
| **estimated** | produced by the forecast component; the method and version are stored alongside |
| **projected** | produced by the planner using the stated, editable assumptions |
| **historical** | observed data (NIFTY 50, RBI series, HCES) used for calibration only |
| **synthetic** | generated research data, labelled wherever it appears |

---

## 2. Tables

### 2.1 `users`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `email` | VARCHAR(320) UNIQUE | stored lowercased; looked up case-insensitively |
| `password_hash` | VARCHAR(255) | bcrypt. **Never** returned by any endpoint |
| `full_name` | VARCHAR(160) | |
| `is_active` | BOOLEAN | |
| `last_login_at` | TIMESTAMPTZ | |
| `token_version` | INTEGER | bumped on logout / password change / reset; invalidates all JWTs for the account |

### 2.2 `password_reset_tokens`
`token_hash` (SHA-256, UNIQUE), `user_id`, `expires_at`, `used_at`. The raw token is never
stored. A used or expired token is rejected.

### 2.3 `user_preferences`
`currency`, `locale`, `risk_tolerance`, `loss_ability`, `liquidity_requirement`,
`onboarding_step`, `onboarding_completed`, `assumptions_json` (free-form user overrides).

> `risk_tolerance` (appetite) and `loss_ability` (capacity) are **separate columns on purpose**.
> Neither is ever derived from the other.

### 2.4 `financial_profiles`
| Column | Meaning |
|---|---|
| `monthly_income` | convenience aggregate; the income sources are the source of truth and are kept in step |
| `essential_expenses`, `discretionary_expenses` | the user's **stated** monthly figures |
| `monthly_savings_target` | *desired* savings — explicitly not the same thing as available surplus |
| `savings_target_is_mandatory` | mandatory vs aspirational |
| `preferred_cash_buffer`, `willing_to_adjust_discretionary` | |
| `emergency_months` | emergency-fund guideline, in months of essential expenses |
| `emi_income_ratio_cap`, `risk_capacity` | planning parameters |
| `inflation_assumption`, `investment_return_assumption`, `savings_return_assumption`, `loan_interest_assumption` | editable assumptions, defaults 3 % / 5 % / 0 % / 12 % |

### 2.5 `income_sources`
| Column | Notes |
|---|---|
| `source_type` | salary, freelance, business, rental, other |
| `amount` | the amount **as stated in `frequency`** |
| `frequency` | monthly, annual, quarterly, weekly, one_time |
| `monthly_equivalent` | normalised: ×1, ÷12, ÷3, ×(52/12), ×0 |

The original frequency is always retained. `one_time` normalises to 0 for planning and is
excluded from recurring income.

### 2.6 `assets`
`asset_type` (liquid_savings, emergency_savings, investment, fixed_deposit, other),
`current_value`, `is_liquid`, `usable_for_goals`, `annual_return`, `risk_score`,
`earmarked_goal_id`.

> Total assets ≠ available cash. Only rows with `is_liquid` **and** `usable_for_goals` enter the
> goal-funding pool.

### 2.7 `liabilities`
`liability_type`, `outstanding_principal`, `annual_interest_rate`, `emi_amount`,
`remaining_tenure_months`.

> **The monthly obligation is the EMI.** It already contains principal *and* interest. The
> outstanding principal is a balance-sheet figure and is never added to it. Adding both is the
> double-count the research audit flagged (finding F-06/B-1).
>
> Derived for display only: `total_repayment_if_held_to_tenure = emi × remaining_tenure`,
> `total_interest_if_held_to_tenure = max(0, total_repayment − principal)`.

### 2.8 `goals`
`name`, `purpose`, `goal_type`, `current_cost`, `target_date`, `current_funded_amount`,
`priority` (1–5), `criticality` (1–5), `date_flexible`, `amount_flexible`,
`liquidity_requirement`, `risk_constraint`, `status` (active, paused, completed, archived).

### 2.9 `goal_contributions`
`goal_id`, `amount`, `contribution_date`, `source`, `note`. Recording a contribution **adds** to
`goals.current_funded_amount`; it never substitutes for it.

### 2.10 `monthly_records`
One row per user per period (`UNIQUE (user_id, period)`). `status` ∈ open | estimated |
reconciled. Totals: `total_income_expected`, `total_income_actual`, `total_expense_estimated`,
`total_expense_actual`, `surplus_projected`, `surplus_actual`, `reconciled_at`.

### 2.11 `transactions`
| Column | Notes |
|---|---|
| `kind` | income or expense |
| `category` | one of the 14 defaults, or a custom category |
| `classification` | essential, discretionary, income — defaulted from the category, overridable |
| `status` | **estimated** or **actual** (the provenance label) |
| `is_recurring` | drives month seeding |
| `goal_id` | optional link |
| `client_ref` | idempotency key; a repeat submission returns the existing row |

Default categories: `housing, food_groceries, utilities, transport, education, healthcare,
insurance, family, loan_payments, shopping, entertainment, travel, subscriptions, other`.

Essential by default: housing, food_groceries, utilities, transport, education, healthcare,
insurance, family, loan_payments. Everything else defaults to discretionary.

### 2.12 `budgets`
`category` (UNIQUE per user), `monthly_limit`, `classification`, `is_active`.

### 2.13 `expense_forecasts`
**Immutable once committed.** `period`, `category`, `forecast_amount`, `method`, `method_version`,
`input_cutoff`, `history_months_used`, `is_provisional`, `data_quality`
(provisional | low | fair | good). Unique on `(month_id, category, method_version)`.

### 2.14 `forecast_evaluations`
`forecast_id`, `period`, `category`, `forecast_amount`, `actual_amount`, `abs_error`,
`pct_error`. Created at reconciliation **next to** the forecast.

> A category with a forecast and **no recorded actual** gets no evaluation row and is reported as
> `actual_recorded: false` / `unmatched`. Reporting it as a 100 % miss would be a false statement
> about the forecast.

### 2.15 `optimization_runs`
`kind` (plan | compare), `algorithm`, `status`, `feasible`, `assumptions_json`,
`input_snapshot_json`, `result_json`, `objective_value`, `weighted_achievement`,
`total_shortfall`, `runtime_ms`, `model_version`, `config_version`, `warnings_json`.

Append-only: a run is never updated. The plan response carries a `diff` against the previous run.

### 2.16 `goal_allocations`
One row per goal per run: `goal_ref` (`G<db id>`), `goal_id`, `goal_name`, `funding_gap`,
`initial_savings_allocated`, `existing_assets_allocated`, `monthly_savings_contribution`,
`monthly_investment_contribution`, `loan_principal`, `estimated_loan_emi`,
`estimated_loan_interest_cost`, `projected_new_funding`, `shortfall`, `achievement_ratio`.

### 2.17 `scenarios` / `scenario_runs`
`scenarios`: `name`, `preset`, `parameters_json`.
`scenario_runs`: `baseline_run_id`, `stressed_run_id`, `result_json`, `deltas_json`.

### 2.18 `model_versions`
Registry mirror: `name`, `version`, `kind` (lp | rl | hybrid | forecast), `status`,
`artifact_path`, `metadata_json`, `evaluated_at`. Unique on `(name, version)`.

### 2.19 `audit_events`
`user_id`, `event_type`, `detail_json`, `ip`, `created_at`. Events: register, login,
login_failed, logout, reset_requested, reset_requested_unknown_email, password_reset,
password_changed, data_export.

---

## 3. Computed fields (never stored; always derived)

| Field | Definition |
|---|---|
| `monthly_equivalent` | `amount × {monthly:1, quarterly:1/3, annual:1/12, weekly:52/12, one_time:0}` |
| `existing_emi` | `Σ liability.emi_amount` |
| `essential_expenses` | `Σ` essential expense lines (with `loan_payments` excluded — see below) |
| `monthly_surplus` | `income − essential − discretionary − existing_emi` (may be negative) |
| `emergency_fund_target` | `emergency_months × essential_expenses` |
| `emergency_fund_gap` | `max(0, target − liquid_savings)` |
| `emergency_fund_progress` | `min(1, liquid_savings / target)`, or 1 when the target is 0 |
| `emi_income_ratio` | `existing_emi / income`; compared to `emi_income_ratio_cap` |
| `earmarked_goal_funding` | `Σ active goal.current_funded_amount` |
| `available_cash_for_goals` | `max(0, liquid_assets − emergency_fund_target − earmarked_goal_funding)` |
| `savings_target_attainment` | `min(1, max(0, surplus) / savings_target)` |
| `future_target` | `current_cost × (1 + inflation)^(months/12)` |
| `remaining_gap` | `max(0, future_target − existing_funding)` |
| `required_monthly_contribution` | `remaining_gap / months_remaining` |
| `goal_priority_score` | `clip(priority,1,5) × clip(criticality,1,5) × (1 + min(12/m, 2)) / 2` |
| `achievement_ratio` | `min(1, projected_new_funding / funding_gap)`, or 1 when the gap is 0 |
| `weighted_goal_achievement` | `Σ(achievement_ratio × goal_priority_score) / Σ goal_priority_score` |
| `investment_capacity_ratio` | `min(risk_capacity × liquidity_factor, loss_ability_ceiling)` — derivation always disclosed |
| `situation_tier` | see below |

### `situation_tier` rules (a transparent label, not a credit score)

| Tier | Condition |
|---|---|
| `deficit` | `monthly_surplus ≤ 0` |
| `debt_stressed` | `emi_income_ratio > emi_income_ratio_cap` |
| `thin_buffer` | `emergency_fund_progress < 0.5` |
| `strong` | surplus ratio ≥ 0.30 **and** emergency progress ≥ 1.0 |
| `moderate_saving` | surplus ratio ≥ 0.15 |
| `thin_surplus` | otherwise |

### The `loan_payments` exclusion

When expenses are taken from month transactions, rows in the `loan_payments` category are
**skipped**: the EMI obligation is already present as `existing_emi`. The skip count is returned
as `loan_payment_lines_skipped` and warned about. Without this rule the same loan payment would
be charged twice.

---

## 4. Research data (read-only, never modified)

| Artefact | Location | Rows | Used for | Caveat |
|---|---|---:|---|---|
| Monthly market/credit path | `simulation/05_simulation_runs/rl_prototype/rl_market_credit_validated.csv` | 142 | the shared monthly path for every arm | historical observations (2015-03 →), **not** a guaranteed forward return |
| Benchmark population | `…/rl_sample_financial_profiles.csv` | 100 × 38 | benchmarks page, RL environment | synthetic |
| Benchmark goals | `…/rl_sample_goals.csv` | 390 × 12 | RL environment | synthetic |
| Train/test split | `…/rl_train_test_user_split.csv` | 100 × 2 | labelling benchmark rows | |
| Multi-goal population | `GoalPilot_MultiGoal_Extension/data/multigoal_financial_profiles.csv` | **10,000 × 38** | population statistics | synthetic |
| Multi-goal inputs | `…/synthetic_multigoal_input.csv` | **39,932 × 12** | goal statistics | synthetic |
| PPO checkpoints | `training_logs/experiments/**/*.zip` | 28 files | the RL arm | each valid only under its training config |
| Recorded evaluation | `outputs/evaluation/final_validation_v8/*` | | reported as research results | never re-derived by the app |

The application **never loads the full research dataset at runtime**. It reads the single
142-row market path and the checkpoint; population CSVs are touched only by the benchmark
endpoint, which is capped and paged.

### Schema note on the multi-goal inputs

`multigoal_financial_profiles.csv` and `final_optimisation_input.csv` share the **same 38-column
household schema**. Neither contains goal rows. Goal-level data lives only in
`synthetic_multigoal_input.csv`, joined on `user_id`. Feeding the household file into a
multi-goal solver without that join is a modelling error, and the platform never does it.

---

## 5. Data-quality and missing-value rules

| Situation | Rule |
|---|---|
| No expense history | cold start; every forecast is `is_provisional=true` with `data_quality="provisional"`, sourced from declared obligations and user estimates only. Zero is assumed for a category with neither, stated explicitly. |
| No actual expense for a category in a month | excluded from reconciliation totals and marked `actual_recorded: false`; **never** treated as a 100 % error |
| No income source | planning is refused with an actionable message rather than assuming income |
| No financial profile | planning is refused |
| Non-liquid assets | counted in `total_assets`, excluded from `liquid_savings` and the funding pool |
| Negative surplus | returned as a deficit and flagged; never clamped to zero |
| Rate/return inputs | validated to be finite and `> −100 %`; a weight/ratio must be in `[0,1]` |
| Rounding | half-up to 2 decimals on write; display always 2 decimals with thousands separators |

## 6. Versioning

| Artefact | Version string |
|---|---|
| Capacity-constrained LP | `constrained_lp@research-2026-10-11` |
| Unconstrained research LP | `multi_goal_lp@research-2026-10-10` |
| PPO policy | `ppo_recommended_v1@recommended` |
| Hybrid | `hybrid_rl_theta_lp@v1` |
| Forecaster | `forecast_v1` |
| Selector | `selector@v1` |
| Database schema | Alembic revision `903315a72db4` |

Every optimisation run stores its `model_version` and `config_version`, so any historical plan
can be traced to the exact model, configuration and assumptions that produced it.
