# Controlled reward-function experiment — results and recommendation

**Date:** 2026-10-11 · **Experiment ID:** `reward_experiment_v1`
**Working copy:** `S:\fyp\GoalPilot_AI_Completed` · **Original:** `S:\fyp\GoalPilot_AI` (untouched)
**Interpreter:** `C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe` (3.13.7)

---

## 1. What was run

| Item | Value |
|---|---|
| Environment | `GoalPilotConfig.recommended()` — `share` action semantics, `market_weighted` crediting, ledger accounting, inflated targets, 6-month reserve |
| Reward versions | `archived_v1`, `candidate_a`, `candidate_b` (equations in `REWARD_EQUATIONS_v1.md`) |
| Policies trained | **9 fresh PPO policies** — 3 versions x 3 matched seeds (7, 17, 27). No pre-existing checkpoint was used for any arm |
| Training budget | **50,000 timesteps each**, 353 episodes each — identical for all nine, and the same budget the historical checkpoint was trained with |
| Hyper-parameters | identical: `MlpPolicy`, `n_steps=256`, `batch_size=64`, `n_epochs=4`, `gamma=0.99`, `lr=3e-4`, `net_arch=[128,128]` |
| Train / held-out | 80 / 20 users, same split file for every arm |
| Evaluation | deterministic, same 20 held-out users, 142-month episodes, identical metric set |
| Historical reference | archived checkpoint, evaluated **separately** under `GoalPilotConfig.archived()` |

### The validity gate (ran before every training invocation, passed every time)

An identical fixed policy rolled out under all three reward versions produced **bit-identical
state trajectories** — cash, portfolio, loan balance, goal balances and net worth, all 142
months, all three sampled users. The reward version therefore changes the learning signal and
**nothing else**: no dynamics, no accounting, no crediting. Any difference in the results below
is attributable to learning.

Had this failed, no comparison would have been produced.

**Invariant checks during evaluation across all 180 rollouts: 0 budget violations, 0 cash-floor
activations, 0 reserve breaches, 0 interest shortfalls.** No policy was infeasible or excluded.

---

## 2. Results — mean of seed means ± SD across 3 seeds (20 held-out users each)

| Metric | `archived_v1` | `candidate_a` | `candidate_b` |
|---|---:|---:|---:|
| Weighted goal achievement | 0.3202 ± 0.0220 | **0.4024 ± 0.0215** | 0.3886 ± 0.0365 |
| % goals fully funded | 0.2311 ± 0.0236 | **0.3361 ± 0.0163** | 0.2819 ± 0.0211 |
| % goals met by deadline | 0.0781 ± 0.0292 | **0.1267 ± 0.0079** | 0.1108 ± 0.0160 |
| Goal-level shortfall (₹) | 6,503,587 ± 449,538 | 6,492,056 ± 296,712 | **6,207,687 ± 151,523** |
| Final net worth (₹) | 2,394,967 ± 102,037 | 2,396,402 ± 90,149 | **2,473,537 ± 79,391** |
| Final liquid cash (₹) | 1,650,682 ± 123,424 | **1,670,587 ± 123,446** | 1,515,758 ± 82,625 |
| Final portfolio value (₹) | 754,299 ± 223,610 | 746,178 ± 215,762 | **974,137 ± 168,343** |
| Outstanding loan (₹) | **10,014 ± 9,454** | 20,364 ± 6,598 | 16,358 ± 8,286 |
| Total loan principal (₹) | **29,282 ± 23,040** | 67,509 ± 22,687 | 59,420 ± 6,220 |
| Total interest paid (₹) | **5,675 ± 4,655** | 13,728 ± 5,032 | 12,107 ± 2,003 |
| Downside exposure (₹) | **638,326 ± 151,682** | 655,572 ± 133,627 | 755,056 ± 115,900 |
| Budget violations | 0 | 0 | 0 |
| **Total reward** *(not comparable)* | −13.51 ± 1.53 | −40.24 ± 0.75 | **+2,869.86 ± 6.03** |

**Derived (normalised) downside intensity** — downside exposure ÷ portfolio value, which I
computed because raw downside exposure is not portfolio-normalised and therefore favours
whoever holds the smallest portfolio:

| | `archived_v1` | `candidate_a` | `candidate_b` |
|---|---:|---:|---:|
| Downside ÷ portfolio | 0.846 | 0.879 | **0.775** |

### Historical reference — read with care

Archived checkpoint under `archived()` semantics: weighted achievement **0.2928**, % fully
funded 0.170, shortfall ₹5,167,241, loan principal ₹79,675, interest paid ₹19,028, net worth
**₹887,092**.

Its **net-worth column is not comparable** to the three arms: `archived()` uses legacy
accounting, which never records unallocated surplus in any account (audit finding F-04/§4.4.1),
whereas the three arms use ledger accounting. Its *skill* comparison is also confounded — it was
trained under `magnitude` action semantics against nominal targets. It is a historical
reference, not a peer row.

