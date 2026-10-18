# Capacity-constrained LP benchmark — design, validation, comparison

**Date:** 2026-10-11 · **Version:** v7 (v1–v6 untouched)
**New source:** `simulation/05_simulation_runs/rl_prototype/goalpilot_constrained_lp.py`
**New tests:** `tests/test_goalpilot_constrained_lp.py` (11)
**Experiment:** `audit_tools/56_constrained_lp_comparison.py`
**Data:** `outputs/evaluation/final_validation_v7/`
**No PPO training. No reward coefficients changed. No reward version selected. No previous output
modified.**

---

## 1. Design

### 1.1 What the existing LP does and what is missing

`optimize_multi_goal` already separates `save` and `invest` per goal, but bounds monthly
investment **only by the monthly surplus**:

```
sum_j (save_j + invest_j)           <= monthly_surplus
sum_j (save_j + invest_j + loan_j * emi_factor) <= monthly_surplus
sum_j loan_j * emi_factor           <= income * emi_income_ratio_cap - existing_emi
```

The RL environment additionally caps investment at

```
invest_cap = available_after_existing_loan x investment_capacity_ratio
```

with `investment_capacity_ratio <= 0.4988` in this population. **That constraint is absent from
the LP**, and the v6 report measured the consequence: 1,438,590 of unimplementable investment
demand per cohort.

### 1.2 Constraints added (each independently switchable)

Let `g = 6n` variables: per goal `cash0_j, asset0_j, save_j, invest_j, loan_j, short_j`.

**(a) Investment capacity** — enabled by `enforce_investment_capacity`:

```
sum_j invest_j  -  capacity_ratio * sum_j loan_j * emi_factor   <=  capacity_ratio * monthly_surplus
```

i.e. `sum_j invest_j <= (monthly_surplus - sum_j loan_j * emi_factor) x capacity_ratio`, exactly
the environment's `available_after_existing_loan x investment_capacity_ratio` with the capacity
base taken **net of the new loan's EMI commitments**.

**(b) Single loan** — enabled by `enforce_single_loan_limit`:

```
sum_j loan_j  <=  max_new_loan          (= 150000, the environment's cap)
```

The existing LP bounds loans **per goal**, so it can originate `n x 150000` in one month.

**(c) Unchanged, inherited from the existing model:** the per-goal funding-gap equality (which
with `short_j >= 0` already enforces the goal cap), the shared cash pool net of the emergency
reserve (`emergency_months x essential_expenses`, `emergency_months = 6.0` as in `lp_parity` and
`recommended`), the usable-existing-assets pool, the EMI cap, and the combined affordability
constraint.

### 1.3 Differences that remain, and why they are unavoidable

| Assumption | Existing/constrained LP | RL environment |
|---|---|---|
| Horizon | per-goal `time_horizon_months`, contributions valued at each goal's deadline | one 142-month episode, credited monthly |
| Returns | fixed `savings_return = 0.0`, `investment_return = 0.05` | realised NIFTY monthly path |
| Loan rate | fixed 12% p.a. | monthly `walr_monthly` path |
| Plan timing | **one-shot** static monthly plan, replayed | monthly decision on observed state |
| Budget base | `income - essential - discretionary - existing_emi` | `surplus - current_emi_due - new_emi` |
| Goal targets | `prepare_goals` inflation-adjusted (`1.03^(months/12)`) | `recommended()` uses `inflated` with `annual_inflation = 0.03` ✅ consistent |
| Emergency reserve | 6 months of essential expenses, deducted from the cash pool | 6 months, held as restricted cash ✅ consistent |
| Investment capacity | added here (constraint (a)) | always present |
| Max new loan | added here (constraint (b)) | always present |

Targets, reserve treatment, capacity rule, loan cap and credit mode are therefore **matched**;
horizon, return paths and the one-shot-versus-monthly decision are **not**, and are documented
rather than papered over.

