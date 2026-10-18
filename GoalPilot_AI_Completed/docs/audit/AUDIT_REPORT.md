# GoalPilot AI — Audit Report

**Date:** 2026-10-10
**Auditor:** Accio (local, offline analysis)
**Scope:** `S:\fyp\GoalPilot_AI` (complete downloaded project) + `S:\fyp\GoalPilot_RL_PreCheck.ipynb` (standalone notebook)
**Working copy:** `S:\fyp\GoalPilot_AI_Completed` — originals untouched

> Every finding below is backed by a file + line reference or by a CSV/console artefact
> produced by a script in `audit_tools/`. Nothing in this report is asserted from
> unexecuted code. Where a claim could not be tested locally, it is marked **NOT TESTED**.

---

## 1. File inventory

### 1.1 Workspace root (`S:\fyp`)

| Entry | Files | Size | Role |
|---|---:|---:|---|
| `GoalPilot_AI/` | 192 | 1,549.68 MB | **Complete downloaded project (authoritative)** |
| `GoalPilot_AI_old/` | 161 | 1,546.08 MB | Superseded snapshot (pre-2026-10-10-v2) |
| `simulation/` | 67 | 1,326.36 MB | Stray partial download; contains a **nested** `GoalPilot_AI/` subtree |
| `datasets/` | 24 | 343.74 MB | Extracted upstream datasets + normalised simulation inputs |
| `GoalPilot_MultiGoal_Extension/` | 44 | 19.26 MB | Duplicate of the extension inside `GoalPilot_AI/` |
| `GoalPilot_RL_PreCheck.ipynb` | 1 | 1.80 MB | Standalone pre-check notebook |
| `GoalPilot_Simulation.ipynb` | 1 | 2.65 MB | Earlier simulation notebook |
| `GoalPilot_Optimization.ipynb` | 1 | 1.47 MB | Earlier LP notebook (also in `trials/`) |
| `GoalPilot_MultiGoal_Optimization_FullRun.ipynb` | 1 | 0.12 MB | LP full-run notebook |
| `GoalPilot_Application` | 50 | 0.45 MB | Application sources |
| `nifty50_data.csv`, `findata.py`, `summary of simu.txt` | 3 | 0.25 MB | Loose inputs |
| `FYP*.pptx` | 3 | 7.03 MB | Presentation decks |

**Total: 552 files, 4,800.2 MB.**

### 1.2 Project root: `GoalPilot_AI/`

```
GoalPilot_AI/
├── Copy of GoalPilot_RL_PreCheck.ipynb     1.80 MB   <- byte-identical to the standalone notebook
├── GoalPilot_MultiGoal_Extension/          LP optimizer package (src/, tests/, data/, docs/, outputs/)
├── optimization/
│   ├── final_outputs/                      4 final LP result files
│   └── lp_inputs/                          73 LP diagnostic/audit CSVs
└── simulation/
    ├── 01_input_data/                      cpi/household/market/walr scaled inputs
    ├── 02_synthetic_population/            base + income
    ├── 03_financial_profiles/              debt, investment, risk, savings
    ├── 04_economic_environment/            economic_environment.csv, rl_monthly_market_credit.csv
    ├── 05_simulation_runs/
    │   ├── monthly_financial_simulation_base.csv      959.34 MB
    │   ├── portfolio_simulation_validated.csv         169.12 MB
    │   └── rl_prototype/                              <-- RL prototype (env, model, results)
    │       ├── goalpilot_env.py                       19,163 B  <- AUTHORITATIVE ENV
    │       ├── goalpilot_env.py.pre_*.bak   (9 files)  patch history
    │       ├── models/goalpilot_ppo_50000.zip         588,536 B
    │       ├── models/best_ppo/best_model.zip         588,521 B
    │       ├── training_logs/ppo_eval/evaluations.npz
    │       ├── training_logs/tensorboard/PPO_1/
    │       ├── rl_sample_financial_profiles.csv      100 users, 38 cols
    │       ├── rl_sample_goals.csv                   390 goals, 12 cols
    │       ├── rl_market_credit_validated.csv        142 months, 20 cols
    │       ├── rl_train_test_user_split.csv          80 train / 20 test
    │       └── rl_*.csv  (policy comparison / LP diagnostics)
    ├── 06_results/                         final_goal_outcome_dataset.csv etc.
    └── 07_validation/                      validation CSVs
```

### 1.3 RL sample data facts (measured)

| Property | Value |
|---|---|
| Users | 100 (`USER_00001` … `USER_000100`) |
| Goals per user | min 3, max 5, mean 3.9 → distribution {3: 40, 4: 30, 5: 30} |
| Market months | 142 (2015-03 … ) |
| `action_space` | `Box(shape=(5, 3))` = 15 continuous dims |
| `observation_space` | `Box(shape=(42,))` |
| Train / test split | 80 / 20 users (no overlap) |
| `investment_capacity_ratio` | min 0.0000, max 0.4988, 79 distinct |

### 1.4 Redundancy (informational)

147 duplicate groups, **3,128.03 MB redundant**:

- `monthly_financial_simulation_base.csv` (959 MB) exists **3×** (`GoalPilot_AI/`, `GoalPilot_AI_old/`, `simulation/GoalPilot_AI/`)
- `household_scaled.csv` (106 MB) exists **5×**
- `portfolio_simulation_validated.csv` (169 MB) exists **3×**

