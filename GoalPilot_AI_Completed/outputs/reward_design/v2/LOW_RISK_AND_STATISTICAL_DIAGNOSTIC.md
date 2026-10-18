# Diagnostic report — low-risk cohort, statistical validity, training sufficiency, fair comparison

**Date:** 2026-10-11 · **Version:** v2 (v1 artefacts untouched)
**Working copy:** `S:\fyp\GoalPilot_AI_Completed` · **Original:** `S:\fyp\GoalPilot_AI` (untouched)
**Interpreter:** `C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe` (3.13.7)

**No training was started.** All findings below come from existing artefacts plus read-only
diagnostics. The proposed runs in §4 are a plan awaiting approval.

---

## 0. Artefacts and commands

| Phase | Script | Outputs |
|---|---|---|
| 1 | `audit_tools/40_low_risk_diagnosis.py` | `low_risk_cohorts.csv`, `low_risk_user_details.csv`, `low_risk_action_trace.csv`, `low_risk_feasibility_test.csv`, `low_risk_diagnosis_summary.json`, `low_risk_diagnosis_console.txt` |
| 2 | `audit_tools/41_statistical_validity_audit.py` | `statistical_audit_paired_corrected_v1.csv`, `statistical_audit_summary_v1.json`, `statistical_audit_console.txt` |
| 3 | `audit_tools/42_learning_curve_audit.py` | `learning_curve_per_run_v1.csv`, `learning_curve_summary_v1.csv`, `learning_curve_audit_v1.json`, `learning_curve_console.txt` |
| 4 | `evaluation/fair_comparison_harness_v2.py` | `fair_comparison_metrics_v1.csv`, `fair_comparison_summary_v1.csv`, `fair_comparison_by_cohort_v1.csv`, `harness_console.txt` |
| 1 | `tests/test_goalpilot_env_semantics.py::test_zero_surplus_users_cannot_fund_goals_under_any_action` | **new** — 19 passed in 22.43s |

All new files are under `outputs/reward_design/v2/` and `outputs/evaluation/final_validation_v2/`.
Nothing under `outputs/reward_design/v1/`, `outputs/evaluation/final_validation_v1/` or
`training_logs/experiments/reward_experiment_v1/` was modified.

---

## 1. PHASE 1 — Why the low-risk cohort scores 0.0000

### 1.1 How the cohort is defined, and its true size