---

## 2. Validation of the plan (Phase 2)

### 2.1 Model equivalence — the reimplementation is the same model

`test_flags_off_reproduces_the_existing_optimizer_exactly` asserts, for four real users, equality
with `optimize_multi_goal` on the **objective**, the **weighted achievement**, the **total
shortfall** and **every allocation column** (rtol 1e-9). With both switches off the module is the
original model, so any difference in §4 is attributable to the added constraints.

### 2.2 Feasibility, budget conservation, capacity, goal caps, affordability

| Check | Result |
|---|---|
| Budget conservation: `savings + investment + loan_EMI <= monthly_surplus` | **holds** for every solved user |
| Affordability: `loan_EMI <= emi_cap` and combined cash-flow `<= surplus` | **holds** |
| Capacity: `investment_total <= permitted` | **holds**; `capacity_permitted` equals `allowed_monthly_investment(...)` to 1e-9 |
| Goal caps: `projected_new_funding <= funding_gap`, `shortfall >= 0` | **holds**, 0 violations |
| Non-negative allocations | **holds** |
| Determinism | identical allocations on repeated solves |

### 2.3 Optimisation infeasibility is structurally unreachable

Every goal equality contains `short_j` with coefficient 1 and bounds `(0, gap)`, so the model
always has a feasible slack solution. **Solver "infeasibility" cannot arise from the modelling**
— a user with zero capacity and zero loan allowance still returns `optimal`, with
`investment_total = 0` and a positive `total_shortfall`. Any difference between the LP's numbers
and the environment's is therefore an **execution** difference, not infeasibility. Pinned by
`test_infeasibility_is_unreachable_because_shortfall_is_a_slack`.

### 2.4 Planned versus executed — the measured execution gap

Per-month averages across the 16 fresh test users:

| Arm | planned savings /mo | planned investment /mo | investment permitted | executed investment /mo | executed savings /mo | executed overflow /mo |
|---|---:|---:|---:|---:|---:|---:|
| `existing_LP_unconstrained` | **0.0** | **13,736.66** | n/a | 2,023.56 | 6,914.10 | **10,130.92** |
| `constrained_LP` | 9,848.47 | 4,096.73 | **4,096.73** | 1,518.32 | 4,255.95 | **0.000058** |
| `constrained_LP_capacity_only` | 9,699.93 | 4,036.73 | 4,036.73 | 1,503.58 | 4,078.98 | 0.000047 |

Three things this establishes:

1. **The unconstrained LP plans an all-investment strategy with zero monthly savings** — 13,736.66
   of investment per month, of which the environment accepts only 2,023.56 and **relabels
   10,130.92/month as savings**. That is the exact mechanism behind the v6 finding, now measured
   at plan level.
2. **The capacity constraint binds exactly** (`planned investment == permitted investment`), and
   executed overflow falls from **10,130.92 to 0.000058** per month — a factor of about 1.75x10^5.
3. **Execution is partial even when feasible:** 1,518.32 of 4,096.73 investment (37%) and
   4,255.95 of 9,848.47 savings (43%) actually execute. The LP plans against the full monthly
   surplus while the environment reserves EMIs first and releases budget once goals saturate. I
   have **not** isolated which of those dominates; it is recorded as an execution gap.

### 2.5 Tests

```
$ python -m pytest tests\test_goalpilot_constrained_lp.py -q
11 passed in 3.06s
```

Covering: model equivalence and legacy parity, no cross-contamination of the original optimizer,
determinism, capacity enforcement, capacity = 0, the capacity constraint demonstrably binding,
budget conservation, affordability, goal caps, the single-loan constraint, structural
infeasibility, and encode-then-execute in the environment with the capacity ceiling asserted every
month.

**One corrected claim of my own:** I first asserted the single-loan cap would bind. It **never
binds** on this population — the EMI-affordability constraint restricts borrowing far below
150,000 first. The test now asserts that redundancy explicitly and demonstrates the mechanism
separately with a deliberately tight cap.