---

## 3. Paired comparisons (paired on `user_id` × `seed`, n = 60, bootstrap 95% CI)

Significant differences only:

| Comparison | Metric | Mean difference | CI95 | Favours |
|---|---|---:|---|---|
| `archived_v1` → `candidate_a` | weighted achievement | **+0.0821** | [0.0517, 0.1159] | candidate_a |
| `archived_v1` → `candidate_a` | % fully funded | **+0.1050** | [0.0628, 0.1486] | candidate_a |
| `archived_v1` → `candidate_a` | % met by deadline | **+0.0486** | [0.0150, 0.0839] | candidate_a |
| `archived_v1` → `candidate_a` | loan principal | +38,227 | [13,858, 63,704] | archived_v1 |
| `archived_v1` → `candidate_a` | interest paid | +8,053 | [3,121, 13,148] | archived_v1 |
| `archived_v1` → `candidate_b` | weighted achievement | **+0.0684** | [0.0323, 0.1060] | candidate_b |
| `archived_v1` → `candidate_b` | % fully funded | **+0.0508** | [0.0067, 0.0981] | candidate_b |
| `archived_v1` → `candidate_b` | % met by deadline | **+0.0328** | [0.0011, 0.0653] | candidate_b |
| `candidate_a` → `candidate_b` | % fully funded | **−0.0542** | [−0.0861, −0.0267] | candidate_a |

### What is **not** significant — and must not be claimed

- **`candidate_a` vs `candidate_b` on weighted achievement: not significant.** The two are
  statistically indistinguishable on overall goal achievement (0.4024 vs 0.3886).
- **`candidate_a` vs `candidate_b` on % met by deadline: not significant.**
- **Net worth: no difference between any pair is significant.** Candidate B's seemingly higher
  net worth (₹2.474 M vs ₹2.396 M) is **within seed noise**. It must not be reported as an
  improvement.
- `candidate_b`'s higher loan principal and interest than `archived_v1` are **not** significant
  (the archived arm's variance is large); only `candidate_a`'s are.

---

## 4. Profile breakdown (weighted achievement / net worth / % by deadline / interest paid)

| Profile | `archived_v1` | `candidate_a` | `candidate_b` |
|---|---|---|---|
| risk **low**, horizon ≤7y | 0.0000 / 66,598 / 0.000 / 0 | 0.0000 / 66,598 / 0.000 / 0 | 0.0000 / 66,598 / 0.000 / 0 |
| risk **low**, horizon >7y | 0.0000 / 44,675 / 0.000 / 0 | 0.0000 / 44,675 / 0.000 / 0 | 0.0000 / 44,675 / 0.000 / 0 |
| risk **mid**, horizon ≤7y | 0.3409 / 1,540,928 / 0.033 / 2,244 | 0.3683 / 1,524,555 / 0.033 / 11,580 | **0.3729** / 1,534,262 / 0.033 / 18,017 |
| risk **mid**, horizon >7y | 0.3495 / 1,296,824 / 0.078 / 1,654 | **0.4397** / 1,288,829 / 0.089 / 8,898 | 0.4006 / 1,280,959 / 0.089 / 17,040 |
| risk **high**, horizon ≤7y | 0.7755 / 1,680,309 / 0.108 / 10,422 | **0.8161** / 1,670,482 / **0.217** / 14,123 | 0.7947 / 1,693,721 / 0.150 / 19,838 |
| risk **high**, horizon >7y | 0.4624 / 5,989,293 / 0.161 / 13,592 | **0.6533** / 6,008,138 / **0.280** / 31,260 | 0.6392 / 6,259,518 / 0.249 / 16,377 |

Two observations:

1. **The improvement is concentrated in the high-risk and long-horizon profiles**, where
   candidate A roughly doubles deadline success for high-risk short-horizon users
   (0.108 → 0.217). For mid-risk users the gain is small.
2. **The low-risk group scores 0.0000 under every reward version, with byte-identical net worth
   and zero interest.** The policies are indistinguishable from each other there, which suggests
   a subpopulation effect rather than a reward effect (most likely a collapsed/near-constant
   action). **This was not expected and is unexplained.** It is recorded as an open finding, not
   smoothed over — and it is the strongest reason not to declare any version a general success.

---

## 5. Two incomparabilities that must not be ignored

1. **Total reward is on different numeric scales and cannot rank the versions.** `candidate_b`
   scores **+2,869.86** against −13.51 and −40.24 for the others, purely because its
   `wealth_delta` and terminal terms are normalised differently. Selecting on total reward would
   always pick `candidate_b` — which is *not* the best on goal achievement and whose net-worth
   advantage is not significant. Conversely `archived_v1` has a *better* total reward than
   `candidate_a` while being significantly worse on every attainment metric. Reward-based
   selection is not merely discouraged here; it would give the wrong answer.
2. **The archived reference's wealth columns are not comparable** (legacy vs ledger accounting,
   §2).

