# Evaluation methodology and results

**Date:** 2026-10-11 · **Status of this document:** all numbers below are copied from CSVs and
consoles produced by executed runs. Nothing is projected. Sources are given per table.

---

## 1. Methodology

### 1.1 Cohorts

| cohort | size | source | rule |
|---|---:|---|---|
| RL sample (all) | 100 users, 390 goals | `rl_sample_*.csv` | 3–5 goals each, mean 3.9 |
| Train / test (original) | 80 / 20 | `rl_train_test_user_split.csv` | 80/20 split |
| **Fresh split** | **48 train / 16 validation / 16 test** | `fresh_split_v1_manifest.json` | 100 users **minus the 20 previously used for selection** (contaminated), re-partitioned deterministically at seed 20261011 with no overlap |

The 20 excluded users were the evaluation set in which `candidate_a` was originally chosen; that
was **test-set selection** (declared in `reward_design/v2/LOW_RISK_AND_STATISTICAL_DIAGNOSTIC.md`
§2.4). The fresh split removes the leakage.

### 1.2 Fairness rules

- Identical users, goals, targets, market path and initial conditions across arms.
- One environment configuration per comparison (`recommended()` unless stated).
- RL arms run **only** under their training semantics; a script asserts
  `action_mode == share and overflow_policy == legacy` before loading a checkpoint. No checkpoint
  is reinterpreted under `mix` or `magnitude`.
- Fixed-policy arms (savings-only, investment-only, uniform mix, urgency) use the same action
  contract; the LP arm is the capacity-constrained plan encoded into that contract.
- No arm uses privileged information. Any oracle/upper-bound strategy is excluded from
  deployable-performance claims.

### 1.3 Metrics

`weighted_goal_achievement` (priority-weighted, capped at target), `pct_goals_fully_funded`,
`pct_goals_met_by_deadline`, `goal_level_shortfall`, savings and investment contributions,
`investment_cap_overflow`, `capacity_violation_months` / `affordability_violations`,
final cash, portfolio, net worth, loan balance, principal, interest, investment gain, downside
exposure.

### 1.4 Uncertainty