---

## 3. Cohort definitions

Eligibility is **ex-ante**: `income - expenditure - existing_emi > 0`. On the fresh test cohort:
**14 feasible / 2 structurally infeasible** (`USER_00087`, `USER_00082`).

**In the structurally infeasible cohort every one of the 13 arms scores exactly 0.0000
achievement, 0 fully funded, 0 deadline success, shortfall 6,252,575 and net worth 53,414** —
identical across LP, rules and RL. Nothing a policy can do differs there, which is the Phase-1
result restated at arm level.

---

## 4. Controlled comparison (Phase 3)

Identical 16 fresh test users, identical goals and targets, identical market path, one
configuration (`recommended()` = `share` + `legacy`). **0 capacity violations and 0
affordability violations in every arm.** RL arms run only under their training semantics (the
script asserts `action_mode == share` **and** `overflow_policy == legacy` before loading a
checkpoint; none is reinterpreted under `mix`).

### 4.1 Full population (n = 16)

| Policy | achievement | fully funded | by deadline | shortfall | savings | investment | cap overflow | net worth | debt | interest |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| RL `archived_v1` seed7 | **0.5908** | 0.4813 | 0.1146 | 8,589,238 | 965,674 | 374,028 | 388,382 | 2,748,925 | 10,178 | 8,716 |
| `investment-only` | 0.5800 | 0.4656 | 0.1427 | 8,567,394 | 972,435 | 386,883 | 1,479,048 | 2,751,777 | 0 | 0 |
| `mixed allocation` | 0.5800 | 0.4656 | 0.1427 | 8,567,394 | 972,435 | 386,883 | 439,156 | 2,751,777 | 0 | 0 |
| `uniform savings` | 0.5584 | 0.4531 | 0.1427 | 8,783,226 | 1,390,884 | 0 | 0 | 2,363,890 | 0 | 0 |
| `existing_LP_unconstrained` | 0.4928 | 0.3771 | **0.16875** | 8,713,979 | 981,803 | 287,345 | 1,438,590 | 2,680,083 | 5,554 | 7,484 |
| `constrained_LP` | **0.2452** | 0.2323 | 0.15313 | 9,192,529 | 604,345 | 215,601 | **0** | 2,606,859 | 5,977 | 11,357 |
| `constrained_LP_capacity_only` | 0.2421 | 0.2323 | 0.15313 | 9,220,419 | 579,215 | 213,508 | **0** | 2,603,544 | 5,672 | 11,371 |
| `urgency` | 0.4051 | 0.0625 | **0.0** | 8,125,197 | 2,048,914 | 0 | 0 | 2,363,890 | 0 | 0 |
| `need-proportional savings` | 0.3211 | 0.0625 | **0.0** | 8,125,197 | 2,048,914 | 0 | 0 | 2,363,890 | 0 | 0 |

### 4.2 Feasible cohort (n = 14)

| Policy | achievement | by deadline | shortfall | cap overflow | net worth |
|---|---:|---:|---:|---:|---:|
| RL `archived_v1` seed7 | **0.6753** | 0.13095 | 8,923,048 | 443,866 | 3,133,998 |
| `investment-only` | 0.6628 | 0.16310 | 8,898,082 | 1,690,341 | 3,137,257 |
| `uniform savings` | 0.6382 | 0.16310 | 9,144,747 | 0 | 2,693,958 |
| `existing_LP_unconstrained` | 0.5632 | **0.19286** | 9,065,608 | 1,644,103 | 3,055,321 |
| `constrained_LP` | 0.2803 | **0.17500** | 9,612,523 | **0** | 2,971,637 |
| `constrained_LP_capacity_only` | 0.2767 | 0.17500 | 9,644,397 | **0** | 2,967,848 |
| `urgency` | 0.4630 | 0.0 | 8,392,714 | 0 | 2,693,958 |
| `need-proportional savings` | 0.3669 | 0.0 | 8,392,714 | 0 | 2,693,958 |