---

## 6. Limitations

1. **Three seeds is a small sample for a stochastic learner.** It is enough to show the
   achievement gains are larger than seed noise (SDs ~0.02 vs a +0.08 gap) and to reject the
   net-worth claims, but not enough to characterise the tails.
2. **50,000 timesteps is a modest budget.** These results show which reward provides a *better
   learning signal at this budget*, not which wins at convergence. PPO may be far from
   converged — `pct_goals_met_by_deadline` is 0.13 at best.
3. **Single environment implementation.** The validity gate guarantees the reward version is the
   only difference, but the environment itself still carries the earlier design choices
   (R-08 goal-cap funds not reallocated; the goal-cap and affordability mechanics), which cap
   achievable attainment for every arm equally.
4. **Coefficients are design parameters, not optima**, and were not tuned against held-out users.
   A different `loan_cost_weight` or `wealth_delta_weight` would produce a different experiment.
   Only `candidate_a`'s and `candidate_b`'s *specified* forms were tested.
5. **Downside exposure is not portfolio-normalised** in the raw metric; the derived intensity
   in §2 is my own calculation and is labelled as derived.
6. **`pct_goals_met_by_deadline` is unavailable for the archived reference** (not recorded), and
   its other metrics are confounded by the semantics change.
7. **No fine-tuning, no hyper-parameter search, no reward-coefficient sweep.** Deliberately.

---

## 7. Recommendation

**Retain `candidate_a` as the training reward for GoalPilot v1**, configured as
`GoalPilotConfig.recommended().replace(reward_version=REWARD_VERSION_A)`. Keep `archived_v1` as
the package default: the original reward implementation must stay unchanged and reproducible.

Rationale:

- Candidate A improves **every** goal-attainment metric by a margin that is significant under
  paired comparison and larger than cross-seed dispersion: achievement +0.082, fully-funded
  +0.105, deadline success +0.049. Goal attainment is the stated purpose of the system.
- It is the only version that is significantly ahead of Candidate B on any attainment metric
  (% goals fully funded, +0.054), and it reaches the best result in the high-risk and
  long-horizon profiles, which is where the difficulty actually lies.

**The honest cost, which must be reported alongside the gain:** Candidate A achieves this by
borrowing roughly twice as much as the historical reward (+₹38,227 principal, +₹8,053 interest
per user, both significant). The household pays real interest for earlier goal completion. If
that trade-off is judged unacceptable, **Candidate B is the more conservative alternative** —
statistically tied on overall achievement, lower normalised downside intensity (0.775 vs 0.879),
and its extra borrowing is not statistically significant — but it funds significantly fewer
goals outright.

**Further redesign is needed before any claim of general improvement**, on two specific points:

1. **The low-risk subpopulation collapse** (§4.2): all three rewards score 0.0000 there. This is
   unresolved and must be diagnosed before GoalPilot is presented as working across the
   population.
2. **The debt-cost trade-off**: an experiment sweeping `loan_cost_weight` (with the held-out set
   untouched, using a separate validation split) is the natural next step if the interest
   increase is to be traded against achievement deliberately rather than incidentally.

Do **not** describe this experiment as showing that PPO "solves" goal-based planning: at 50k
steps even the best arm funds only ~13% of goals by their deadlines, and no comparison against
the LP optimizer's plan is made here (that comparison is in
`outputs/evaluation/final_validation_v1/POLICY_COMPARISON_REPORT.md`).

---

## 8. Reproducing

```powershell
$py = "C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe"
Set-Location S:\fyp\GoalPilot_AI_Completed

# 1. smoke test (validity gate + training + evaluation + checkpoint/metric logging)
& $py audit_tools\33_reward_experiment.py --mode smoke

# 2. controlled training: 3 versions x 3 seeds x 50,000 steps (staged and resumable)
& $py audit_tools\33_reward_experiment.py --mode full --stage train --timesteps 50000 --seeds 7,17,27

# 3. evaluation of all nine checkpoints + the archived reference on the 20 held-out users
& $py audit_tools\33_reward_experiment.py --mode full --stage eval

# 4. aggregation: seed dispersion, paired CIs, profile breakdown
& $py audit_tools\34_reward_experiment_report.py full
```

`--stage train` is idempotent and skips any `(version, seed)` whose checkpoint exists;
`--force` retrains one. This staging exists because an earlier monolithic run was killed by a
15-minute execution cap and lost its unflushed results — no work is now lost on interruption.

Artefacts: checkpoints and per-run logs in
`training_logs/experiments/reward_experiment_v1/<version>/`; metrics in
`outputs/reward_design/v1/`. Raw console output for every command is committed alongside them.
