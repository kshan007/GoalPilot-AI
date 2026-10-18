# Financial Assumptions

Every assumption the platform makes, where it comes from, and how a user can override it.
Defaults are configuration, not truth: each is surfaced in the API response that used it and is
stored with the plan.

---

## 1. Inflation

| Field | Value |
|---|---|
| Default | 3.0% per annum (`DEFAULT_ANNUAL_INFLATION`) |
| Basis | Long-run CPI-informed planning assumption, not a forecast |
| Per-goal override | Supported via the goal record; a goal-level rate wins over the profile rate |
| Applied as | `future_target = current_cost × (1 + π)^years`, compounding annually |
| Where surfaced | `recommendation.goal_recommendations[].assumptions_used.inflation`, plan assumptions |
| Caveat | Applying one rate to education, a vehicle and a holiday is a simplification; overrides exist for that reason |

## 2. Investment and savings returns

| Field | Value |
|---|---|
| Savings return default | 0% real, configurable |
| Investment return default | 5% nominal, configurable |
| Basis | A planning assumption chosen to be deliberately conservative. **Not** derived from NIFTY history |
| Why not historical mean | Using realised equity returns as an expected return would encode survivorship and period bias, and would imply a guarantee |
| Compounding | Monthly, consistent with the monthly contribution grid |
| Where surfaced | Plan assumptions, per-goal `assumptions_used` |
| Caveat | A single expected return ignores sequence risk; scenario analysis exists separately |

## 3. Lending

| Field | Value |
|---|---|
| Loan interest assumption | 11% per annum default, user-configurable |
| EMI formula | `P·r·(1+r)^n / ((1+r)^n − 1)`, `r = annual/12`, end-of-month |
| EMI-to-income ceiling | User's own `emi_income_ratio_cap` (default 35%) — a household rule, not a lender's underwriting standard |
| Scenario rate for missing categories | `GOALPILOT_SCENARIO_LOAN_RATE` (default 12%), then the user's profile assumption, then a labelled fallback |
| APR | IRR over net proceeds and the EMI stream, annualised `(1+i)^12 − 1`; includes fees entered |
| Prepayment | Not modelled automatically; stated as unknown unless the source publishes it |

## 4. The savings buffer

| Field | Value |
|---|---|
| Desired buffer | `max(monthly_savings_target, preferred_cash_buffer)` |
| Why the maximum | The target and the reserve both describe money to retain; summing them would invent an obligation |
| Mandatory flag | If set, the full buffer is protected even when it exceeds the surplus; the gap is reported |
| Emergency fund | A **stock** target of `emergency_months × essential_expenses`, default 6 months |
| Interaction | The emergency reserve is excluded from the goal cash pool, never added to the monthly buffer |
| Deficit | `desired_buffer − min(desired_buffer, max(0, surplus))` — always reported, never netted away |

Worked example: surplus 59,000; target 15,000; reserve 8,000 → buffer 15,000; goal budget 44,000.

## 5. Risk

| Field | Value |
|---|---|
| Risk capacity | 0..1, user-declared ability to bear a loss |
| Investment cap | Investment contribution limited by risk capacity; the LP cannot exceed it |
| Suitability scoring | Additive penalties for risk above capacity, short horizon, illiquidity, lock-in beyond horizon, unverified eligibility, concentration |
| What it is not | Not a regulated risk-profiling instrument, not advice |

## 6. Market and economic data

| Field | Value |
|---|---|
| NIFTY history | Descriptive only (volatility, drawdown, trailing CAGR, 2015-01 → 2026-12) |
| Live index level | Displayed as one observation; never fed into a projection |
| WALR | Historical benchmark (latest 9.27108%, 2026-03); never a product rate |
| Small-savings rates | Notified quarterly (Q3 FY2026-27 values); re-verification required each quarter |

## 7. Time and money conventions

* Money is rounded half-up to 2 decimals at the persistence boundary only; calculations keep full
  precision.
* All figures are nominal INR. No currency conversion is performed.
* A "month" is a calendar month; the planning grid starts at the current month.
* Years are computed as actual days / 365 for capitalisation, and as whole months for goal horizons.

## 8. Forecast versus actual

| Field | Value |
|---|---|
| Surplus basis | `projected` until recorded transactions exist, then `actual` |
| Reconciliation | Forecasts are preserved alongside actuals so forecast error can be measured |
| New users | Receive clearly labelled initial estimates based on entered figures and recurring obligations — never a fabricated spending pattern learned from nothing |
| Adaptation | Rolling estimates update from history; the optimiser re-solves on the new state |

## 9. Overrides and where they appear

| Assumption | Override | Surfaced in |
|---|---|---|
| Inflation | Profile, per goal | Plan assumptions, per-goal block |
| Returns | Profile | Plan assumptions |
| Loan rate | Profile, per request (`scenario_rate`) | Loan response `assumption_source` |
| Buffer | Profile (`monthly_savings_target`, `preferred_cash_buffer`, mandatory flag) | `protected_buffer` block |
| EMI ceiling | Profile | `cash_flow_status.emi_income_ratio_cap` |
| Emergency months | Profile | `protected_buffer.minimum_cash_reserve_rule` |