`constrained_LP` and `constrained_LP_capacity_only` are near-identical everywhere (0.2803 vs
0.2767), confirming §2 that the single-loan constraint is redundant here and the capacity
constraint is the operative change.

### 4.3 Paired per-user differences — `constrained_LP` minus `existing_LP` (n = 16, user-level bootstrap)

| Metric | mean diff | sd | CI95 | improved / worsened | verdict |
|---|---:|---:|---|---:|---|
| `investment_cap_overflow` | **−1,438,590** | 1,440,125 | [−2,143,970, −794,943] | 0 / 12 | **constrained higher** (i.e. overflow eliminated) |
| `goal_achievement` | **−0.24755** | 0.20259 | [−0.34052, −0.15379] | 1 / 11 | **existing higher** |
| `pct_goals_fully_funded` | −0.14479 | 0.17968 | [−0.23229, −0.06250] | 0 / 7 | **existing higher** |
| `shortfall` | +478,551 | 797,550 | [134,502, 884,002] | 9 / 3 | **constrained higher** (worse) |
| `savings_contribution` | −377,457 | 685,822 | [−726,719, −76,546] | 3 / 9 | **existing higher** |
| `investment_contribution` | −71,744 | 129,726 | [−139,783, −18,462] | 1 / 11 | **existing higher** |
| `net_worth` | −73,223 | 137,435 | [−147,415, −18,988] | 2 / 10 | **existing higher** |
| **`pct_goals_met_by_deadline`** | **−0.01563** | 0.13682 | **[−0.07813, +0.04688]** | 1 / 2 | **inconclusive** |
| `debt_outstanding` | +423 | 1,694 | [0, 1,270] | 1 / 0 | inconclusive |
| `interest_paid` | +3,874 | 12,917 | [0, 10,952] | 2 / 0 | inconclusive |
| `overflow_retained_as_cash` | 0 | 0 | [0, 0] | 0 / 0 | inconclusive |
| `capacity_violation_months` | 0 | 0 | [0, 0] | 0 / 0 | inconclusive |
| `affordability_violations` | 0 | 0 | [0, 0] | 0 / 0 | inconclusive |

### 4.4 What the comparison says

**The existing LP's achievement advantage was largely manufactured.** Requiring the LP to respect
capacity costs it **−0.2476 achievement** (CI [−0.3405, −0.1538], 11 of 16 users worse) and
**−0.1448** on fully-funded goals. The mechanism is now measured rather than inferred: under
`share`+`legacy` the uninvestable demand is silently relabelled as savings and credited to goals,
so the existing LP was being paid for an allocation the environment refused to execute. Its
0.4928 should be read as "LP plan with the overflow credited as savings", not "LP plan".

**The benchmark is nevertheless the fairer object** and is not a failure: it eliminates the
capacity violation entirely (−1,438,590, 0 users improved in the wrong direction) with 0
affordability violations, at the cost of goal funding. It is the honest version of the LP for any
LP-vs-RL comparison.

**The deadline-success hypothesis survives.** The existing LP has the best deadline success in
both cohorts (0.16875 full, 0.19286 feasible), and the paired difference against the constrained
LP is **statistically indistinguishable** (CI [−0.07813, +0.04688]). The constrained LP still
ranks second-best in the feasible cohort (0.17500), ahead of `investment-only` and every RL seed.
So on this cohort the LP's deadline strength is **not** an artefact of the relabelling — but with
n = 16 and a CI that wide, that is evidence *for the hypothesis*, not a confirmed result.

**Zero-investment controls remain unchanged** (`urgency`, `need-proportional savings`: 0 overflow,
0.0000 deadline success in every arm).

---

## 5. Historical claim mapping