**The cohort is this audit's own binning, not a project definition.** `audit_tools/
34_reward_experiment_report.py` bins `risk_score` into `(-0.01, 0.33] → low`, `(0.33, 0.66] →
mid`, `(0.66, 1.01] → high`. No such cohort exists anywhere in the project source or data.

**Independent users: 6 of the 20 held-out users** — `USER_00013`, `USER_00031`, `USER_00034`,
`USER_00040`, `USER_00054`, `USER_00074`. Not 18 observations: the earlier report's cohort
figures were means over per-user rows, and any "n" implied by seed repetition would be
pseudo-replication (§2.1).

| Cohort | Users | Mean income | Mean expenditure | Mean existing EMI | **Mean free surplus** | Mean investment capacity | Mean goals |
|---|---:|---:|---:|---:|---:|---:|---:|
| **low** | **6** | 31,439 | 25,333 | 7,841 | **−1,735.84** | **0.000** | 4.17 |
| mid | 6 | 47,136 | 38,733 | 707 | +7,695.30 | 0.152 | 4.17 |
| high | 8 | 62,745 | 36,859 | 0 | +25,885.86 | 0.368 | 3.75 |

### 1.2 Per-user feasibility arithmetic

All six low-risk users, in full:

| User | Monthly surplus | Investment capacity | Σ inflated target | Max achievable from surplus over 142 months | Target ÷ capacity |
|---|---:|---:|---:|---:|---:|
| USER_00013 | **0** | 0.0 | 9,504,727 | **0** | undefined |
| USER_00031 | **0** | 0.0 | 1,874,533 | **0** | undefined |
| USER_00034 | **0** | 0.0 | 875,727 | **0** | undefined |
| USER_00040 | **0** | 0.0 | 2,086,226 | **0** | undefined |
| USER_00054 | **0** | 0.0 | 3,877,400 | **0** | undefined |
| USER_00074 | **0** | 0.0 | 3,531,725 | **0** | undefined |

`monthly_income − monthly_expenditure − monthly_emi <= 0` for every one of them, so the
environment grants a **discretionary budget of exactly zero**; and `investment_capacity_ratio
= 0`, so the investment channel is unavailable even if there were budget.

### 1.3 The decisive test: trained policies vs a maximally aggressive action

Same users, same environment, same 142 months:

| Action | Weighted achievement | Funded (₹) | Loan principal (₹) | Net worth (₹) |
|---|---:|---:|---:|---:|
| `archived_v1` trained (seed 7) | **0.0000** | 0 | 0 | 55,636.68 |
| `candidate_a` trained (seed 7) | **0.0000** | 0 | 0 | 55,636.68 |
| `candidate_b` trained (seed 7) | **0.0000** | 0 | 0 | 55,636.68 |
| **AGGRESSIVE** all-channels savings-only | **0.0000** | 0 | 0 | 55,636.68 |
| **AGGRESSIVE** all-channels mixed + loan | **0.0000** | 0 | 0 | 55,636.68 |
| *same aggressive action, mid cohort* | 0.4898 | 1,073,400 | 42,078 | 1,383,029 |
| *same aggressive action, high cohort* | 0.7267 | 2,915,221 | 92,393 | 5,100,533 |

The probe is sensitive — the identical aggressive action funds ₹2.9M of goals for high-risk
users. It is the *users*, not the probe, that cannot fund anything.

### 1.4 Conclusion, and the hypotheses eliminated

**Cause: expected financial infeasibility.** These households have no discretionary cash flow,
so no allocation policy of any kind can fund a goal. Every alternative hypothesis is refuted by
the table above:

| Hypothesis | Verdict | Evidence |
|---|---|---|
| Policy inaction (agent learned to do nothing) | **Refuted** | A maximally aggressive action also achieves 0.0000 |
| Observation/action design preventing allocation | **Refuted** | The same observation/action space yields 0.4898–0.7267 on other cohorts |
| Risk constraints in the reward suppressing investment | **Refuted** | Achieved with `reward_version` varied across all three versions, all 0.0000 |
| Incorrect cohort evaluation / metric bug | **Refuted** | Cohort derived from `risk_score` data, not from outcomes; the harness independently reproduces 0.0000 and an identical net worth via `surplus>0` membership |
| Unaffordable goals (targets exceed plausible means) | **Partially relevant** | Targets are ₹0.88M–₹9.5M against zero capacity, but the binding constraint is the zero budget, not the target size |
| Learning failure specific to these users | **Refuted** | A zero budget leaves the policy with no action that changes the outcome |

So the earlier characterisation in `REWARD_EXPERIMENT_REPORT.md` §4.2 — "a subpopulation
collapse, unexplained" — **was wrong**, and I am correcting it here. It is not a collapse and not
unexplained: it is environmental, and it is identical across reward versions because the
trajectory is fully determined by the environment when the budget is zero (which is also why the
net worth was identical to the rupee across three independently trained policies).

### 1.5 No implementation defect found — but the behaviour is now pinned

No defect exists to fix, so no defect regression test was added. Instead the behaviour is pinned
as **intentional** in
`tests/test_goalpilot_env_semantics.py::test_zero_surplus_users_cannot_fund_goals_under_any_action`,
which asserts for every zero-surplus user and six different action vectors that `surplus`,
`discretionary_budget`, savings and investment contributions and `new_loan_principal` are all
zero and that goal funding never changes from reset. Verified: **19 passed**.

### 1.6 A population-data observation that needs validation (not a code defect)

30% of the held-out users (6/20) have `monthly_emi > monthly_income − monthly_expenditure`, i.e.
their existing loan instalment exceeds their free cash flow. The existing-EMI cap
(`emi_income_ratio_cap = 0.35`) permits EMI up to 35% of income, so these profiles are
internally legal but describe households in structural deficit. Whether the synthetic generator
*intends* to include cash-flow-negative households is unverified and should be confirmed before
any population-level claim is made.

---

## 2. PHASE 2 — Statistical validity audit

### 2.1 The flaw, confirmed

`audit_tools/34_reward_experiment_report.py` bootstrapped over **60 (user, seed) rows as if they
were 60 independent observations**. They are the same 20 users observed three times. That is
**pseudo-replication**: the confidence intervals were too narrow.

### 2.2 Corrected analysis

Three methods, applied to both an all-users population (n=20) and a pre-specified
feasibility-eligible population (`monthly_surplus > 0`, n=14 — eligibility defined by an ex-ante
constraint, never by outcomes):

- **A. as published** — naive bootstrap over 60 rows (retained for comparison)
- **B. cluster bootstrap** — resample the 20 *users*, keeping each user's three seeds together
- **C. user-mean paired t-test** — average each user across seeds, paired t-test on n=20

| Quantity | Value |
|---|---|
| Independent sample size per arm | **20 users** (14 feasibility-eligible) |
| Observations if pseudo-replicated | 60 (spurious) |
| Median CI width, cluster ÷ naive | **1.016** |
| **Maximum** CI width, cluster ÷ naive | **1.327** (i.e. the published CI was up to 33% too narrow) |
| Comparisons where the verdict changes between methods | **4 of 36**, all on `goal_level_shortfall` |

Seed variability is reported per comparison in
`statistical_audit_paired_corrected_v1.csv` (`seed_variability_sd`), and for training returns in
`learning_curve_summary_v1.csv` (last-50-episode SD across seeds: 1.00 / 7.89 / 356.28 for
`archived_v1` / `candidate_a` / `candidate_b`).

### 2.3 What survives, what changes

**Survives every method, both populations** (cluster CI and paired t agree with the published
claim):

| Comparison | Metric | Mean diff | Cluster CI95 | Paired t p |
|---|---|---:|---|---:|
| `archived_v1` → `candidate_a` | weighted achievement | +0.0821 | [0.041, 0.126] | 0.0016 |
| `archived_v1` → `candidate_a` | % fully funded | +0.1050 | [0.050, 0.164] | 0.0026 |
| `archived_v1` → `candidate_a` | % met by deadline | +0.0486 | [0.007, 0.096] | 0.0518 |
| `archived_v1` → `candidate_b` | weighted achievement | +0.0684 | [0.029, 0.111] | 0.0052 |
| `archived_v1` → `candidate_a` | interest paid | +8,053 | [2,894, 13,939] | 0.0123 |
| `candidate_a` → `candidate_b` | % fully funded | −0.0542 | [−0.083, −0.028] | 0.0015 |

On the **eligible** population the effects are larger: `archived_v1` → `candidate_a` achievement
**+0.1173** [0.067, 0.169], fully funded **+0.1500** [0.081, 0.221].

**Changes under correction — a genuine new finding:**

| Comparison | Metric | Published (naive) | Corrected (cluster + t) |
|---|---|---|---|
| `archived_v1` → `candidate_b` | rupee shortfall | inconclusive | **favours `candidate_b`** |
| `candidate_a` → `candidate_b` | rupee shortfall | inconclusive | **favours `candidate_b`** |

So the trade-off between the candidates is **two-dimensional and was previously mis-stated**:
`candidate_a` funds **more goals** (significantly more by count), while `candidate_b` reduces
**total rupee shortfall** significantly more (mean −₹284,370 vs `candidate_a`; −₹295,901 vs
`archived_v1`). Breadth versus depth. Neither dominates.

**Still not significant under any method:** net worth, in every pair, in both populations
(`candidate_a` vs `candidate_b` +₹77,135, CI [−20,303, +253,821], p=0.37). `candidate_b`'s
apparent wealth advantage remains unproven.

### 2.4 Test-set hygiene — a real breach I must declare

- ✅ Reward coefficients were fixed **a priori** in `REWARD_EQUATIONS_v1.md` and never adjusted
  after seeing held-out results. The budget (50,000) and seed set (7, 17, 27) were fixed before
  results were observed.
- ❌ **`candidate_a` was recommended *after* observing its held-out performance. That is model
  selection on the held-out set**, and it is precisely what the constraint forbids.

Consequence: the recommendation in `REWARD_EXPERIMENT_REPORT.md` §7 must be treated as
**provisional and unconfirmed**. Confirming it requires re-evaluation on a split that was not
used for that choice (§5, P2). I am flagging this rather than quietly re-labelling it.

---

## 3. PHASE 3 — Training sufficiency (assessment only)

### 3.1 Learning curves plateau by 50,000 timesteps

From the nine per-episode logs (353 episodes each). Slope is a linear fit over the **last 100
episodes**, with its standard error:

| Reward version | mean first-50 return | mean last-50 return | tail slope / episode | slope t-stat | runs still improving |
|---|---:|---:|---:|---:|---:|
| `archived_v1` | −12.66 | −14.46 | −0.028 | 1.33 | **0 / 3** |
| `candidate_a` | −55.18 | −52.02 | −0.033 | 1.39 | **0 / 3** |
| `candidate_b` | 4,502.57 | 10,184.35 | −58.78 | 0.82 | **0 / 3** |

No run has a tail slope distinguishable from zero (`|t| > 2` absent everywhere). **All three
reward versions have plateaued at 50k.** This is direct evidence against assuming that more
timesteps will help: the curves are flat, and the residual per-episode noise (SD 7.2 / 35.8 /
72,493) is far larger than any remaining trend.

### 3.2 Measured throughput and extrapolated cost

Measured **585.9 steps/s** (3 instrumented runs, 16 cores, no GPU):

| Budget | Per run | 3 matched seeds | 3 seeds × 2 budgets |
|---|---:|---:|---:|
| 50,000 | 1.42 min | 4.27 min | — |
| 150,000 | 4.27 min | 12.80 min | |
| 300,000 | 8.53 min | 25.60 min | **≈ 38.4 min training** |

Plus ≈6 min of evaluation (9 checkpoints × 20 users × 142 months). Each single run fits inside
the 15-minute background cap, so the design must be staged per run as in
`audit_tools/33_reward_experiment.py`.

### 3.3 Proposed controlled budget comparison — **not launched**

| Element | Specification |
|---|---|
| Arm | `candidate_a` only (the provisional leader), fixed configuration `GoalPilotConfig.recommended().replace(reward_version=REWARD_VERSION_A)` |
| Budgets | 50,000 (already trained), 150,000, 300,000 |
| Seeds | 7, 17, 27 — matched with the existing 50k runs |
| New runs required | 6 (150k × 3, 300k × 3) ≈ 38 min training + ≈6 min evaluation |
| Evaluation | identical harness, same 20 held-out users, pre-specified feasibility-eligible population, **cluster bootstrap** (per §2) |
| Primary metric | weighted goal achievement on the 14 feasibility-eligible users |
| **Stopping criterion** | Stop extending when **both**: (a) the tail-100 slope t-stat `|t| < 2` (curve flat), **and** (b) the change in weighted achievement from the previous budget is **smaller than the across-seed SD** of that budget. Stop immediately if any budget *degrades* achievement beyond the seed SD. |
| Pre-registration | the criterion above is fixed before the runs, so the decision cannot be made post hoc |

Two cautions stated in advance: (i) the plateau in §3.1 predicts these runs may simply confirm
50k is sufficient, which is a useful negative result; (ii) completion of P1 and P2 below takes
priority, because a stronger policy is worthless if the strategy-space question in §4 is open.

---

## 4. PHASE 4 — Fair comparison across savings-only / investment-only / rule-based / LP / RL

### 4.1 Harness

`evaluation/fair_comparison_harness_v2.py` — 10 strategies, one configuration
(`GoalPilotConfig.recommended()`), identical 20 held-out users, identical goal definitions,
income/expense scenarios, market paths, accounting, targets and reserve policy. 200 rollouts.
Integrity: **0 affordability violations**, max budget-check residual **2.9e-11**, LP solved
`optimal` for **20/20** users.

### 4.2 Results — feasibility-eligible users (n = 14)

| Strategy | Weighted achievement | % fully funded | % by deadline | Shortfall (₹) | Net worth (₹) | Interest (₹) | Downside (₹) |
|---|---:|---:|---:|---:|---:|---:|---:|
| **Investments only** | **0.6161** | **0.4774** | **0.2155** | 7,465,825 | 3,537,838 | 0 | 1,093,904 |
| **LP optimizer plan** | 0.6113 | 0.4298 | 0.1774 | 7,251,945 | **3,579,144** | 5,143 | 1,158,712 |
| RL `candidate_a` seed7 | 0.5963 | 0.4964 | 0.1917 | 7,646,943 | 3,404,120 | 16,908 | 942,475 |
| RL `candidate_a` seed27 | 0.5885 | 0.4905 | 0.1690 | 7,338,659 | 3,526,045 | 27,759 | 1,118,811 |
| **Savings only** | 0.5873 | 0.4536 | **0.2155** | 7,807,041 | 2,982,685 | 0 | **290,801** |
| RL `candidate_a` seed17 | 0.5397 | 0.4536 | 0.1821 | 8,176,709 | 3,268,595 | 14,167 | 737,380 |
| RL `archived_v1` seed7 | 0.4896 | 0.3690 | 0.1595 | 7,749,054 | 3,268,973 | 8,000 | 721,500 |
| RL `archived_v1` seed27 | 0.4561 | 0.3131 | 0.0905 | 7,089,223 | 3,555,903 | 14,810 | 1,145,838 |
| RL `archived_v1` seed17 | 0.4268 | 0.3083 | 0.0845 | 8,373,454 | 3,367,737 | 1,512 | 857,415 |
| Rule-based urgency | 0.3713 | 0.0714 | **0.0000** | **6,863,977** | 2,982,685 | 0 | **290,801** |

Zero-surplus cohort (n = 6): **0.0000 achievement and ₹55,637 net worth for all ten strategies**,
including the deterministic LP — the independent confirmation of §1.4.

### 4.3 The finding that matters most

**No RL policy beats the simple baselines on goal achievement.** The best RL run (0.5963) sits
*below* both `Investments only` (0.6161) and the LP plan (0.6113), and only 0.009 above
`Savings only` (0.5873) — while RL's own seed spread on the same cohort is 0.054
(0.5397–0.5963), **six times larger than its margin over `Savings only`**.

Therefore:

- The v1 claim that `candidate_a` "improves every goal-attainment metric" is **true only
  relative to the archived reward**, holding the RL arm fixed. It is **not** evidence that RL
  adds value over the strategy space.
- There is **no evidence here that RL provides adaptive allocation beyond the LP or simple
  rules** — the question the brief set out to test. Answering it negatively is the honest
  result.
- `Savings only` is a strong risk-adjusted baseline: joint-best deadline success with a third
  of `Investments only`'s downside exposure (₹290,801 vs ₹1,093,904) and lower net worth.
- **The rule-based baseline is mine and it is bad** — 0.0000 deadline success, worse than doing
  nothing strategically. That is a defect in my rule (it commits the entire budget to a single
  goal), not a finding about rule-based strategies. It must be redesigned before it is used as a
  comparison point.

### 4.4 Unavoidable differences, documented

| Difference | Detail |
|---|---|
| LP is one-shot, RL is monthly | The LP returns a constant monthly savings/investment amount per goal plus a loan; it is mapped onto the environment's monthly `share` weights. The environment still enforces its own `max_new_loan`, EMI cap and affordability constraints, so the LP plan can be truncated |
| Loan rate | LP uses a fixed `loan_annual_rate = 0.12`; the environment uses the month's actual `walr_monthly` path |
| LP is deterministic | It plans against assumed returns; RL and the rule react to the realised market path month by month |
| Rule-based is bespoke | Written for this audit; not a published heuristic |
| Seedless strategies | `Savings only`, `Investments only`, LP and the rule are deterministic, so they have no seed spread to report, unlike the RL arm |

---

## 5. Prioritised next-step plan

| Priority | Action | Why | Status |
|---|---|---|---|
| **P0** | **Do not launch the budget experiment yet.** | §4.3 shows the RL policy is not the binding constraint; spending 38 min of training to make a dominated policy slightly better is premature | — |
| **P1** | Diagnose why a constant `Investments only` action beats every RL policy and matches the LP. Hypothesis: with `share` semantics the investment channel's capacity overflow returns to savings, so it acts as "allocate fully, then let it grow"; and the per-goal cap (R-08) releases money that neither the rule nor RL reallocates | Explains the strategy-space order and tells us whether the environment, not the learner, is the problem | not started |
| **P2** | Confirm or reject `candidate_a` on a **fresh 20-user split** (e.g. a held-out block never used in this audit) with the cluster-bootstrap methodology and the feasibility-eligible population pre-specified | Removes the §2.4 test-set-selection breach and the two-dimensional breadth/depth trade-off will be re-tested cleanly | not started |
| **P3** | Run the §3.3 budget comparison (150k, 300k × 3 seeds) with the pre-registered stopping criterion | Directly answers whether 50k suffices; the plateau suggests it may | planned, blocked on P1/P2 |
| **P4** | Redesign the rule-based baseline (e.g. spread across goals by urgency rather than concentrating) before quoting it | Its 0.0000 deadline success is a defect in the baseline, not a result | not started |
| **P5** | Validate the synthetic population's income / expenditure / EMI distributions | 30% of held-out users have negative free cash flow with EMI above it; population-level claims depend on whether that is intended | not started |
| **P6** | Re-run `evaluation/run_all.py` to refresh the pre-fix CSVs | They still reflect the pre-R-01/R-02/R-03 code; currently preserved deliberately as the historical record | deferred |

---

## 6. Corrections to my earlier statements

| Earlier claim | Correction |
|---|---|
| "The low-risk group scores 0.0000 — a subpopulation collapse, **unexplained**" | **Explained**: expected financial infeasibility. Six users have a zero discretionary budget and zero investment capacity. All ten strategies, including a maximally aggressive action and the LP, also score 0.0000 there |
| "`candidate_a` improves **every** goal-attainment metric" | True **only against the archived reward**. Against the strategy space, `Investments only` and the LP both score higher |
| "`candidate_a` is significantly ahead of `candidate_b` on any attainment metric" | Still true for **goal counts** (% fully funded). But `candidate_b` is significantly better on **rupee shortfall** once the pseudo-replication is corrected — a breadth/depth trade-off, not a dominance |
| "CI = bootstrap over 60 pairs" | Pseudo-replicated. Corrected CIs are a median 1.6% and up to 32.7% wider; independent n = 20 |
| "Recommended: retain `candidate_a`" | **Provisional only.** It was selected after seeing held-out results, which is test-set selection. Requires the P2 confirmation |

---

## 7. Limitations

1. **No new training was run**, so every statement about training sufficiency is inference from
   the existing nine curves, not a controlled budget experiment.
2. **The feasibility-eligible population (n=14) is small.** Effects are larger there, but the CIs
   are correspondingly wide.
3. **Cohort binning is this audit's own** and the low/mid/high split happens to coincide exactly
   with the zero-surplus split on this 20-user cohort (6 = 6). That coincidence is a property of
   this synthetic sample, not a general identity.
4. **Eligibility uses `monthly_surplus > 0`,** a necessary but not sufficient condition for goal
   feasibility; some eligible users have capacity far below their targets.
5. **One environment implementation** underlies every comparison; its design choices (R-08
   non-reallocation in particular) bound what any policy can achieve.
6. **The archived checkpoint's wealth columns remain incomparable** to ledger-accounting arms.
7. **PPO remains far from solving the task**: the best arm funds under half of goals and meets
   ~22% by deadline at best.