`S:\fyp\simulation\GoalPilot_AI\` is a nested second copy of the project. **Not deleted** — the
task requires originals to be preserved. Flagged for the user to prune manually if desired.

---

## 2. Notebook comparison — which is authoritative?

| | `S:\fyp\GoalPilot_RL_PreCheck.ipynb` | `S:\fyp\GoalPilot_AI\Copy of GoalPilot_RL_PreCheck.ipynb` |
|---|---|---|
| Size | 1,797,185 B | 1,797,185 B |
| Cells | 144 (all code, 0 markdown) | 144 (all code, 0 markdown) |
| Cells with outputs | 142 | 142 |
| `execution_count` | 89× `None`, then 161…219 | 89× `None`, then 161…219 |
| Total source chars | 271,463 | 271,463 |
| Kernel | `python3` | `python3` |

**Result: the two notebooks are byte-for-byte identical in source and outputs.**
`identical_source = True`; the only difference is the filesystem timestamp.

**Conclusion:** there is **no version conflict** and no "latest authoritative version" to choose
between them. There is no need to overwrite either. Both are the same Colab pre-check notebook.

### 2.1 What this notebook actually is

It is **not** a clean analysis notebook. It is a *diagnostic + in-place patcher*:

- Cells 0–88: `execution_count = None` — reconnaissance and **source-code patching**. Several
  cells read `goalpilot_env.py`, write a `.bak` backup, and rewrite the file in place
  (cells 60–88). This is the origin of the ten `goalpilot_env.py.pre_*.bak` files.
- Cells 89–143: `execution_count = 161…219` — executed diagnostics, LP-vs-RL comparison,
  training, and evaluation.

### 2.2 Patch history reconstructed from backup sizes

| # | Backup `goalpilot_env.py.pre_*.bak` | Size (B) |
|---:|---|---:|
| 1 | `pre_budget_debug` | 13,276 |
| 2 | `pre_loan_fix` | 13,840 |
| 3 | `pre_final_payment_fix` | 14,844 |
| 4 | `pre_cashflow_guard` | 15,224 |
| 5 | `pre_earmark_reconciliation` | 16,354 |
| 6 | `pre_incremental_reward` | 17,032 |
| 7 | `pre_correct_budget_guard` | 17,083 |
| 8 | `pre_goal_cap` | 17,204 |
| 9 | `pre_loan_goal_assignment` | 17,924 |
| — | **current `goalpilot_env.py`** | **19,163** |

All ten files share one `mtime` (download time), so ordering is inferred from the size monotonicity
and from the notebook's own narrative. The final two cells (142, 143) confirm the last fix:
cell 143's comment is *"Correct: combined commitment already includes contributions."*

---

## 3. Environment and capability check (measured)

### 3.1 Two Python installations exist — this matters

| | Interpreter | State |
|---|---|---|
| **A** | `…\Accio\pre-install\bd5ff2c6816a\python\python.exe` (3.12.2) | **Empty.** No numpy/pandas/torch. This is what bare `python` resolves to. |
| **B** | `C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe` (3.13.7) | **Populated.** This is what `pip` resolves to. |

**All project work must use interpreter B.** The project's own `__pycache__` contains both
`cpython-312` and `cpython-313` bytecode, i.e. it has previously been run under both.

### 3.2 Interpreter B — installed packages

| Package | Version | | Package | Version |
|---|---|---|---|---|
| numpy | 2.2.3 | | torch | 2.8.0**+cpu** |
| pandas | 2.3.1 | | tensorboard | 2.20.0 |
| scipy | 1.16.0 | | PyYAML | 6.0.2 |
| scikit-learn | 1.7.2 | | tqdm | 4.67.1 |
| statsmodels | 0.14.6 | | pytest | 9.1.1 |
| matplotlib | 3.10.3 | | nbformat / nbconvert | 5.10.4 / 7.17.1 |
| seaborn | 0.13.2 | | jupyter_client / ipykernel | 8.8.0 / 7.2.0 |
| plotly | 6.2.0 | | psutil | 7.0.0 |

### 3.3 Packages that were **missing** and were installed during this audit

| Package | Installed version | Needed by |
|---|---|---|
| `gymnasium` | 1.4.0 | `goalpilot_env.py` |
| `stable_baselines3` | 2.9.0 | PPO training / loading checkpoints |
| `sb3_contrib` | 2.9.0 | (companion; not directly imported) |
| `pulp` | 4.0.0 | not required — LP uses `scipy.optimize.linprog(method="highs")` |

`cvxpy` / `pyomo` remain absent — **not required** by this project.

### 3.4 Hardware

| Resource | Value | Consequence |
|---|---|---|
| CPU | 16 logical cores | PPO training is CPU-bound but feasible |
| RAM | 16.83 GB total, **5.61 GB free** | Constrains multi-env PPO and the 959 MB CSV |
| GPU / CUDA | **None** (`torch 2.8.0+cpu`, `cuda_available=False`) | Local PPO training is slow → Colab justified for large runs |
| OS | Windows 11 (10.0.26300) | — |

### 3.5 Capability verdict

| Capability | Status |
|---|---|
| Static checks, unit tests, data validation | **Available locally** |
| Small simulation tests (env rollouts, LP solves) | **Available locally** |
| Loading the existing PPO checkpoint | **Available locally** |
| Full 50k-step PPO retrain | Feasible but slow on CPU; Colab recommended |
| Google Colab | Not reachable from here — the notebook must stay Colab-ready, not Colab-dependent |

### 3.6 Baseline test run (original project, unmodified)

```
cd GoalPilot_AI\GoalPilot_MultiGoal_Extension
python -m pytest tests -q
-> 26 passed in 4.02s
```

Note: the committed `outputs/test_results.txt` says *"11 passed"* — **stale**, written before
15 further tests were added. The live suite is 26 tests and all pass.

---

## 4. Audit findings

Severity: **S1** = invalidates headline results · **S2** = distorts conclusions · **S3** = robustness/craft.

---

### F-01 · S1 · Savings-only and Mixed-allocation are **mathematically identical** for goal funding

**Confirmed, 100/100 users, exact.**

Evidence — `audit_tools/diag_baseline/baseline_policy_summary.csv`:

| policy | mean funded (₹) | mean funding ratio | mean final portfolio (₹) |
|---|---:|---:|---:|
| Savings only | 1,220,790.18 | 0.2735 | 165,778.06 |
| Mixed allocation | 1,220,790.18 | 0.2735 | 710,294.22 |

Per-user: `|mixed − savings| <= 1e-12` for **100 / 100** users; max abs difference **1.665e-16**;
max abs difference in funded rupees **1.397e-09**.
Meanwhile the median portfolio difference is **₹237,955.72**.

**Root cause** — `goalpilot_env.py` lines 216–225:

```python
raw_savings     = action[:n, 0] * available_after_existing_loan
raw_investments = action[:n, 1] * invest_cap          # invest_cap = A * investment_capacity_ratio
total_raw       = raw_savings.sum() + raw_investments.sum()
budget_scale    = min(1.0, A / total_raw)              # A = available_after_existing_loan
savings_alloc   = raw_savings * budget_scale
invest_alloc    = raw_investments * budget_scale
```

then line 364 credits **both channels at face value**:

```python
contribution = savings_alloc + invest_alloc
self.goal_balances[j] += float(amount)
```

For `n` goals with ratio `ρ`, savings-only gives `A/n` per goal. Mixed `(0.5, 0.5)` gives
`0.5·A·s + 0.5·A·ρ·s` with `s = 2/(n(1+ρ))` → **`A/n`**. Identical.

**The exact condition is saturation.** The identity holds whenever the combined action
weights are large enough that `budget_scale` clamps:

$$n \;(1 + \rho) \;\ge\; 2$$

Measured: all 100 users have `n ∈ {3,4,5}` and satisfy the condition.
`pd.crosstab(identity_expected, exact_match)` = **100 True / 100 True**.
For a user with a single goal and low investment capacity the identity would not hold, because
`total_raw < A` and no clamping occurs.

### 4.1.1 The archive used two *different* "Mixed allocation" policies

This matters because a comparison that conflates them is simply wrong:

| archived file | "Mixed allocation" weights | mean funding ratio (100 users) |
|---|---|---:|
| `rl_baseline_policy_comparison.csv` | `(0.25, 0.25)` | 0.2683 |
| `rl_policy_diagnostic_summary.csv` | `(0.25, 0.25)` | 0.2683 |
| `rl_heldout_policy_comparison_detail.csv` | **`(0.50, 0.50)`** | 0.2256 |
| `rl_heldout_policy_comparison_summary.csv` | **`(0.50, 0.50)`** | 0.2256 |

`(0.25, 0.25)` sums to less than the monthly budget and therefore under-allocates by F-02;
`(0.50, 0.50)` saturates and is exactly equivalent to savings-only. **The degeneracy applies
only to the held-out tables — which are precisely the tables used to compare PPO.** Both
variants are now labelled explicitly in `evaluation/policy_evaluation.py`.

**Impact:** the "mixed allocation vs savings-only" column is:
* in the **held-out / PPO comparison** tables — **zero information** (identical by construction);
* in the **100-user baseline** tables — under-allocating, i.e. a variant of the F-02 handicap
  rather than a policy difference.

In both cases the mix only ever changes portfolio growth — i.e. wealth, not goals. Any
conclusion of the form "the mix does not help goal funding" is an artefact of the environment,
not a finding.

---

### F-02 · S1 · The action vector is a **magnitude**, not a **share** → policies that output < ~0.5 systematically under-fund

Evidence — `audit_tools/diag_baseline/baseline_policy_summary.csv`:

| constant savings action | mean funded (₹) | mean unallocated surplus (₹) | funded / Savings-only |
|---|---:|---:|---:|
| 0.25 | 1,150,004.96 | 847,540.31 | 94.2 % |
| 0.50 | 1,220,790.18 | 776,755.09 | 100.0 % |
| 0.75 | 1,220,790.18 | 776,755.09 | 100.0 % |
| 1.00 (Savings only) | 1,220,790.18 | 776,755.09 | 100.0 % |

Two consequences:

1. **Below the saturation point the policy under-funds.** `budget_scale = min(1, A/total_raw)` only
   ever scales *down*; it never scales *up*. A policy emitting `0.3` on every channel commits only
   ~60 % of the available budget, and the remainder is silently dropped.
2. **Above the saturation point the reward is flat.** Actions 0.5 / 0.75 / 1.0 produce *identical*
   goal funding, therefore *identical* reward. There is **no gradient** pushing the policy from 0.5
   toward 1.0. The baseline policies sit exactly on this plateau by construction; PPO does not.

**Impact:** PPO is structurally handicapped against every baseline. The baselines are hand-coded to
emit exactly `1.0` and thereby always capture the full budget; a stochastic Gaussian policy cannot
reliably find that plateau because the reward gives it no reason to. This is a **primary cause** of
F-03 and must be fixed before any retrain is meaningful.

---

### F-03 · S1 · The risk penalty dominates the reward and has no offsetting terminal-value term

Evidence — `audit_tools/diag_baseline/baseline_policy_summary.csv`, `mean_reward` column:

| policy | mean_reward | mean final portfolio (₹) | mean funded ratio |
|---|---:|---:|---:|
| Savings only | **−7.92** | 165,778 | 0.2735 |
| Mixed allocation | **−11.67** | 710,294 | 0.2735 |
| Loan request only | −13.00 | 165,778 | 0.0802 |
| No action | −13.62 | 165,778 | 0.0176 |
| Investments only | **−23.13** | 2,259,643 | 0.2440 |

Savings-only and Mixed have **identical goal funding** yet rewards of −7.92 vs −11.67. The only
difference is portfolio size. The term responsible is `goalpilot_env.py` lines 397–400:

```python
reward -= max(0.0, abs(market_return) - risk_score * 0.05) * (self.portfolio / 100000.0)
```

This is charged **every month**, scales linearly with portfolio (÷100,000), and is the *only* reward
term that grows with wealth. There is **no reward for terminal portfolio value or net worth**.
By contrast the goal-progress term is bounded at `2.0` per goal per month (line 383–386).

**Impact:** the reward function actively teaches the agent *not to invest*. PPO's held-out mean final
portfolio is ₹351,024 versus ₹2,259,643 for Investments-only — consistent with the agent having
learned to suppress the investment channel. This is the **second primary cause** of PPO
underperformance, and it is a reward-design defect, not a training-budget defect.

---

### F-04 · S1 · Contributions are counted twice — `cash`, `portfolio` **and** `goal_balances` all hold the same money

**Confirmed by exact reconstruction.**

Evidence — `audit_tools/diag_baseline/baseline_policy_all_users.csv`, H3 block
(Savings only, first 5 users, all `match = True`):

| user | env `final_cash` (₹) | reconstructed (₹) | `goal_balances` (₹) | contributions (₹) |
|---|---:|---:|---:|---:|
| USER_00001 | 1,554,312.04 | 1,554,312.04 | 1,494,522.91 | 1,435,050.65 |
| USER_00003 | 406,499.72 | 406,499.72 | 345,794.47 | 333,487.82 |
| USER_00004 | 235,063.47 | 235,063.47 | 169,630.11 | 148,495.53 |
| USER_00005 | 2,607,035.49 | 2,607,035.49 | 2,628,229.74 | 2,514,727.59 |

`final_cash == (initial_savings − reconciled_earmark) + total_savings_contributions` **exactly**.
And `goal_balances` contains *the same* `savings_alloc + invest_alloc` (line 364).
`portfolio` separately contains `invest_alloc` (line 317).

**Impact:** any aggregate of the form `cash + portfolio + goal_balances` is **structurally
wrong** — it double-counts savings and investments by exactly the contributions. Every wealth
column in `rl_baseline_policy_comparison.csv`, `rl_heldout_policy_comparison_*.csv`,
`rl_long_horizon_policy_comparison.csv` inherits this.

### 4.4.1 A second, larger defect in the same line of code: the archive discarded the unallocated surplus

Once the ledger was balanced, a **worse** problem surfaced, and it moves the numbers further
than the double count does.

In the archived environment, `cash` increased only by `savings_alloc.sum()`
(`goalpilot_env.py:319`). Surplus that the policy did *not* allocate to a goal — the
`unallocated_surplus` — entered **no account at all** and vanished from the balance sheet.

Measured on the 20 held-out users (`outputs/evaluation/policy_summary_corrected_accounting_test.csv`
vs the archived `rl_heldout_policy_comparison_summary.csv`):

| policy | archived `mean_net_financial_wealth` | corrected ledger net worth | mean unallocated surplus | difference |
|---|---:|---:|---:|---:|
| **No action** | **232,303.39** | **2,030,439.84** | 1,798,136.44 | **+1,798,136.45** |
| Savings only | 1,302,720.08 | 2,030,439.84 | 727,719.76 | +727,719.76 |
| Investments only | 2,182,848.29 | 2,983,077.47 | 800,229.18 | +800,229.18 |
| Mixed (0.50/0.50) | 1,570,221.13 | 2,297,940.89 | 727,719.76 | +727,719.76 |
| PPO | 887,092.48 | 2,098,076.46 | 1,128,588.05 | +1,210,983.98 |

The difference equals the unallocated surplus in every row, exactly. For the **"No action"**
policy the archive reported mean net worth of **₹232,303** when the household in fact still
holds **₹2,030,440** of unspent surplus — an **8.7× understatement**.

This is the most consequential accounting error in the project. It inverted the ordering of the
policies on wealth: the archive made "No action" look like the *poorest* outcome, when it is in
fact indistinguishable from "Savings only" — both simply leave the surplus in cash, and the
corrected ledger shows them at the **same** ₹2,030,439.84.

Any conclusion drawn from an archived wealth column about *whether acting is better than doing
nothing* is therefore unreliable in both directions. It must be re-derived — which
`evaluation/policy_evaluation.py` now does, reporting `net_worth_ledger` and
`net_worth_archived_aggregate` side by side so the gap is visible rather than implicit.

---

### F-05 · S1 · Loan proceeds are credited to goals but never recorded as an asset; EMI payments never leave any account

`goalpilot_env.py`:

- line 340: `self.loan_balance = float(new_loan)` — **liability created**
- line 358–366: `loan_goal_contribution` credited to `goal_balances` — **goal asset created**
- **no** `self.cash += new_loan` — the proceeds never enter a balance-sheet asset
- line 322–336: the EMI is computed and `loan_balance` amortised, but
  **no account is debited** — `self.cash` and `self.portfolio` are untouched by the payment

So a loan increases goal funding (and reward) while leaving the ledger untouched on both sides.

Corroborating evidence — `audit_tools/diag_baseline/baseline_policy_summary.csv`:

| policy | mean new loan principal (₹) | mean final loan balance (₹) | mean funded ratio |
|---|---:|---:|---:|
| Loan request only | 193,576.64 | 25,831.55 | 0.0802 |
| Savings only | 0.00 | 0.00 | 0.2735 |
| No action | 0.00 | 0.00 | 0.0176 |

Loan-only funding (0.0802) is **4.6× No-action** (0.0176) purely from principal credit, and its
reward (−13.00) is *better* than No-action (−13.62). Borrowing is rewarded without being paid for.

**Impact:** `mean_new_loan_principal = 13,534` and `mean_final_loan_balance = 351,024` for PPO in
`rl_heldout_policy_comparison_summary.csv` are not interpretable as financial outcomes. The observed
"PPO generates borrowing" behaviour is a rational response to a mis-specified ledger, not (only) a
policy artefact.

---

### F-06 · S2 · LP and RL operate on **different goal targets and different assumptions**

`GoalPilot_MultiGoal_Extension/src/multi_goal_optimizer.py` line 102:

```python
g["future_goal_cost"] = g.current_cost * (1 + annual_inflation) ** (g.time_horizon_months / 12)
```

Called from the notebook with `annual_inflation=0.03` (cell at line 7,816).
`goalpilot_env.py` line 157:

```python
self.goal_targets = self.user_goals["current_cost"].astype(float).to_numpy()
```

and its own docstring: *"Inflation is deliberately excluded until a defensible rate series is
available."*

| Aspect | LP | RL env |
|---|---|---|
| Goal target | `current_cost × 1.03^(months/12)` | `current_cost` (nominal) |
| Emergency reserve | `liquid_savings − 6 × essential_expenses − earmarks` | not deducted |
| Investment return | fixed `5 %` p.a. | actual monthly NIFTY return |
| Loan rate | fixed `12 %` p.a., 60-month tenure | `walr_monthly` per month, 60-month tenure |
| Existing investments | `usable_existing_investments = 0.0` | not modelled |
| Horizon | per-goal `time_horizon_months` (1–240) | global `len(market)` = 142 months |

Numbers being compared (both averaged over the same 100 users):

| source | file | metric | value |
|---|---|---|---|
:---:|---|---|---:|
| LP | `rl_lp_diagnostic_summary.csv` | mean weighted goal achievement | **0.2269** |
| RL | `rl_policy_diagnostic_summary.csv` | Savings-only mean funding ratio | **0.2735** |
| RL | `rl_policy_diagnostic_summary.csv` | Investments-only mean funding ratio | **0.2440** |

The RL figure is *not* better than the LP: the RL denominator is nominal while the LP denominator is
inflated by 3 % p.a. over horizons up to 240 months (up to **+80 %**), and the RL run has no emergency
reserve. **The two numbers are not commensurable.**

---

### F-07 · S2 · Reward components are unvalidated and mis-scaled relative to each other

`goalpilot_env.py` reward block (lines 370–400), with measured magnitudes:

| Component | Line | Formula | Measured magnitude |
|---|---|---|---|
| Incremental goal progress | 383–386 | `+2.0 · Δratio · priority/5` | ≤ 2.0 / goal / month |
| Deadline shortfall penalty | 389–393 | `−5.0 · shortfall_ratio · criticality/5` | fires **once**, in the deadline month only |
| Loan penalty | 396 | `−0.00001 · new_loan` | ₹150,000 loan → **−1.5** |
| Risk penalty | 397–400 | `−max(0, \|r\| − risk·0.05) · portfolio/100000` | dominated; see F-03 |

Three problems, all measurable:

1. **The shortfall penalty fires only in the exact deadline month** (`if self.month_index + 1 ==
   self.goal_deadlines[j]`). A goal missed by 60 % at month 123 is penalised once and then forgotten.
   Because `gamma = 0.99` (effective horizon ≈ 100 steps), the month-123 signal is discounted to
   ≈ `0.99^123 ≈ 0.29` — and for `max_goals` slots whose deadline exceeds 142 months it **never fires
   at all**, because the episode ends first.
2. **Reward is not normalised by goal scale.** A ₹50,000 goal and a ₹8,710,322 goal (both present in
   `rl_sample_goals.csv`) each contribute at most `2.0` per month.
3. **The loan penalty (₹1.5 per ₹150k) is 10⁵ times weaker per rupee than the goal credit it buys.**

---

### F-08 · S2 · Evaluation harness has its own double-counted budget metric

`GoalPilot_RL_PreCheck.ipynb` cell **141** (exec 217):

```python
budget_excess = savings + investments + commitment - surplus
```

where `commitment = info["combined_monthly_commitment"]`, and the environment defines
`combined_monthly_commitment = savings + investments + monthly_loan_commitment`
(line 402–406). This expression adds savings and investments **twice**.

The author noticed and corrected it in cell **143** (exec 219, comment *"Correct: combined commitment
already includes contributions."*) — but **cell 143 overwrote the same output CSVs** with the corrected
metric, so `rl_heldout_policy_comparison_detail.csv` reflects the *corrected* version. The buggy cell
141 version was never persisted. **Verified** by reading both cells; both write to the same paths.

Status: **already fixed in the notebook, still latent in the codebase** because the metric is
re-implemented ad-hoc in five separate cells. It must be moved into one shared evaluator (plan P1).

---

### F-09 · S2 · Test coverage does not reach the RL environment at all

26 tests exist (`GoalPilot_AI/GoalPilot_MultiGoal_Extension/tests/`), all 26 pass.
They cover the LP (`test_optimizer.py`), providers (`test_providers.py`) and the adapter
(`test_simulation_adapter.py`).

**There is no test file for `goalpilot_env.py`** — no assertion on:
budget conservation, the earmark reconciliation, the goal cap, loan amortisation, the
`combined_monthly_commitment` guard, reward finiteness, or determinism.

The notebook performed these checks ad-hoc (`check_env`, one full-episode budget check in cell 119),
but none is registered as a regression test. F-04 and F-05 therefore have **no failing test** to
catch them.

---

### F-10 · S3 · PPO is severely undertrained relative to the problem size

`GoalPilot_RL_PreCheck.ipynb` cell **139** (exec 214):

```python
model = PPO("MlpPolicy", train_env, learning_rate=3e-4, n_steps=1024, batch_size=256,
            n_epochs=10, gamma=0.99, gae_lambda=0.95, ent_coef=0.01,
            policy_kwargs={"net_arch": [128, 128]}, seed=42)
