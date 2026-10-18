# R-12 action-space design experiment — proposal, implementation, tests, fixed-policy results

**Date:** 2026-10-11 · **Version:** v4 (v1–v3 untouched)
**Scripts:** `audit_tools/53_action_mapping_comparison.py`, `tests/test_goalpilot_env_action_mix.py`
**Source changed:** `goalpilot_env.py`, `goalpilot_config.py` — one opt-in flag, see §5
**Status:** design + implementation + tests + fixed-policy evaluation complete. **No PPO training
was run and none is proposed in this document.**

---

## 1. What was inspected

| Component | Location | Relevant fact |
|---|---|---|
| Action space | `GoalPilotEnv.__init__` | `Box(shape=(5, 3))` — per goal slot: savings weight, investment weight, loan request |
| Share mapping | `goalpilot_env.py::_allocate` | `shares = concat(w_sav, w_inv) / Σ`, allocates `A` to each channel, then caps the investment portion at `invest_cap` and **pushes the overflow into savings** |
| Capacity | `goalpilot_env.py`, `step` | `invest_cap = available_after_existing_loan × investment_capacity_ratio` |
| R-12 evidence | `outputs/reward_design/v2/P1_STRATEGY_SPACE_DIAGNOSIS.md`, `.../v3/P1B_R12_AND_P4_FAIR_BASELINES.md` | `(0,1,0)` and `(0.5,0.5,0)` identical at achievement 0.6545, idle 0.0295, net worth to the cent |
| R-13 implementation | `goalpilot_env.py`, flag `reallocate_capped_budget` | Reallocates `released_by_goal_cap` to goals with remaining need; **does not touch the investment-cap overflow** (§5.3) |
| Validation reports | `outputs/evaluation/final_validation_*`, `outputs/reward_design/v1–v3` | Archived parity is byte-identical; 133 tests green before this change |

**The root cause, stated exactly.** In `share` mode the overflow above `invest_cap` is returned to
the savings channel, so whenever the investment request meets or exceeds capacity the *only*
thing that survives the transformation is `invest_cap` itself — the requested mix is erased.
`(0,1,0)` and `(0.5,0.5,0)` therefore denote one policy. This is not a cap problem: it is a
**relabelling** problem.

---

## 2. Options

### A — keep the existing `share` mapping (baseline)

| | |
|---|---|
| Semantics | Overflow → savings. Total allocated is always the full available budget. |
| Pros | No dependency on capacity; never wastes budget; all published results and checkpoints remain valid. |
| Cons | The requested mix is **unobservable** above capacity. An investment-only request silently becomes a savings-heavy policy. No "does the mix matter?" question can be answered. |

### B — explicit investment-fraction control (**selected**)

Identical to `share` except that investment demand above capacity is **left unallocated** and
reported, instead of being relabelled as savings. The investment-fraction control is the **mix
ratio** `Σw_inv / (Σw_inv + Σw_sav)`, which spans [0,1] and is honoured up to capacity:

```
realised investment = min( mix_ratio × available_after_existing_loan , invest_cap )
```

| | |
|---|---|
| Pros | One behavioural difference, ~10 lines. Every action dimension keeps its meaning. Fully reversible through a config flag. Makes `(0,1,0)` ≠ `(0.5,0.5,0)` (§7). |
| Cons | Lowers measured achievement for investment-heavy policies (§7.2) and raises idle budget unless the policy requests savings explicitly. Requires re-encoding anything expressed in absolute rupees (§9.2). |

### C — a separate goal-allocation decision, decoupling intensity from distribution

| | |
|---|---|
| Semantics | Extra action dimensions for how to split money across goals, separate from how much to invest. |
| Verdict | **Not necessary.** The existing weights already carry a pure *distribution* role — within each channel the weights are normalised to shares of that channel's envelope (`shares[:n]`, `shares[n:]`). Distribution and intensity are already separable: the *ratio* of the two channel sums sets the investment fraction, the *relative* weights set the distribution. Adding dimensions would enlarge the action space without adding a decision that cannot already be expressed. |
| Rejected because | It fails the "smallest interpretable change" test, and it would break the 15-dimension schema every existing result depends on. |