| # | Historical claim | Verdict |
|---|---|---|
| 1 | v6: "the LP plans 1,438,590 of investment the environment cannot accept" | **Unchanged, now strengthened** — measured at plan level: the LP plans **zero** monthly savings and 13,736.66/month investment, of which 10,130.92/month is relabelled |
| 2 | v6: "LP 0.4928 under `share`+`legacy`" | **Unchanged** (0.4928 reproduced exactly) but **re-characterised**: it is the achievement of the *unexecutable* plan under silent relabelling, not a valid LP benchmark |
| 3 | v6: "the LP has the best deadline success of any arm (0.1687)" | **Unchanged and now robust** — still best (0.16875 full / 0.19286 feasible), and statistically indistinguishable from the capacity-constrained LP (CI [−0.078, +0.047]) |
| 4 | v6: "`legacy` vs `retain_as_cash` vs `redirect_to_savings`" | **No longer the operative axis** for LP fairness — with the capacity constraint the overflow is ~0 in every mode, so the choice stops mattering for the constrained LP |
| 5 | v6: "the LP's plan is investment-heavy" | **Corrected in the strongest form**: it is *all*-investment (planned savings exactly 0.0) |
| 6 | v3/v4/v5: "the LP's investment is truncated by the environment's caps" | **Corrected** — the truncation is not marginal: ~74% of planned investment (10,130.92 / 13,736.66) is unimplementable |
| 7 | v6 §7: "the LP cannot be fairly compared without documenting the capacity gap" | **Resolved** — the constrained LP closes the gap; §4.3 is the fair comparison |
| 8 | Phase-H/v2: "LP vs RL is not comparable" | **Unchanged** — and now quantifiable: the existing LP's numbers are inflated by the relabelling |
| 9 | All prior RL-vs-LP orderings | **No longer comparable as stated** — they used the unexecutable LP plan |

---

## 6. Limitations

1. **n = 16 users (14 feasible).** CIs are wide; §4.3 verdicts that are "inconclusive" should be
   read as exactly that.
2. **One configuration, one budget.** `recommended()` only; no budget sweep (deliberately).
3. **The execution gap is measured but not decomposed** (§2.4 item 3). I have not isolated
   whether the per-goal cap, the EMI reservation or the encoder's relative weighting dominates.
4. **The LP is deterministic and one-shot**; the environment is monthly and stochastic. This is
   irreducible without re-deriving the LP as a multi-period stochastic program, which was not the
   task.
5. **The constrained LP is a benchmark, not a policy.** It scores lower than the unconstrained LP
   and no claim is made that it is better than any RL policy — the two are on different
   horizons and return assumptions.
6. **Fixed policies only.** Nothing here is evidence about a trained policy.
7. **`retain_as_cash` / `redirect_to_savings` are not adopted**; `legacy` remains the default and
   every historical output is unchanged.

---

## 7. Reproducing

```powershell
$py = "C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe"
Set-Location S:\fyp\GoalPilot_AI_Completed

& $py -m pytest tests\test_goalpilot_constrained_lp.py -q    # 11 passed in 3.06s
& $py audit_tools\56_constrained_lp_comparison.py            # sections 2-4
& $py -m pytest -q                                           # full suite, archived parity
```

Executed results:

```
$ python -m pytest tests\test_goalpilot_constrained_lp.py -q
11 passed in 3.06s

$ python -m pytest -q
164 passed in 552.95s (0:09:12)
```

164 = the 153 that passed before this change + the 11 constrained-LP tests. **Archived parity is
intact** (`test_goalpilot_env_parity.py` is among them: 100 users x 5 policies x 142 months,
reward to 1e-12), so the new module and its constraints changed no existing behaviour. Console:
`outputs/reward_design/v7/pytest_full_after_constrained_lp.txt`. Test inventory:
**164 RL + 26 LP = 190 tests, 0 failures, 0 errors, 0 skips.**