User-level bootstrap (2,000–20,000 resamples, seeded) for spread; **user-clustered** bootstrap
(resampling users, keeping all of a user's seeds together) plus a paired t-test on user means for
paired differences. Repeated rolls of the same user are never treated as independent
observations. A published CI-width audit found that naive resampling understates CI width by up
to 33 % (`reward_design/v2/LOW_RISK_AND_STATISTICAL_DIAGNOSTIC.md` §2.2), which is why the
clustered variant is reported.

---

## 2. Regression guarantees

| check | result | source |
|---|---|---|
| Archived parity: 100 users × 5 policies × 142 months, reward to 1e-12, state to 1e-9 | **passes** | `tests/test_goalpilot_env_parity.py` (part of the 164) |
| Archive verification: 5,541 field comparisons vs historical CSVs | **0 mismatches** | `outputs/evaluation/archive_verification.json` |
| LP model equivalence: constrained module with both switches off == original optimizer | rtol 1e-9 on objective, achievement, shortfall, every allocation column | `tests/test_goalpilot_constrained_lp.py` |
| Budget identity every month across all arms | residual < 1e-6 | `CONSTRAINED_LP_BENCHMARK.md` §2.2 |
| Large-CSV identities (1,430,000 rows × 2 files) | portfolio / market-coupling / cross-file all **0 failures** | `outputs/audit/large_csv_validation_v1/` |

---

## 3. The capacity finding (v6 → v7)

The RL environment caps monthly investment at
`investment_capacity_ratio × surplus available after loan commitments` (`≤ 0.4988` in this
population). The **existing LP does not contain that constraint**, so it plans investment the
environment can never execute — and under `share`+`legacy` the refused demand is silently
relabelled as savings and credited to goals.

Per-month averages across the 16 fresh test users (`constrained_lp_plan_vs_executed_v1.csv`):

| arm | planned savings /mo | planned investment /mo | investment permitted | executed investment /mo | executed savings /mo | overflow /mo |
|---|---:|---:|---:|---:|---:|---:|
| `existing_LP_unconstrained` | **0.0** | **13,736.66** | n/a | 2,023.56 | 6,914.10 | **10,130.92** |
| `constrained_LP` | 9,848.47 | 4,096.73 | 4,096.73 | 1,518.32 | 4,255.95 | **0.000058** |

Adding the capacity constraint removes ~10,131/month of unimplementable investment demand
(equivalently 1,438,590 per cohort) and lowers the existing LP's achievement from 0.4928 to
0.2452 — a paired −0.2476 (CI [−0.3405, −0.1538], 11 of 16 users worse). The earlier
"LP advantage" was therefore **largely an accounting artefact**, not a better plan.

---

## 4. Baseline / LP / constrained LP / RL comparison

### 4.1 v7 cohort (16 fresh test users, 13 arms, `recommended()`)

| policy | achievement | fully funded | by deadline | shortfall | cap overflow | net worth |
|---|---:|---:|---:|---:|---:|---:|
| RL `archived_v1` seed7 | 0.5908 | 0.4813 | 0.1146 | 8,589,238 | 388,382 | 2,748,925 |
| `investment-only` | 0.5800 | 0.4656 | 0.1427 | 8,567,394 | 1,479,048 | 2,751,777 |
| `mixed allocation` | 0.5800 | 0.4656 | 0.1427 | 8,567,394 | 439,156 | 2,751,777 |
| `uniform savings` | 0.5584 | 0.4531 | 0.1427 | 8,783,226 | 0 | 2,363,890 |
| `existing_LP_unconstrained` | 0.4928 | 0.3771 | **0.16875** | 8,713,979 | 1,438,590 | 2,680,083 |
| `constrained_LP` | 0.2452 | 0.2323 | 0.15313 | 9,192,529 | **0** | 2,606,859 |
| `urgency` / `need-proportional` | 0.4051 / 0.3211 | 0.0625 | **0.0** | 8,125,197 | 0 | 2,363,890 |

Source: `outputs/evaluation/final_validation_v7/constrained_lp_summary_v1.csv`.

**What this says.** The best simple policy and the single RL seed are close (0.5800 vs 0.5908,
one seed — not a claim). The *unconstrained* LP's 0.4928 is achieved by an unexecutable plan; the
honest LP is 0.2452 on this cohort. Zero-investment rules have **zero** deadline success. In the
structurally infeasible cohort every one of the 13 arms scores exactly 0.0000 — nothing a policy
can do differs there.

### 4.2 Fresh-split reward comparison at 50k (v3)

| metric (paired, `candidate_a` − `archived_v1`) | v1 (contaminated) | v3 (fresh split) |
|---|---:|---:|
| weighted achievement | +0.0821 | **+0.0069**, CI [−0.0268, +0.0444], p = 0.72 |
| % fully funded | +0.1050 | −0.0184 |
| % by deadline | +0.0486 | +0.0247 |

Source: `outputs/reward_design/v3/FRESH_SPLIT_CONFIRMATION.md`.
The apparent reward-version advantage **did not reproduce** on an uncontaminated split. **No
reward version has been selected.**

### 4.3 Controlled PPO training and held-out evaluation (v8)

Six validation-selected PPO policies (2 reward versions × 3 matched seeds, 50,000 timesteps each)
versus five rule baselines and the capacity-constrained LP, all on the **same 16 fresh test
users**. Full detail in §6 and `outputs/evaluation/final_validation_v8/`.

---

## 5. Ablations and sensitivity

| factor | setting | effect | source |
|---|---|---|---|
| Action mode | `magnitude` flat-0.25 vs `share` flat-0.25 | 0.17960 → 0.19292 achievement; 782,168 → 694,266 unallocated | `outputs/evaluation/action_mode_comparison.csv` |
| Overflow policy | `legacy` vs `retain_as_cash` vs `redirect_to_savings` | investment-only allocation 386,883 → 496,041 (+28 %) | `reward_design/v5/LP_ENCODING_AND_OVERFLOW_POLICY.md` §1.4 |
| Per-goal cap reallocation (R-13) | off → on | savings 0.5873 → 0.6333; investment/mixed 0.6161 → 0.6545; LP 0.6113 → 0.6384; idle budget 26–29 % → ~3 % | `reward_design/v3/P1A_R13_FIX_AND_POPULATION_VALIDATION.md` §1.2 |
| Goal credit | `face_value` vs `market_weighted` | `face_value` makes savings-only and mixed identical (F-01); `market_weighted` breaks the degeneracy for a real reason and keeps `Σ goals ≤ cash + portfolio` | `docs/audit/AUDIT_REPORT.md` F-01 |
| Investment capacity | ×1 vs ×0 (deterministic what-if) | ×0 → executed investment exactly 0; shortfall never decreases | `tests/test_goalpilot_explain.py` |
| Emergency reserve | 0 vs 6 months | changes the investable pool and every allocation | `goalpilot_config.emergency_months` |

**Capacity sensitivity is a design fact, not a tuned optimum.** `investment_capacity_ratio`
ranges 0.0000–0.4988 with 79 distinct values in this population; the production default is
unchanged and no capacity value was chosen to maximise a score.

---

## 6. Controlled PPO training under `recommended()` — v8

Executed 2026-10-11. Sources: `outputs/evaluation/final_validation_v8/ppo_v8_{summary,detail,
across_seeds,paired,digest}` and `outputs/reward_design/v8/PPO_TRAINING_AND_EVALUATION.md`
(rendered from those files by `audit_tools/81_ppo_v8_report.py`).

### 6.1 Training

`GoalPilotConfig.recommended()`; reward versions `archived_v1` and `candidate_a` (the archived
reward was never modified); seeds 7 / 17 / 27; **50,000 timesteps per run**; 48 training users;
checkpoint selection by `EvalCallback` on the **16 validation users only**.

| reward version | seed | seconds | steps/s | episodes | mean train return |
|---|---:|---:|---:|---:|---:|
| `archived_v1` | 7 | 503.2 | 99 | 353 | −13.575 |
| `archived_v1` | 17 | 407.6 | 123 | 353 | −14.384 |
| `archived_v1` | 27 | 409.6 | 122 | 353 | −14.379 |
| `candidate_a` | 7 | 413.2 | 121 | 353 | −54.063 |
| `candidate_a` | 17 | 769.4 | 65 | 353 | −55.180 |
| `candidate_a` | 27 | 295.5 | 169 | 353 | −54.552 |

Hardware: CPU only (torch CPU build); 46.6 minutes of training wall time across the six runs.
Throughput varies with machine load (65–169 steps/s), measured separately by
`audit_tools/82_ppo_throughput_probe.py`.

> **Budget justification.** A 100k budget was attempted first and could not complete within the
> host's 15-minute background-command limit, so the budget was set to 50k — which also matches the
> v1/v3 runs exactly and makes v8 directly comparable with them. All six runs were completed; none
> was truncated and none was hand-picked.

### 6.2 Held-out results (16 fresh test users, 14 feasibility-eligible)

| arm | seeds | achievement | fully funded | by deadline | net worth | shortfall | cap overflow | interest paid |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `investment-only` | — | **0.5800** | 0.4656 | 0.1427 | **2,751,776.94** | 8,567,393.74 | 1,479,047.97 | 0 |
| `mixed allocation` | — | **0.5800** | 0.4656 | 0.1427 | **2,751,776.94** | 8,567,393.74 | 439,155.53 | 0 |
| `uniform savings` | — | 0.5584 | 0.4531 | 0.1427 | 2,363,889.62 | 8,783,225.85 | 0 | 0 |
| **RL `archived_v1`** | 3 | 0.4842 | 0.3674 | 0.1083 | 2,659,502.00 | 8,973,439.60 | 776,631.22 | 8,637.94 |
| **RL `candidate_a`** | 3 | 0.4398 | 0.3059 | 0.0892 | 2,633,769.57 | 8,862,778.94 | 355,556.28 | 20,046.80 |
| `urgency` | — | 0.4051 | 0.0625 | **0.0000** | 2,363,889.62 | 8,125,196.71 | 0 | 0 |
| `need-proportional savings` | — | 0.3211 | 0.0625 | **0.0000** | 2,363,889.62 | 8,125,196.71 | 0 | 0 |
| `constrained_LP` | — | 0.2452 | 0.2323 | **0.1531** | 2,606,859.50 | 9,192,529.49 | 0.0082 | 11,357.39 |

**0 affordability violations** across every arm; maximum budget-identity residual **7.28e-12**.

Across-seed standard deviation (achievement): `archived_v1` 0.0554, `candidate_a` 0.0852 — the
seed spread is comparable to the differences being discussed, which is why no ranking is claimed
between them.

### 6.3 Paired, user-level differences (RL mean over seeds minus each baseline)

Direction-aware (for `investment_cap_overflow` **lower** is better). Selected rows:

| RL arm | baseline | metric | better | mean diff | CI95 | significant |
|---|---|---|---|---:|---|---|
| `archived_v1` | `uniform savings` | achievement | uniform savings | −0.0742 | [−0.1187, −0.0298] | yes |
| `archived_v1` | `investment-only` | achievement | investment-only | −0.0957 | [−0.1423, −0.0497] | yes |
| `archived_v1` | `investment-only` | fully funded | investment-only | −0.0983 | [−0.1795, −0.0302] | yes |
| `archived_v1` | `uniform savings` | by deadline | — | −0.0344 | [−0.0813, 0.0090] | **inconclusive** |
| `archived_v1` | `constrained_LP` | achievement | **RL** | +0.2390 | [0.1516, 0.3214] | yes |
| `archived_v1` | `need-proportional` | achievement | **RL** | +0.1632 | [0.0628, 0.2604] | yes |
| `archived_v1` | `urgency` | achievement | **RL** | +0.0791 | [0.0076, 0.1504] | yes |
| `archived_v1` | `constrained_LP` | by deadline | — | −0.0448 | [−0.1083, 0.0174] | **inconclusive** |
| `candidate_a` | `investment-only` | achievement | investment-only | −0.1402 | [−0.1876, −0.0948] | yes |
| `candidate_a` | `constrained_LP` | achievement | **RL** | +0.1945 | [0.1024, 0.2861] | yes |
| `candidate_a` | `urgency` | achievement | — | +0.0347 | [−0.0442, 0.1209] | **inconclusive** |

Across all 204 paired rows: RL better in **14**, baseline better in **15**, inconclusive in
**53** (the remainder involve non-headline metrics).

### 6.4 What the v8 run supports

1. **RL does not beat the simple baselines.** The best mean achievement is `investment-only`
   (0.5800); the best RL arm is `archived_v1` at 0.4842 — *below* it by 0.0957, with a paired
   interval that excludes zero. This is reported as a negative result.
2. **RL does beat the constrained LP and the weak rules** on achievement: +0.2390 (LP),
   +0.1632 (need-proportional), +0.0791 (urgency), all significant.
3. **Deadline success is where RL is weakest.** `constrained_LP` has the best deadline rate
   (0.1531); RL `archived_v1` reaches 0.1083 — statistically indistinguishable from
   `uniform savings` / `investment-only` (interval spans zero) but below the LP.
4. **RL invests more and pays more interest** than the savings rules (overflow 776,631 and
   interest 8,638 for `archived_v1` versus 0 and 0 for `uniform savings`), and it earns a higher
   net worth for it (2,659,502 vs 2,363,890).
5. **`candidate_a` is not better than `archived_v1`** on any headline metric here (−0.0444
   achievement, larger across-seed spread), which is consistent with the v3 fresh-split finding
   that the candidate's apparent advantage did not reproduce. **No reward version is selected.**
6. **The capacity constraint is the reason the LP scores 0.2452**: it is the only arm with
   essentially zero cap overflow (0.0082) and it still delivers the best deadline success — the
   LP trades goal *amount* for goal *timing*.
7. **No superiority claim exceeded the evidence.** Where an interval spans zero the arms are
   reported as indistinguishable.

---

## 7. Honest summary of what the numbers support

1. **The corrected ledger and the archived environment reproduce the history exactly** (1e-12).
2. **The capacity constraint is the single most consequential correction**: it removes all
   unimplementable investment demand and roughly halves the unconstrained LP's apparent
   achievement.
3. **The LP's deadline success is a genuine property** that survives the correction — but with
   n = 16 the paired difference against the constrained LP is not statistically distinguishable.
4. **RL does not beat the simple baselines.** On the v8 held-out cohort the best arm is
   `investment-only` (0.5800) and the best RL arm is 0.4842 — a significant shortfall. The reward
   version gains seen on the contaminated cohort did not reproduce, and `candidate_a` is not
   better than `archived_v1`. RL *does* beat the constrained LP (+0.2390) and the weak rules.
5. **Rule-based urgency is the worst option on deadline success** (exactly 0.0), because it
   concentrates the budget on one goal.
6. **Structurally infeasible users are policy-invariant**: every arm scores 0.
