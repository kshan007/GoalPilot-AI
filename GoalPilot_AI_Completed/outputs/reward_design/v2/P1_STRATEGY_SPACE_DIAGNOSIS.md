# P1 — Why a constant `Investments only` action beats every RL policy

**Date:** 2026-10-11 · **Version:** v2 · **Script:** `audit_tools/50_strategy_space_diagnosis.py`
**Population:** the 14 feasibility-eligible held-out users (zero-surplus users excluded per §1 of
`LOW_RISK_AND_STATISTICAL_DIAGNOSTIC.md`), 142 months each, one shared configuration
(`GoalPilotConfig.recommended()`).

Console: `outputs/evaluation/final_validation_v2/strategy_diagnosis_console.txt`.
Data: `strategy_space_summary.csv`, `strategy_space_diagnosis.csv`,
`rl_action_distributions.csv`.

---

## 1. The full ranking, with the mechanism columns

| Strategy | Achievement | % fully funded | **Allocated fraction of budget** | Idle fraction | **Market value earmarked to goals (₹)** | Net worth (₹) |
|---|---:|---:|---:|---:|---:|---:|
| **Need-proportional invest** | **0.6350** | 0.4155 | 0.8256 | 0.1744 | 1,738,583 | 3,756,623 |
| AGGRESSIVE all channels | 0.6252 | 0.4774 | 0.7078 | 0.2922 | 1,085,819 | 3,507,317 |
| **Investments only** | 0.6161 | 0.4774 | 0.7059 | 0.2941 | 1,117,512 | 3,537,838 |
| **Mixed (0.50/0.50)** | **0.6161** | **0.4774** | **0.7059** | **0.2941** | **1,117,512** | **3,537,838** |
| LP optimizer plan | 0.6113 | 0.4298 | 0.7420 | 0.2580 | 1,248,066 | 3,579,144 |
| RL `candidate_a` seed7 | 0.5963 | 0.4964 | 0.6398 | 0.3602 | 789,222 | 3,404,120 |
| RL `candidate_a` seed27 | 0.5885 | 0.4905 | 0.6389 | 0.3611 | 1,137,823 | 3,526,045 |
| Savings only | 0.5873 | 0.4536 | 0.7253 | 0.2747 | 0 | 2,982,685 |
| RL `candidate_a` seed17 | 0.5397 | 0.4536 | 0.5511 | 0.4489 | 523,208 | 3,268,595 |
| RL `archived_v1` seed7 | 0.4896 | 0.3690 | 0.6779 | 0.3221 | 560,854 | 3,268,973 |
| RL `archived_v1` seed27 | 0.4561 | 0.3131 | 0.6621 | 0.3379 | 1,182,049 | 3,555,903 |
| Need-proportional both | 0.4358 | 0.1429 | **0.9409** | 0.0591 | 1,730,323 | 3,755,961 |
| RL `archived_v1` seed17 | 0.4268 | 0.3083 | **0.4853** | **0.5147** | 742,154 | 3,367,737 |
| Rule-based urgency | 0.3713 | 0.0714 | 0.9527 | 0.0473 | 0 | 2,982,685 |
| Need-proportional savings | 0.3673 | 0.0714 | 0.9527 | 0.0473 | 0 | 2,982,685 |

**The achievable ceiling for a deterministic policy here is ≈0.635** (Need-proportional
invest). The best RL run reaches 0.5963 — **0.039 below a simple reference policy**, and below
`Investments only`, `Mixed` and the LP.

---

## 2. Findings

### R-12 (new) — In `share` mode the savings/investment split is **degenerate** whenever the investment request exceeds capacity

`Investments only` and `Mixed (0.50/0.50)` are **byte-identical** on every column of the table
above: 0.6161 / 0.4774 / 0.7059 / 1,117,511.88 / 3,537,837.79. Not approximately — identically.

Mechanism: `_allocate` caps investment at `invest_cap = available × investment_capacity_ratio`
and returns the overflow to savings. With `investment_capacity_ratio` between 0.15 and 0.37 for
these users, **any** action whose investment request meets or exceeds capacity produces the same
allocation: "invest as much as capacity allows, save the rest". The (0, 1, 0) and (0.5, 0.5, 0)
actions therefore denote the same policy.

Consequence: this is a **share-mode analogue of the original F-01 degeneracy**. The 5×3 action
space is effectively lower-dimensional for any policy that requests at or above capacity, so a
"savings versus investment mix" conclusion drawn from this environment is again an artefact of
the environment rather than a property of the strategies. It also means **the environment cannot
express a genuinely investment-light strategy** beyond what capacity allows.

### R-13 (new) — The per-goal cap discards a quarter to a half of the monthly budget

`idle_fraction` is the share of the discretionary budget released by the per-goal cap (finding
R-08) and then discarded instead of being reallocated to goals that still need money:

| Group | Idle fraction |
|---|---|
| Best simple policies (`Investments only`, `Mixed`, AGGRESSIVE) | **0.29** |
| LP plan | 0.26 |
| **RL policies** | **0.36 – 0.51** |
| Most-concentrated policies (`Rule-based urgency`, `Need-proportional savings`) | 0.05 |

So **even the best strategies waste ~26–29% of every monthly budget**, and the RL policies waste
**36–51%**. Combined with `rl_action_distributions.csv` (savings channel mean 0.22–0.54 with
14–61% of entries below 0.05), the picture is that the RL policies **concentrate their requests
on a subset of goals**; those goals then saturate, the cap releases the excess, and the released
money is thrown away. RL's deficit is therefore substantially a **budget-utilisation failure
interacting with an environment defect**, not purely a weak-optimisation failure.

This also explains why `Rule-based urgency` and `Need-proportional savings` — which allocate
95% of the budget, the most efficient allocation in the table — still perform **worst**: they
spread nothing and invest nothing, so they complete almost no goal. **Allocation efficiency and
achievement are not the same thing.**

### The three levers that actually determine the ranking

1. **Whether the policy invests.** `market_value_earmarked` tracks the ranking far better than
   allocated fraction does (1.74M → 0.635; 1.12M → 0.616; 0 → 0.587). Investing genuinely
   creates wealth, which `market_weighted` credits to goals as **realised** revaluation — real,
   not projected, and bounded by `goal_balances ≤ cash + portfolio`.
2. **How much budget the cap discards** (R-13): 26% for the leaders, up to 51% for RL.
3. **Spread versus concentrate.** `Investments only` spreads uniformly and completes 47.7% of
   goals; `Need-proportional both` earmarks the *most* rupees (1.73M) yet completes only 14.3%,
   because it keeps spreading across all goals and finishes none. Consistently, more rupees
   earmarked does not mean more goals completed.

**Answer to P1:** the ordering is caused by the interaction of (1) and (2) — RL leaves 36–51% of
its budget idle against 26–29% for the leading simple policies, while the investment channel is
also degenerate (R-12) so the policies that invest are compressed onto one effective behaviour.

---

## 3. What this does **not** show

- It does **not** show the RL reward designs are wrong. `candidate_a` still beats `archived_v1`
  (0.5963 vs 0.4896) on identical inputs — which is the comparison the reward experiment was
  designed to make, and that conclusion stands.
- It does **not** show RL "cannot work". It shows that **under this environment** the policy has
  two structural disadvantages (a degenerate action space, R-12, and a large incentive to
  concentrate requests, which the cap then punishes, R-13) that no reward change can fix.
- `Need-proportional invest` is a **reference ceiling for diagnosis**, not a deployable
  strategy: it reads the simulator's exact remaining needs each month with no uncertainty, so it
  cannot compete as a realistic baseline.

---

## 4. Revised next steps

| Priority | Action | Rationale |
|---|---|---|
| **P1a** | **Fix R-13 (reallocate cap-released budget to goals with remaining need), gated behind a new config flag so `archived()` and all existing presets stay byte-identical** | Quantified: 26–51% of every monthly budget is currently destroyed. Until this is fixed, every strategy comparison under-states what is achievable and rewards RL for a behaviour (concentrating) that the environment then penalises |
| **P1b** | **Decide how to handle R-12** — either document the degeneracy as a known property of `share` mode, or make the investment cap non-degenerate (e.g. let unused capacity revert only up to a fixed share) | The action space currently cannot express an investment-light policy, so "mix matters" claims are again unreliable |
| **P2** | Confirm `candidate_a` on a **fresh split** with cluster-bootstrap statistics | Still outstanding: the recommendation was made on the held-out set that was subsequently used for evaluation |
| **P3** | The 50k / 150k / 300k budget comparison (plan in `LOW_RISK_AND_STATISTICAL_DIAGNOSTIC.md` §3.3, ≈38 min training) | **Defer until P1a/P1b are settled** — running it now would answer a question about a policy in an environment that structurally penalises it |
| **P4** | Replace `Rule-based urgency` with two fair rule baselines: a uniform **and** a need-proportional rule, both investing up to capacity | The current single rule scored 0.0000 deadline success and ranked last; it is a defective baseline, not a finding |
| **P5** | Validate the synthetic population (30% zero-surplus) | Population-level claims depend on whether that is intended |

**Recommendation:** the binding constraint on GoalPilot's policy-learning results is the
**environment**, not the reward. R-13 in particular is a measured, mechanical loss of 26–51% of
household budget every month. Fixing it (gated, with regression tests) should precede any further
training, because it changes the achievable ceiling for every strategy including the baselines.