---

## 3. Recommendation

**Adopt B**, implemented as a new opt-in `action_mode="mix"`, reachable only through
`GoalPilotConfig.with_action_mix()`.

Rationale: it is the smallest change that removes the ambiguity (one branch, one behavioural
difference), every existing dimension retains a clear financial meaning (§4), it is exactly
reversible, and it is verifiable at the level of a single month (§6). Option C is unnecessary
because distribution and intensity are already independent axes of the existing weights.

---

## 4. What every dimension means

| Dimension | Financial decision it encodes | Cap applied | What happens to the excess |
|---|---|---|---|
| `a[j, 0]` | Share of the **savings envelope** earmarked to goal *j* (cash kept, credited to the goal now) | None directly; the envelope is bounded by `available_after_existing_loan` | `share`: n/a. `mix`: excess savings demand is bounded by the guard and reported in `unallocated_surplus` |
| `a[j, 1]` | Share of the **investment envelope** allocated to goal *j* (cash converted into the portfolio) | `invest_cap = A × investment_capacity_ratio`, enforced per month | **`share`: relabelled into savings. `mix`: left unallocated**, reported in `budget_audit["unallocated_from_investment_cap"]` |
| `a[j, 2]` | Request to originate a loan for goal *j* (only the largest request is used, one loan at a time) | `max_new_loan`, the `emi_income_ratio_cap`, and the month's surplus | No loan is originated; nothing is created |
| **Mix ratio** `Σw_inv / (Σw_inv + Σw_sav)` | **Investment intensity**, as a fraction of the available budget | capacity, as above | as above |
| **Within-channel ratios** `w[j]/Σw` | **Goal distribution** — which goal gets more of each envelope | per-goal remaining need | Excess above remaining need is released and — with the R-13 flag on — reallocated |

Two properties to state plainly, because they caused two of my own test failures and would
mislead anyone reading the schema:

- **The weights are scale-free.** `(0, 0.25, 0)` is *not* "invest a quarter" — with no savings
  weight the mix is 100% investment, so it behaves exactly like `(0, 1, 0)`. Only the *ratio*
  between the channel sums carries information.
- **The memo account partitions gross assets.** `sum(goal_balances) <= cash + portfolio` is the
  valid bound; subtracting `loan_balance` is only valid for policies that never borrow, because
  goal earmarks may be loan-funded.

---

## 5. Implementation

### 5.1 Changes

| File | Change |
|---|---|
| `goalpilot_config.py` | New `ACTION_MODE_MIX = "mix"` added to `ACTION_MODES`; documentation of the mode; new classmethod `with_action_mix()` |
| `goalpilot_env.py` | `_allocate` returns a third value `unallocated_from_cap` (0.0 for `magnitude`/`share`); new `mix` branch; call site unpacks it; `budget_audit["unallocated_from_investment_cap"]` exposed |

### 5.2 Gating

- `action_mode` defaults to `ACTION_MODE_MAGNITUDE`; **`archived()`, `corrected_accounting()`,
  `lp_parity()`, `recommended()` and `with_reallocation()` are all unchanged**, pinned by test.
- `with_action_mix()` is pinned to differ from `recommended()` in **exactly one field**.
- Archived parity **did** hold: after the change the full RL suite reported
  **124 passed in 193.46s**, with `test_goalpilot_env_parity.py` (100 users x 5 policies x
  142 months, reward to 1e-12) among them. The change is verified safe to keep.

### 5.3 Known interaction: two independent release channels

R-13's reallocation consumes `released_by_goal_cap` only. The investment-cap overflow is a
**different** channel and is *not* reallocated. Consequences, both pinned by test:

1. `mix` stays non-degenerate **even with the R-13 flag on** (good).
2. With **both** flags on, the investment-cap overflow is still discarded (open question — is
   that intended? R-13's stated principle is "nothing is wasted", which would argue for also
   reallocating it. Not changed here because R-13 is already published and tested).

