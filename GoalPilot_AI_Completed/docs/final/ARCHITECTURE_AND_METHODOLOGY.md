# GoalPilot AI — architecture, data flow, simulation, LP and RL methodology

**Date:** 2026-10-11 · **Project:** `S:\fyp\GoalPilot_AI_Completed`
Companion diagram: [`architecture.svg`](architecture.svg)

---

## 1. Architecture

Seven layers. Each maps to real files; the traceability matrix in
`docs/REQUIREMENTS_TRACEABILITY.md` links requirements to evidence.

| layer | directory | role |
|---|---|---|
| 1 Data | `simulation/01_input_data`, `optimization/lp_inputs` | HCES, CPI, WALR, NIFTY, and the LP audit inputs (preserved, read-only) |
| 2 Simulation | `simulation/02…07` | synthetic population, financial profiles, economic environment, monthly runs, validation |
| 3 Optimisation | `GoalPilot_MultiGoal_Extension/src`, `…/rl_prototype/goalpilot_constrained_lp.py` | static multi-goal LP; capacity-constrained benchmark |
| 4 RL environment | `simulation/05_simulation_runs/rl_prototype/` | Gymnasium environment, config, LP encoder |
| 5 Decision policy | same + `training_logs/` | PPO checkpoints and rule baselines |
| 6 Evaluation & explanation | `evaluation/`, `audit_tools/`, `goalpilot_explain.py` | fair comparison, diagnostics, grounded explanations |
| 7 Application | `S:\fyp\GoalPilot_Application` | FastAPI single-goal LP + React UI |

**Design rules enforced across the project**

- The archived environment is preserved byte-identically
  (`archive/goalpilot_env_archived_20261010.py`, SHA-256 `FDFE6D9D…4A9FEFD`) and every change is
  an **opt-in preset**, so no published result is silently altered.
- Every generated artefact carries the configuration that produced it.
- Archived result CSVs are never overwritten; new work goes to versioned folders
  (`final_validation_v1…v8`, `reward_design/v1…v8`).

## 2. Data and preprocessing flow

```
HCES 2023–24 expenditure ──► household_profiles.csv ──► household_scaled.csv
RBI CPI ───────────────────► cpi_historical_calibration.csv ──► cpi_scaled.csv
RBI WALR ──────────────────► walr_scaled.csv ────────────────► market_scaled.csv
NIFTY 50 daily ────────────► monthly returns (142 months) ───┘
                                          │
                    ┌─────────────────────┴──────────────────────┐
                    ▼                                            ▼
     synthetic_population_* (base, income, debt,        rl_sample_financial_profiles.csv
     investment, risk, savings)                          rl_sample_goals.csv (390 goals)
                    │                                     rl_market_credit_validated.csv
                    ▼                                     rl_train_test_user_split.csv
     monthly_financial_simulation_base.csv  ◄── 1,430,000 rows × 10,000 users (validated)
```

**Conventions that matter**

| point | rule |
|---|---|
| HCES | a *population expenditure benchmark*, not an individual's salary |
| NIFTY | historical observation, not a promised return |
| WALR forward-fill | never introduces future information; validated by the NIFTY/WALR reconstruction audit |
| CPI | applied consistently; inflated goal targets use `(1 + 0.03)^(months/12)` |
| nominal vs real | never mixed in one comparison; `target_basis` makes the choice explicit |
| `monthly_surplus` in the population CSV | equals `income − expenditure`; **EMI is separate** (finding B-1) |

## 3. Financial simulation methodology

The RL environment (`goalpilot_env.GoalPilotEnv`) is a monthly, finite-horizon
(142-month) simulator over a user's goals.

**Per month, in order:** income and expenditure are inflation-adjusted → existing EMI is
reserved → a discretionary budget is formed → the action allocates savings / investment / loan
demand to goals → the investment ceiling is applied and its overflow handled by the configured
policy → per-goal caps are enforced → the portfolio is marked to the realised NIFTY monthly
return → loan interest and EMI are serviced → goal balances are credited under the configured
`goal_credit_mode` → rewards are computed → net worth is updated.

**Accounting modes**

- `legacy` (archived): contributions sit in `cash` *and* in `goal_balances` (double count, F-04);
  loan proceeds are credited to goals with no liability settlement (F-05).
- `ledger` (default): each rupee is counted exactly once; the emergency reserve is restricted
  cash inside the balance sheet (R-02); loan proceeds credit cash then transfer to the goal;
  every EMI payment debits cash; a residual principal is settled or carried, never silently
  written off (R-01).

**Invariants asserted** every month: `savings + investment + unallocated − discretionary_budget
= 0` (`budget_check`), non-negative allocations, goal caps respected, affordability respected,
and `earmarked_goal_funding ≤ cash + portfolio`.

## 4. LP optimisation

### 4.1 The historical base LP (`optimization/lp_inputs/lp_5r_formal_lp_specification.csv`)