model.learn(total_timesteps=50_000, callback=eval_callback)
```

| Quantity | Value | Implication |
|---|---|---|
| Timesteps | 50,000 | — |
| Episode length | **142 steps** (market length) | ≈ **352 episodes total** |
| Action dimensionality | **15** continuous dims | large for 352 episodes |
| Observation | 42 dims | — |
| `eval_freq` | `142 × 10` = 1,420 | ≈ 35 evaluations × 10 episodes |
| Effective horizon | `1/(1−γ)` = **100 steps** | < episode length; deadline signals at 123–240 months are discounted to 0.09–0.29 or never reached |

**Impact:** the checkpoint genuinely cannot be read as evidence about PPO's potential. Any claim that
"PPO underperforms" must be stated as *"this 50k-step PPO underperforms, for reasons partly
structural (F-02, F-03) and partly budget (F-10)"*.

---

### F-11 · S3 · Long-horizon evaluation silently excludes PPO

`RL_PreCheck` cells 135–136 build `rl_long_horizon_policy_comparison.csv` from
`policies = ["No action", "Savings only", "Investments only", "Mixed allocation"]`.
`rl_long_horizon_policy_summary.csv` therefore has **26 goals × 4 policies and no PPO row**.
The file name does not disclose this. Any reader comparing "long horizon" results to the held-out
table will silently compare different policy sets.

---

### F-12 · S3 · Hard-coded Colab paths throughout

Every notebook cell uses `Path("/content/drive/MyDrive/GoalPilot_AI/…")` (~40 occurrences) plus
`drive.mount("/content/drive")`. `GoalPilot_MultiGoal_Extension` scripts use relative paths.
There is **no shared path resolver**, so the project cannot be executed in both environments from one
source of truth.

---

### F-13 · S3 · `torch` is CPU-only and `sb3 2.9.0` / `gymnasium 1.4.0` are newer than the pins the notebook assumes

Notebook cell 0 pins `"gymnasium>=1.0,<2.0"` and `"stable-baselines3>=2.4,<3.0"`.
Locally we resolved **gymnasium 1.4.0 / sb3 2.9.0** — inside the stated ranges, so
compatible by declaration. This has **not** been exercised end-to-end yet;
`check_env` + a load-and-predict smoke test are in the plan (P1-11) precisely to prove it.

---

### F-14 · NOT TESTED · 959 MB and 169 MB CSVs were not fully parsed

`monthly_financial_simulation_base.csv` (959.34 MB) and `portfolio_simulation_validated.csv`
(169.12 MB) exceed the safe working set for 5.61 GB free RAM alongside the RL data.
Their **schemas** were inspected; their **content** was not validated end-to-end.
Upstream preprocessing (`datasets/`, `simulation/01–04_*`) was inspected structurally only.

---

### F-15 · NOT TESTED · Genesis of the multi-goal synthetic assumptions

`rl_sample_goals.csv` carries `synthetic_assumption_version = v1_seed_20261010` and
`goal_data_origin ∈ {existing_single_goal_simulation, synthetic_generated_goal}`.
The generator that produced the 290 synthetic goals is
`GoalPilot_MultiGoal_Extension/generate_multigoal_dataset.py`; its assumptions
(`docs/validation_report_2026-10-10_v2.md`, `docs/optimization_audit.md`) were **read and are internally
consistent**, but the generator was not independently re-derived. Determinism was not re-verified.

---

## 5. Findings mapped to the reported issues

| Reported issue | Verdict | Finding(s) |
|---|---|---|
| PPO underperforms savings / mixed baselines | **Confirmed**, but the comparison is not yet fair | F-02 (no gradient above the saturating action), F-03 (risk penalty suppresses investing), F-10 (352 episodes) |
| Savings-only ≡ mixed-allocation goal funding | **Confirmed exactly, 100/100 users** | F-01 |
| PPO generates borrowing needing examination | **Confirmed**, caused by a broken ledger | F-05, corroborated by F-07(3) |
| Reward components and their effect need validation | **Confirmed defective and unvalidated** | F-03, F-07 |
| LP and RL use different goal targets/assumptions | **Confirmed** | F-06 |
| Budget audit must avoid double-counting contributions/balances | **Confirmed in the env** (F-04); already fixed in the LP (earmarks) and in notebook cell 143 | F-04, F-08 |

---

## 6. Prioritised implementation plan

Ordering rule: **nothing that changes PPO-visible behaviour until its diagnostic exists.** The
reward function is frozen until P0-3 (reward decomposition) is delivered.

### P0 — Correctness. Must land before any retrain or any re-run of comparisons.

| ID | Change | Files | Acceptance test |
|---|---|---|---|
| P0-1 | Add a single **cash-flow ledger + balance sheet** to the env: EMI payments debit an account; loan proceeds credit an account; separate *earmarked goal balances* from *liquid assets*; expose `info["ledger"]` and `info["budget_audit"]` per month | `goalpilot_env.py` | New test: every month satisfies `inflow − expenses − existing_EMI − new_EMI − Σcontributions − unallocated == 0`; and `cash + portfolio − loan == initial_net_worth + Σ(investment returns)` |
| P0-2 | Add a documented `net_worth` that does **not** re-add goal balances, and keep goal balances as a memo account | `goalpilot_env.py`, evaluator | Test: `net_worth` after a zero-action episode equals initial `cash + portfolio − loan` |
| P0-3 | **Reward decomposition harness** — per month, per component (progress, deadline shortfall, loan, risk, unallocated), for fixed seeds and fixed policies, written to CSV + plot | new `evaluation/reward_decomposition.py` | Output CSV produced; component totals sum to the env reward within 1e-9 (`test_reward_components_sum_to_reward`) |
| P0-4 | **Borrowing audit** — per user: loans originated, EMI paid, interest cost, whether the loan changed goal funding or net worth, and the same goal's outcome with borrowing disabled | new `evaluation/borrowing_audit.py` | CSV + `test_borrowing_ledger_is_balanced` |
| P0-5 | Move the held-out evaluator into **one** shared module with the **corrected** budget metric (no double count) | new `evaluation/policy_evaluation.py` | `test_budget_metric_not_double_counted`; reproduced numbers must match the existing CSVs to 1e-9 for baselines (they do not depend on the bug) |
| P0-6 | **Baseline degeneracy guard** — an executable test that *documents and pins* F-01, so it can never regress silently | `tests/test_goalpilot_env.py` | `test_savings_only_equals_mixed_when_n_ge_threshold` passes on the current env and is marked as an xfail-after-fix |

### P1 — Make the comparison meaningful.

| ID | Change | Acceptance test |
|---|---|---|
| P1-7 | **Action semantics**: add `action_mode ∈ {"magnitude" (default, current), "share" (normalised)}`. In `share` mode the vector is normalised so the budget is fully allocated → removes the F-02 handicap for every policy including PPO | `test_share_mode_fully_allocates_budget`; flat 0.25/0.5/0.75/1.0 must produce **identical** funding in share mode |
| P1-8 | **Configurable goal-credit channel** so the savings/investment mix can matter: `goal_credit_mode ∈ {"face_value" (default), "growth_weighted"}` using the savings rate vs the market path | `test_mix_matters_in_growth_weighted_mode` (mixed ≠ savings under this mode) |
| P1-9 | **`GoalPilotConfig`** — one config object for `annual_inflation`, `target_basis`, `emergency_months`, loan rate source, tenure, `max_loan_per_goal`; and a `--target-basis {nominal,inflated}` switch applied to **both** LP and RL | `test_lp_and_rl_share_target_basis` — same input ⇒ same total target |
| P1-10 | **Path resolver** `goalpilot_paths.py` — env var → local auto-detect → Colab fallback. Notebook rewritten to use it | `test_paths_resolve_locally`; notebook imports the resolver |
| P1-11 | **Compatibility smoke test**: `check_env`, load `best_model.zip`, predict, roll out one episode | `test_env_passes_gymnasium_check`, `test_ppo_checkpoint_loads_and_predicts` |

### P2 — Execute and evidence.

| ID | Change |
|---|---|
| P2-12 | Re-run the full baseline + PPO evaluation under **both** action modes, emitting versioned CSVs to `outputs/evaluation/` |
| P2-13 | Produce plots (funding ratio by policy, reward-component stackplot, borrowing distribution, LP-vs-RL on a common target basis) |
| P2-14 | Optional local PPO retrain at a **documented** budget with the fixed action semantics, CPU-only, logged to `training_logs/`; Colab config provided for a larger run |

### P3 — Documentation and reproducibility.

| ID | Deliverable |
|---|---|
| P3-15 | `README.md` — how to run locally and in Colab, with the exact interpreter |
| P3-16 | `docs/FYP_DEMO_GUIDE.md` — a scripted 10-minute demonstration |
| P3-17 | `docs/MODIFICATION_LOG.md` — every modified file + reason + versioned backup path |
| P3-18 | `docs/EXECUTION.md` — what was actually run, with raw console output |

---

## 7. How to reproduce this audit

```powershell
# Interpreter B is the only one with the dependencies.
$py = "C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe"

