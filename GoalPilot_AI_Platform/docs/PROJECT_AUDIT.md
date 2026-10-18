# GoalPilot AI — Project Audit

**Audit date:** 2026-10-14
**Auditor:** GoalPilot AI Platform build (engineering pass)
**Scope:** everything accessible under `S:\fyp`
**Nature of this document:** every factual claim is traceable to a named file, an executed
command, or an explicit "not verified" marker. Nothing here is assumed.

---

## 1. What actually exists

The repository contains **three distinct layers**, not one project. Conflating them is the single
most common error in previous passes, so they are separated first.

| Layer | Location | What it is | State |
|---|---|---|---|
| **A. Research / model system** | `GoalPilot_AI_Completed\` | Audited, tested LP + RL + evaluation harness | Genuinely complete and validated |
| **B. Research originals (untouched)** | `GoalPilot_AI\`, `GoalPilot_AI_old\`, root notebooks/CSVs | Pre-audit artefacts kept byte-exact | Reference only |
| **C. Web application** | `GoalPilot_Application\` | Small FastAPI + Vite/React prototype | Works, but single-goal LP, **no DB, no auth** |

Layer C is **not** a base for the requested platform in its current form: it has no database, no
authentication, no persistence, no multi-goal planning and no RL inference. Its own health payload
declares `multi_goal_optimization: false` and `reinforcement_learning: false`
(`GoalPilot_AI_Completed\docs\APPLICATION.md` §2.2), which is accurate.

Neither layer is discarded. Layer A is **reused as the model source of truth**; the new platform is
built around it (see `ARCHITECTURE.md`).

---

## 2. Verified inventory

### 2.1 Datasets (verified by reading the files, not by reading documentation)

| File | Rows × Cols | Verified facts |
|---|---:|---|
| `GoalPilot_MultiGoal_Extension\data\multigoal_financial_profiles.csv` | **10,000 × 38** | one row per synthetic household |
| `GoalPilot_MultiGoal_Extension\data\synthetic_multigoal_input.csv` | **39,932 × 12** | one row per synthetic goal; mean 3.99 goals/user |
| `GoalPilot_MultiGoal_Extension\data\final_optimisation_input.csv` | **10,000 × 38** | **same 38-column schema as the profiles file** |
| `simulation\05_simulation_runs\rl_prototype\rl_sample_financial_profiles.csv` | 100 × 38 | RL sample population |
| `simulation\05_simulation_runs\rl_prototype\rl_sample_goals.csv` | 390 × 12 | RL sample goals (3–5 per user) |
| `simulation\05_simulation_runs\rl_prototype\rl_market_credit_validated.csv` | 142 × 20 | monthly NIFTY + WALR path, **2015-03 onward** |
| `simulation\05_simulation_runs\rl_prototype\rl_train_test_user_split.csv` | 100 × 2 | original 80/20 split |
| `simulation\04_economic_environment\economic_environment.csv` | present | macro environment |
| `simulation\05_simulation_runs\monthly_financial_simulation_base.csv` | present | monthly simulation |
| `simulation\05_simulation_runs\portfolio_simulation_validated.csv` | present | portfolio simulation |
| `simulation\06_results\final_goal_outcome_dataset.csv` | present | goal outcomes |
| `datasets\GoalPilot_AI\**` | 10 files | feature extractions + scaled simulation inputs (household_scaled.csv ≈ 106 MB) |

**The ~10,000 / ~39,932 counts in the brief are confirmed.** They are real, not documentation claims.

**Critical schema finding (confirmed).** The brief warned not to assume `final_optimisation_input.csv`
suits multi-goal optimisation. The audit confirms the warning is correct in a *different* way than
expected: `final_optimisation_input.csv` and `multigoal_financial_profiles.csv` are the **same
38-column household-level schema** — neither contains goal rows. Goal-level data lives *only* in
`…_goals.csv` / `synthetic_multigoal_input.csv`, joined on `user_id`. Any implementation that feeds
`final_optimisation_input.csv` into a multi-goal solver without the goals join is wrong.

### 2.2 Models

| Artefact | File | Verified facts |
|---|---|---|
| Multi-goal LP | `GoalPilot_MultiGoal_Extension\src\multi_goal_optimizer.py` (297 lines) | `scipy.optimize.linprog(method="highs")`; 6 variables per goal |
| Capacity-constrained LP | `simulation\05_simulation_runs\rl_prototype\goalpilot_constrained_lp.py` (299 lines) | rebuilds the same model + 2 extra constraints |
| Funding-option providers | `GoalPilot_MultiGoal_Extension\src\providers.py` | `EconomicScenario`, `LoanOffer`, `SavingsProduct`, `InvestmentCandidate` |
| Shared config | `…\rl_prototype\goalpilot_config.py` (321 lines) | `GoalPilotConfig` + 7 named presets |
| RL environment | `…\rl_prototype\goalpilot_env.py` (58,050 bytes) | Gymnasium env, `GoalPilotEnv` |
| LP encoder | `…\rl_prototype\goalpilot_lp_encoder.py` | encodes an LP plan into the RL action contract |
| Explainability | `…\rl_prototype\goalpilot_explain.py`, `goalpilot_knowledge.py` | grounded explanation layer |
| **Trained policies** | `training_logs\experiments\**\*.zip` | **30 PPO checkpoints** across 4 experiment families |
| Archived environment | `archive\goalpilot_env_archived_20261010.py` | pre-audit env, SHA-256 recorded |

**PPO checkpoints verified present** (not merely claimed):

- `ppo_recommended_v1\{archived_v1,candidate_a}\seed{7,17,27}\best\best_model.zip` — 6 checkpoints,
  the v8 trained policies, 50,000 timesteps each, checkpoint-selected on the 16 **validation** users.
- `fresh_split_v1\{archived_v1,candidate_a}\ppo_*_seed{7,17,27}.zip` — 6 more.
- `reward_experiment_v1\{archived_v1,candidate_a,candidate_b}\ppo_*_seed{7,17,27}.zip` — 9 more.
- `smoke\ppo_smoke.zip` — 1 smoke checkpoint.
- Each run also carries `run_*.json`, `monitor_*.monitor.csv`, `training_episodes_*.csv`.

### 2.3 Tests (already executed on this host — counts are from the recorded runs)

| Suite | Location | Recorded result |
|---|---|---|
| RL environment | `GoalPilot_AI_Completed\tests\` (15 files) | **174 passed in 599.33s** |
| LP optimizer | `GoalPilot_MultiGoal_Extension\tests\` (3 files) | **26 passed in 1.94s** |
| Application (old) | `GoalPilot_Application\backend\tests\` (3 files) | 15 passed in 71.24s |
| **Total research** | | **200 tests, 0 failures, 0 errors, 0 skips** |

The strongest single artefact is `tests\test_goalpilot_env_parity.py`: 100 users × 5 policies × 142
months, rolled out twice, every reward compared to **1e-12**. That is a real regression guarantee.

---

## 3. Mathematical formulations found

### 3.1 LP — single-goal (legacy, root notebooks)

Discrete monthly LP over a horizon up to 144 months, minimising goal shortfall subject to monthly
cash-flow availability. Assumptions audited: **inflation 3 %, investment return 5 %, loan interest
12 %**. These are **assumptions, not facts** — they are user-supplied parameters with those defaults
(`multi_goal_optimizer.optimize_multi_goal` keyword defaults: `annual_inflation=0.03`,
`investment_return=0.05`, `loan_annual_rate=0.12`). They are treated as auditable parameters, not
universal constants.

### 3.2 LP — multi-goal (the reusable model)

Variables, **6 per goal** `j`:

| Index | Variable | Meaning | Units |
|---|---|---|---|
| `6j+0` | `cash_j` | initial savings allocated to goal `j` | ₹ (present value) |
| `6j+1` | `asset_j` | existing investments allocated to goal `j` | ₹ (present value) |
| `6j+2` | `save_j` | monthly savings contribution to goal `j` | ₹/month |
| `6j+3` | `invest_j` | monthly investment contribution to goal `j` | ₹/month |
| `6j+4` | `loan_j` | loan principal drawn for goal `j` | ₹ |
| `6j+5` | `short_j` | unfunded remainder of goal `j` | ₹ |

Objective (minimise):

```
Σ_j [ w_j · shortfall_penalty   · short_j          # primary, priority-weighted
    + loan_cost_penalty  · r_loan · (tenure/12) · loan_j
    + (0.001 + risk_penalty · ρ_invest) · invest_j
    + (0.001 + risk_penalty · ρ_asset)  · asset_j
    + 0.001 · save_j ]