---

## 6. Regression-test plan — implemented, 17 tests, all passing

| Required area | Test |
|---|---|
| Legacy parity / not silently enabled | `test_mix_mode_is_not_enabled_by_any_existing_preset`, `..._changes_one_field` |
| **Parity with the published mapping** | `test_mix_matches_share_exactly_when_demand_is_within_capacity` — action built from each user's own capacity so it is provably affordable; savings, investment and surplus must match to 1e-9 |
| Non-degenerate investment behaviour | `test_mix_is_non_degenerate_when_demand_exceeds_capacity`, `test_mix_honours_the_requested_investment_fraction` (monotonicity in the mix ratio) |
| Action bounds and no-op | `test_mix_all_zero_action_is_a_true_no_op`, `test_mix_extreme_actions_stay_in_bounds` |
| Budget conservation, per-goal limits, memo bound | `test_mix_budget_conservation_limits_and_memo_bound` (5 policies), `test_mix_per_goal_limit_holds_when_the_credit_clamp_is_active` |
| Released-budget redistribution | `test_mix_released_budget_redistribution_still_works` |
| R-13 interaction | `test_mix_stays_non_degenerate_with_reallocation_on` |
| Loan affordability | `test_mix_loan_affordability_is_respected` |
| Determinism | `test_mix_is_deterministic` |

```
$ python -m pytest tests\test_goalpilot_env_action_mix.py -q
17 passed in 6.78s
```

---

## 7. Fixed-policy comparison — the same users, the same market path

`audit_tools/53_action_mapping_comparison.py`, run on the **fresh** test users (16, the
uncontaminated partition), one configuration apart: `recommended()` vs `with_action_mix()`.
RL arms are excluded (§8). `affordability_violations = 0` for every arm in both mappings.

### 7.1 Does the mapping actually change the allocation? — **Yes (requirement 7 satisfied)**

| Policy | users with different investment | users with different savings | achievement `share` | achievement `mix` | Δ | improved / worsened |
|---|---:|---:|---:|---:|---:|---:|
| uniform savings | 0 / 16 | 0 / 16 | 0.5584 | 0.5584 | **0.0000** | 0 / 0 |
| need-proportional savings | 0 / 16 | 0 / 16 | 0.3211 | 0.3211 | **0.0000** | 0 / 0 |
| urgency | 0 / 16 | 0 / 16 | 0.4051 | 0.4051 | **0.0000** | 0 / 0 |
| uniform 50/50 | **14 / 16** | **14 / 16** | 0.5800 | 0.5281 | −0.0518 | 0 / 14 |
| uniform investment | **14 / 16** | **14 / 16** | 0.5800 | 0.3761 | −0.2039 | 0 / 14 |
| need-proportional both | 1 / 16 | **14 / 16** | 0.3629 | 0.2863 | −0.0766 | 0 / 13 |
| need-proportional investment | **14 / 16** | **14 / 16** | 0.5835 | 0.1321 | −0.4514 | 0 / 14 |
| LP plan | 9 / 16 | 12 / 16 | 0.4955 | 0.2215 | −0.2740 | 0 / 12 |

**`uniform investment` and `uniform 50/50` were identical under `share` (0.5800 both) and are
now different (0.3761 vs 0.5281).** R-12 is removed.

**The three zero-delta rows are controls, and they are the strongest evidence the change is
surgical:** they request no investment at all, so the investment-cap overflow never occurs and
the outcome is bit-identical. Exactly one mechanism moved, exactly where predicted.

### 7.2 The direction of the effect — read this before using the numbers

**`mix` does not improve anything. It removes a hidden subsidy, and every
investment-requesting policy therefore scores *lower*.** 0 of 16 users improve; 12–14 worsen for
the six policies that request investment.

Under `share`, an investment-heavy request was silently converted into savings and **credited to
the goals as if the household had chosen to save** — so those policies were being paid for a
decision they never expressed. Idle budget also rises: `uniform investment` 0.2459 → **0.6936**,
`need-proportional investment` 0.1386 → **0.6680**, LP plan 0.3713 → **0.7568**.