$py audit_tools\00_env_check.py            # env + dependency probe
$py audit_tools\01_notebook_compare.py     # notebook byte/diff comparison
$py audit_tools\02_inventory.py            # inventory + duplicate detection
$py audit_tools\03_extract_nb.py           # notebook -> flat .py + cell index
$py audit_tools\10_diag_env.py             # F-01, F-02, F-04 evidence

# Original LP suite
Push-Location GoalPilot_AI\GoalPilot_MultiGoal_Extension
& $py -m pytest tests -q
Pop-Location
```

Artefacts are written to `audit_tools/` and `audit_tools/diag_baseline/`.

---

## 8. Verification and measured resolution

Everything below was produced by running code in this working copy. Raw console output is in
`docs/EXECUTION.md`.

### 8.1 The reworked environment reproduces the archive exactly

`evaluation/verify_against_archive.py` compares the new shared evaluator against all four
archived result files, in `GoalPilotConfig.archived()` mode:

| archived file | field comparisons | mismatches |
|---|---:|---:|
| `rl_baseline_policy_comparison.csv` | 4,800 | **0** |
| `rl_policy_diagnostic_summary.csv` | 16 | **0** |
| `rl_heldout_policy_comparison_detail.csv` | 700 | **0** |
| `rl_heldout_policy_comparison_summary.csv` | 25 | **0** |
| **total** | **5,541** | **0** |

Independently, `tests/test_goalpilot_env_parity.py` rolls out **100 users × 5 policies ×
142 months** against the archived environment module and compares reward, goal balances,
goal targets, cash, portfolio and loan balance **month by month**, to 1e-12 on reward and
1e-9 on state. Result: **3 passed in 158 s**.

The archived environment is preserved byte-exact at
`archive/goalpilot_env_archived_20261010.py`
(SHA-256 `FDFE6D9D5280E20C1C69A9180FBDF326F7D3B9D353BCE4DAA13065F7C4A9FEFD`).

### 8.2 F-04 / F-05 quantified — legacy vs ledger

Measured on the 20 held-out users with an identical savings plan with and without a loan
request (`evaluation/borrowing_audit.py`):

| accounting | mean net-worth change attributable to borrowing |
|---|---:|
| `legacy` (archived) | **−₹65,948.63** |
| `ledger` (corrected) | **−₹12,718.60** (= interest paid) |

The legacy figure is a **5.2× overstatement**: it charges the full outstanding principal as
a loss because the proceeds never entered an account. In the corrected ledger, borrowing
alone changes net worth by **₹0.00** at origination, and over an episode by exactly
`surplus + investment gain − interest` — asserted every month by
`test_ledger_net_worth_change_equals_expected`.

The double count itself is pinned numerically in
`test_legacy_mode_double_counts_and_ledger_mode_does_not`:

```
legacy.cash                        == initial_cash + contributions
legacy.earmarked_goal_funding      == earmark      + contributions
legacy.cash + legacy.earmarked     == initial_savings + 2 × contributions
```

i.e. every contributed rupee appears exactly twice. Worked example, USER_00001, savings-only,
142 months (verified numerically against `rl_baseline_policy_comparison.csv`):

| quantity | value (₹) |
|---|---:|
| initial savings | 178,733.65 |
| initial investment | 45,777.55 |
| scaled goal earmark | 59,472.26 |
| cumulative savings contributions | 1,435,050.65 |
| archived `final_cash` | 1,554,312.04 |
| archived `final_goal_funding` (= `goal_balances`) | 1,494,522.91 |
| archived `final_portfolio` (market value) | 122,266.53 |
| **archived `cash + goal_balances`** | **3,048,834.94** |
| **archived `cash + goal_balances + portfolio`** | **3,171,101.47** |
| **true net worth** (`cash + portfolio`, ledger basis) | **1,736,050.82** |
| overstatement | **1,435,050.65** — exactly the contributions |

The true liquid position (cash and savings only) is ₹1,613,784.30, which equals
`archived cash + earmark` = 1,554,312.04 + 59,472.26 — the archive's `cash` alone hides the
earmark, and `goal_balances` then re-adds it.

### 8.3 F-07 quantified — what actually drives the reward

`evaluation/reward_decomposition.py`, 20 held-out users × 142 months = 2,840 user-months per
policy. Component sums (max |reward − Σcomponents| = **1.78e-15**):

| policy | total reward | incremental progress | deadline shortfall | loan penalty | risk penalty |
|---|---:|---:|---:|---:|---:|
| No action | −274.29 | 0.00 | −246.90 | 0.00 | −27.38 |
| Savings only | −171.56 | **+44.48** | −188.66 | 0.00 | −27.38 |
| Investments only | −422.96 | +41.13 | −193.65 | 0.00 | **−270.44** |
| Mixed (0.50/0.50) | −237.80 | +44.48 | −188.66 | 0.00 | −93.62 |
| Mixed (0.25/0.25) | −237.83 | +44.31 | −189.12 | 0.00 | −93.02 |
| Savings + loan | −182.46 | +45.26 | −188.49 | −11.84 | −27.38 |
| PPO | −236.22 | **+29.99** | −200.78 | **−15.94** | −49.50 |

Three measured conclusions:

1. **The positive signal is tiny against the penalties.** The best policy earns **+44.5** for
   goal progress and pays **−188.7** in deadline shortfalls. Total achievable progress reward
   is bounded by `2 × n_goals × 142 ≈ 1,136`; only **3.9 %** is captured. The reward is
   dominated by terms the agent barely controls.
2. **F-03 is confirmed at scale.** Investing multiplies the risk penalty **10.0×**
   (−270.44 vs −27.38) while adding **no** terminal-value reward. `dominant_component` is
   `risk_penalty` for Investments-only and `deadline_shortfall_penalty` for every other
   policy.
3. **PPO's deficiency is real but partly structural.** PPO earns the **lowest** progress
   reward of any active policy (+29.99 vs +44.48) and pays the **largest** loan penalty
   (−15.94). Both are consistent with F-02 (no gradient above the saturation point) and
   F-10 (352 episodes).

### 8.4 Borrowing: useful or not?

`evaluation/borrowing_audit.py`, corrected ledger, held-out users, savings plan identical
except for the loan request:

| metric | value |
|---|---:|
| users taking a loan | 11 / 20 |
| total principal originated | ₹1,183,966 |
| total interest paid | ₹256,912 |
| **helps goal funding** | **5 users** |
| **hurts goal funding** | **5 users** |
| funding neutral | 1 user |
| mean funding-ratio change | +0.0071 (0.2256 → 0.2327) |
| mean net-worth change | −₹12,718.60 |
| **median interest per extra funded rupee** | **₹0.2885** |

So the answer to "PPO generates borrowing that needs to be examined" is: **borrowing is a
genuine trade-off, not an artefact** — it improves goal funding for about half the users at a
measurable cost of roughly 29 paise of interest per extra rupee funded. The archived version of
this question was unanswerable, because the ledger booked no asset for the proceeds and no
payment for the EMI.

### 8.5 F-02 resolution — measured effect of the action-mode fix

`evaluation/run_all.py` writes `outputs/evaluation/action_mode_comparison.csv`. In `share`
mode, constant savings actions of 0.25 / 0.50 / 0.75 / 1.00 produce **identical** goal funding,
because the full budget is allocated regardless of magnitude; in `magnitude` mode they do not.
That is the whole of the F-02 fix, and it is asserted by
`test_share_mode_makes_action_magnitude_irrelevant`.

### 8.6 A latent defect found while writing the tests

`max_goals` was inferred from *whichever subset of users was passed in*, so the observation
and action space shape depended on the split. In the archived 80/20 split both sides happen
to have 5 slots, so nothing broke — but an eval environment built from a different subset
would silently have a different space and could not load the checkpoint.

Now pinned by `GoalPilotConfig.n_goal_slots` (default 5 in `archived()`), with
`test_n_goal_slots_pins_the_space_across_subsets` and
`test_n_goal_slots_smaller_than_data_is_rejected`.

### 8.7 Test suite status

| suite | tests | result |
|---|---:|---|
| `tests/` (new, RL + config + parity) | **64** | all passing |
| `GoalPilot_MultiGoal_Extension/tests/` (extant LP) | 26 | all passing, unchanged |

Before this work the RL environment had **zero** tests.

### 8.8 Status of each reported issue

| reported issue | status |
|---|---|
| PPO underperforms the baselines | **Confirmed and explained** — F-02 removed as a structural handicap, F-03 and F-10 quantified. A retrain is the next step; the archived checkpoint cannot be fairly compared under `share` semantics |
| Savings-only ≡ mixed goal funding | **Confirmed exactly, 100/100 users; cause derived; fix implemented and tested** |
| PPO borrowing needs examination | **Examined and priced** — 5 help / 5 hurt / 1 neutral; ₹0.29 interest per extra funded rupee; borrowing is net-zero on net worth at origination |
| Reward components need validation | **Validated** — decomposed per month per policy, sums verified to 1.8e-15, dominance measured |
| LP and RL use different targets/assumptions | **Confirmed** — divergence enumerated (F-06); `lp_parity()` aligns them; parity tested |
| Accounting must avoid double counting | **Confirmed in the RL env, fixed, and proved against the archive** — 5,541 comparisons, 0 mismatches |

### 8.9 Not done, by design

The reward function is **unchanged**, and **PPO was not retrained**. The task required the
diagnostics first, and F-03 and F-07 are now documented with the measurements needed to
justify a specific reward redesign and a specific training budget.