```

where `w_j = goal_priority_score_j / Σ_k goal_priority_score_k`.

Per-goal equality (goal accounting, gap closed exactly):

```
cash_j + asset_j·A_j + save_j·SF_j + invest_j·IF_j + loan_j + short_j = funding_gap_j
```

with `A_j=(1+r_asset)^(m_j/12)`, `SF_j = FV factor of ₹1/month at r_savings`,
`IF_j = FV factor of ₹1/month at r_invest`.

Four shared-pool inequalities (the anti-double-counting core):

```
Σ_j cash_j                              ≤ max(0, liquid_savings − emergency_months·essential − Σ_j existing_funding_j)
Σ_j asset_j                             ≤ usable_existing_investments
Σ_j (save_j + invest_j)                 ≤ monthly_surplus
Σ_j loan_j · emi_factor                 ≤ max(0, income·emi_income_ratio_cap − existing_emi)
Σ_j (save_j + invest_j + loan_j·emi_factor) ≤ monthly_surplus      # combined affordability
```

`monthly_surplus = max(0, income − essential − discretionary − existing_emi)`.

The `existing_funding` subtraction from the cash pool is the **explicit double-counting guard**:
money already earmarked to a goal is removed before the shared pool is computed.

### 3.3 LP — capacity-constrained variant (target of the app integration)

Two constraints added, mirroring the RL environment's real executability limits:

```
Σ_j invest_j                  ≤ investment_capacity_ratio · max(0, monthly_surplus − Σ_j loan_j·emi_factor)
Σ_j loan_j                    ≤ max_new_loan
```

With both switches off this module reproduces `optimize_multi_goal` **exactly** (asserted to rtol
1e-9 by `tests\test_goalpilot_constrained_lp.py`). This is the honest LP and it is the one the
platform exposes as the LP arm.

### 3.4 RL — environment

Gymnasium `Env`. Action space is per-goal-slot, `n_goal_slots` pinned to 5 for checkpoint
compatibility. Three action mappings exist and **are not interchangeable**:

| Mode | Semantics |
|---|---|
| `magnitude` | absolute fraction of available budget; never scales *up* → no gradient above saturation |
| `share` | action vector normalised to shares; full budget always allocated |
| `mix` | as `share`, but investment demand above capacity stays **unallocated** |

An RL checkpoint is only valid under the exact semantics it was trained with. The evaluation harness
asserts `action_mode == share and overflow_policy == legacy` before loading a checkpoint.

Goal-credit semantics (`face_value` / `growth_weighted` / `market_weighted`) and accounting mode
(`legacy` / `ledger`) are the other axes. `recommended()` = `share` + `ledger` +
`market_weighted` + inflated 3 % targets + 6-month reserve — and **invalidates the archived
checkpoint**.

### 3.5 Previously claimed "hybrid"

**No executable LP+RL hybrid was found anywhere in the repository.** The only prior hybrid artefact
is a *conceptual* design in the brief itself. What exists is a **comparison harness**
(`evaluation\fair_comparison_harness_v2.py` + `goalpilot_lp_encoder.py`) that encodes an LP plan
into the RL action contract so LP and RL can be scored on identical terms. That is benchmarking, not
a hybrid. This distinction is recorded as finding **F-01** below and drives the Stage-3 build.

---

## 4. Audited assumptions — where the brief's figures came from

| Brief statement | Verdict | Evidence |
|---|---|---|
| "~10,000 synthetic financial profiles" | **Confirmed** | `multigoal_financial_profiles.csv` → 10,000 rows |
| "39,932 goal records" | **Confirmed** | `synthetic_multigoal_input.csv` → 39,932 rows |
| "LP prototype uses `scipy.optimize.linprog`" | **Confirmed** | `multi_goal_optimizer.py:11,254` |
| "3 % inflation, 5 % investment returns, 12 % loan interest" | **Confirmed as defaults, not facts** | `optimize_multi_goal` keyword defaults |
| "`final_optimisation_input.csv` may not suit multi-goal" | **Confirmed** | it is household-level, 38 cols, no goals |
| "`multi_goal_optimizer.py` exists" | **Confirmed** | 297 lines, plus a `.pre_cashflow_fix.bak` |
| Named files `economic_environment.csv` … all present | **Confirmed** | see §2.1 |
| "Existing LP+RL integration" | **Refuted** | no executable hybrid exists; only a comparison harness |

---

## 5. Findings (each one is a defect or a decision the build must respect)

| ID | Finding | Consequence for this build |
|---|---|---|
| **F-01** | No executable hybrid exists; the brief's hybrid is a design sketch | Build it in Stage 3 only after LP and RL are independently testable |
| **F-02** | The web app is single-goal, stateless, no DB, no auth | Build the platform's persistence + auth from scratch; do not extend that prototype's contracts |
| **F-03** | RL does **not** beat a simple investment rule (0.4842 vs 0.5800, paired CI excludes zero) | LP stays the dependable baseline; the app must not present RL as superior |
| **F-04** | The unconstrained LP's apparent advantage is largely an accounting artefact (it plans ₹13,736.66/mo of investment of which only ₹2,023.56 is executable) | The app's LP arm must be the **capacity-constrained** one, or it must disclose the gap |
| **F-05** | The LP and RL used different goal targets (nominal vs inflated) while being compared | All arms in the app must run under one declared assumption set |
| **F-06** | `monthly_surplus` in the population CSV **excludes EMI** | Never join population rows to app calculations naively; recompute surplus explicitly |
| **F-07** | `final_optimisation_input.csv` is not a goal table | Goals are joined from the goals table on `user_id` |
| **F-08** | The archived PPO checkpoint is valid **only** under `archived()` semantics | Pin the config per checkpoint; refuse to load a mismatched pair |
| **F-09** | No reward version has been selected (fresh-split difference +0.0069, p=0.72) | Do not silently prefer `candidate_a` |
| **F-10** | `residual_carried` is asserted but never exercised by real data | Document as unexercised; do not build app logic on it |
| **F-11** | Colab execution was never run from this host | Do not claim Colab readiness; local only |
| **F-12** | The old app's `nism_guidance_notes` field asserted a NISM source with no citation in the repo | Keep NISM as a clearly-labelled educational layer; never present course rates as current |
| **F-13** | `usable_existing_investments` must be ≤ `existing_investments`; the LP asserts it | Enforce at the DB/API boundary too |
| **F-14** | Risk capacity is an explicit input, not inferred from risk appetite | Store both; never derive one from the other |
| **F-15** | Assumption defaults (3/5/12 %) are parameters, not facts | Surface them in every API response as editable assumptions |

---

## 6. What this build reuses, builds and refuses to fake

**Reused unchanged (no rewrite, no fork):**

- `multi_goal_optimizer.py` → `optimize_multi_goal`, `prepare_goals`, `FinancialState`,
  `monthly_emi_per_rupee`, `fv_monthly_contribution_factor`
- `goalpilot_constrained_lp.py` → `solve_constrained_lp`
- `goalpilot_config.py` → `GoalPilotConfig` and its presets
- `goalpilot_env.py` → `GoalPilotEnv`
- The 6 `ppo_recommended_v1` checkpoints and the `fresh_split_v1`/`reward_experiment_v1` families
- The evaluation metrics definitions in `evaluation\*` and `docs\final\EVALUATION_AND_RESULTS.md`

**Built new in this platform:**

- PostgreSQL schema, migrations, ownership enforcement, JWT auth
- Financial-profile / monthly-workflow / goal / budget persistence
- Cash-flow builder that computes surplus **explicitly** (F-06)
- Adaptive expense forecasting (does not exist anywhere in the prior work)
- LP, RL, hybrid and algorithm-selection **service** layer over the reused models
- Scenario simulation service with a shared assumption set (F-05)
- The complete frontend

**Refused:** fabricating a trained model, a hybrid that does not execute, test results, or
performance metrics. Where a model is unavailable the platform reports its true status and falls
back to the LP baseline with an explicit reason.

---

## 7. Known limitations carried forward

1. RL does not beat simple rules on goal achievement; LP is retained as the baseline (F-03).
2. The reward function's diagnosed defects (risk penalty dominance, component scaling) are **not**
   fixed — fixing them requires a retrain under a selected reward version, which no evidence selects.
3. `residual_carried` remains unexercised by real data (F-10).
4. Population CSV `monthly_surplus` excludes EMI (F-06); the platform recomputes it.
5. Group-level `investment_capacity_ratio` values are synthetic population parameters; for a real
   app user the platform derives capacity from the user's own declared preferences and discloses it.
6. Every rate used in the app is an **assumption** with a visible, editable value.