```
minimise   Σ_u D_u
s.t.       G_(u,t) ≥ 0                        (goal funding)
           G_(u,t) ≤ PositiveCashFlow_(u,t)   (monthly budget)
           Σ_t G_(u,t) + D_u = Target_u       (target accounting)
           D_u ≥ 0                            (shortfall slack)
```

Recorded dimensions: 10,000 users, 626,970 `G` variables, 10,000 `D` variables, 636,970 total
variables, 1,273,940 constraints; 7,582 feasible / 2,418 infeasible users in the historical run.

**Explicitly NOT in the base LP** (recorded as `UNSUPPORTED` in the formal spec): monthly
investment allocation, borrowing / WALR, future NIFTY returns, and a minimum reserve. Anything
of that kind added later is an **assumption**, not established financial truth.

### 4.2 The extended multi-goal model (`multi_goal_optimizer.py`, unchanged)

Per goal `j`, six variables `cash0_j, asset0_j, save_j, invest_j, loan_j, short_j`,
bounds `short_j ∈ [0, gap_j]`. Constraints: per-goal funding-gap equality (which with the
shortfall bound also enforces the goal cap), a shared cash pool net of the emergency reserve
(`emergency_months × essential_expenses`), a usable-existing-assets pool, an EMI cap
(`emi_income_ratio_cap`), and the combined-affordability constraint.

### 4.3 The capacity-constrained benchmark (`goalpilot_constrained_lp.py`, v7)

Adds, each independently switchable:

```
(a)  Σ_j invest_j − capacity_ratio · Σ_j loan_j · emi_factor  ≤  capacity_ratio · monthly_surplus
(b)  Σ_j loan_j  ≤  max_new_loan          (= 150,000, the environment's cap)
```

With both switches off the module is **exactly** the original model (asserted to rtol 1e-9 on
the objective, colour-weighted achievement, total shortfall and every allocation column).

Because every goal equality contains `short_j` with bounds `[0, gap_j]`, the model always has a
feasible slack solution: solver *infeasibility cannot arise from the modelling*. Any gap between
the LP's plan and the environment's execution is therefore an **execution** difference.

## 5. RL environment and learning methodology

### 5.1 Observation — 42-dim, normalised, clipped to [0, 1]

12 global features: income, expenditure, EMI, surplus, cash, portfolio, loan balance, capacity
ratio, risk score, month progress, `walr_monthly`, `nifty_monthly_return`. Then **6 features per
goal slot × 5 slots** = 30: remaining need, horizon, priority, criticality, balance/target
ratio, and a validity flag (zero-padded when a user has fewer than five goals).

Only information available at the decision date is exposed — no future return, no future goal
requirement, no simulator outcome.

### 5.2 Action — `Box(5, 3)`

Per goal slot: a savings weight, an investment weight, and a loan flag.

| `action_mode` | semantics |
|---|---|
| `magnitude` (archived) | weights are absolute fractions of the available budget; a policy emitting < the saturation point under-funds goals and the reward is flat above it (F-02) |
| `share` | the vector is normalised to shares, so the whole budget is always allocated — removes the structural handicap against PPO |
| `mix` | as `share`, but investment demand above capacity stays **unallocated** instead of being relabelled as savings, so the requested mix is observable (R-12) |

Overflow policy: `legacy` (default; `share` returns excess to savings, `mix` leaves it idle),
`retain_as_cash`, `redirect_to_savings`.

### 5.3 Goal crediting

`face_value` (archived): a rupee contributed is a rupee of funding, so the savings/investment mix
cannot matter (F-01). `growth_weighted`: contributions compound, matching the LP valuation, but
books a *projection* as realised funding (R-03). `market_weighted` (recommended): a new
contribution is credited at face value and existing earmarks are marked to the *realised* NIFTY
return — a projected return is never booked, so `Σ goal_balances ≤ cash + portfolio` always
holds.

### 5.4 Reward versions

| version | status |
|---|---|
| `archived_v1` | the historical reward, byte-for-byte; **never modified** |
| `candidate_a` | goal-completion centric: ratio-normalised progress, graduated shortfall over a 12-month window, interest-proportional debt penalty, downside-only risk charge, single terminal net-worth credit |
| `candidate_b` | realised-wealth centric: one monthly wealth-delta term, same graduated shortfall, terminal achievement credit |

Candidate coefficients are **design choices, not fitted optima**.

### 5.5 Training

PPO (stable-baselines3, `MlpPolicy`, `n_steps=256`, `batch_size=64`, `n_epochs=4`, `gamma=0.99`,
`lr=3e-4`, `net_arch=[128,128]`), matched seeds 7/17/27. Checkpoint selection uses an
`EvalCallback` on a **validation** partition; the held-out test partition is evaluated once.
The archived 50k checkpoint's only valid preset is `GoalPilotConfig.archived()`; no checkpoint is
reinterpreted under incompatible action semantics.