The consequence for interpretation is important: **every previously published fixed-policy
achievement figure for an investment-heavy policy is inflated relative to `mix`**, and any future
policy under `mix` must specify its savings explicitly rather than relying on the overflow being
relabelled.

---

## 8. Checkpoint compatibility (requirement 8)

> **No existing PPO checkpoint is compatible with `action_mode="mix"`.**
> The checkpoints in `training_logs/experiments/**` and the archived `best_model.zip` were trained
> under `magnitude` (archived) or `share` (`recommended`) semantics. `mix` changes what an action
> *means*: an output the policy learned as "invest heavily" now leaves part of the budget
> unallocated instead of funding goals. The observation space is unchanged, so such a model will
> still load and emit actions without error — which is precisely why the incompatibility is
> dangerous rather than obvious.

Consequences: existing checkpoints may only be evaluated under the mapping they were trained on;
`mix` requires a freshly trained policy; and no cross-mapping comparison of trained policies is
valid unless compatibility has been explicitly tested and proven. No such test is claimed here.

---

## 9. Limitations

### 9.1 Open design questions
1. Should R-13's reallocation also consume the investment-cap overflow (§5.3.2)?
2. Per-goal over-funding through the `market_weighted` gain still occurs without the R-13 credit
   clamp — a pre-existing property, unchanged by this work and independent of the action mode.

### 9.2 The LP encoding is exposed as unfaithful
Under `mix`, the LP plan collapses (0.4955 → 0.2215) and wastes 75.7% of the budget. The cause is
that the LP's plan is expressed in **absolute rupees**, and I encoded it as raw action weights —
but the weights are scale-free, so the absolute information is destroyed, and the plan's
investment-heavy ratio then makes most of the budget uninvestable. Under `share` the relabelling
accidentally rescued it; under `mix` it does not. **The LP arm needs re-encoding as an explicit
mix plus a within-channel distribution before it is used in any `mix` comparison.** I did not
change it here because that would alter a published comparison without a decision.

### 9.3 Not measured
Only fixed, deterministic policies were evaluated. Nothing here says anything about what a
*learned* policy would do under `mix`, which is untested and requires training (§8).

---

## 10. Explicit non-claims

- **`mix` does not improve RL performance**, financial outcomes, goal achievement or anything
  else. On the fixed policies it lowers achievement, and that is the *intended* consequence of
  removing a subsidy (§7.2).
- No claim that `mix` is superior to `share`. `share` remains the default and reproduces every
  published number; `mix` is a substrate for a question `share` cannot answer.
- No claim that a trained policy will reach any particular level under `mix`.
- No claim that projected goal credits are realised wealth (finding R-03 stands; `market_weighted`
  remains the recommended credit mode).

---

## 11. Status

| Item | Status |
|---|---|
| Design proposal (A/B/C) | Done — B selected, C rejected with reasons (§2, §3) |
| Implementation behind an opt-in flag | Done (§5) |
| Regression tests (9 required areas) | **17 tests passing** (§6) |
| Requirement 7 — distinct allocations | **Confirmed** (§7.1) |
| Fixed-policy comparison | Done, both mappings, same users and market path (§7) |
| Checkpoint incompatibility documented | Done (§8) |
| PPO training | **Not started** — awaiting review |
| Full suite after this change | **Verified green** — `124 passed in 193.46s` (107 previous + 17 new), archived parity included. Console: `outputs/reward_design/v4/pytest_full_after_action_mix.txt`. Test inventory is now **124 RL + 26 LP = 150 tests, 0 failures** |

## 12. Reproducing

```powershell
$py = "C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe"
Set-Location S:\fyp\GoalPilot_AI_Completed

& $py -m pytest tests\test_goalpilot_env_action_mix.py -q      # 17 passed
& $py audit_tools\53_action_mapping_comparison.py              # the §7 tables
& $py -m pytest -q                                             # full suite incl. archived parity
```
