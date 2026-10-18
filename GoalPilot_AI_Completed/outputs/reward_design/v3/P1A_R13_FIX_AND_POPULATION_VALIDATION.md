# P1a — R-13 fix (opt-in), and P5 — population feasibility validation

**Date:** 2026-10-11 · **Version:** v3
**Scripts:** `audit_tools/51_reallocation_impact.py`, `tests/test_goalpilot_env_reallocation.py`
**Source changed:** `simulation/05_simulation_runs/rl_prototype/goalpilot_env.py`,
`goalpilot_config.py` — both strictly gated, see §1.3.

---

## 1. P1a — reallocating budget released by the per-goal cap

### 1.1 What was changed

Finding R-13: the per-goal cap releases budget that is then **discarded**, destroying 26–29% of
the monthly budget for the best simple policies and 36–51% for the trained RL policies
(`P1_STRATEGY_SPACE_DIAGNOSIS.md`).

Two changes, **both inside the new opt-in flag**:

1. **Reallocation.** Money released by the cap is given to goals that still have remaining need,
   in proportion to that need, preserving the savings/investment channel split of the surviving
   allocation, respecting investment capacity, and applying each channel's own credit convention.
   Up to four passes, because a grant can saturate a goal and release more.
2. **No credit past the target.** Under `market_weighted` the monthly market gain is credited
   outside the cap, so a fully-funded goal could drift above its target. The credit is now
   clamped to the remaining need. Only the *credit* is clamped — the money already moved into
   cash/portfolio stays there as unattributed wealth, so `sum(goal_balances) <= cash + portfolio`
   is preserved.

### 1.2 Measured effect (14 feasibility-eligible held-out users, identical otherwise)

| Policy | Achievement, flag **off** | flag **on** | Δ | Idle fraction off → on | Users improved / worsened |
|---|---:|---:|---:|---|---:|
| Savings only | 0.5873 | **0.6333** | **+0.0459** | 0.2747 → **0.0473** | 12 / 0 |
| Investments only | 0.6161 | **0.6545** | **+0.0384** | 0.2941 → **0.0295** | 12 / 1 |
| Mixed (0.50/0.50) | 0.6161 | **0.6545** | **+0.0384** | 0.2941 → **0.0295** | 12 / 1 |
| LP optimizer plan | 0.6113 | **0.6384** | **+0.0271** | 0.2580 → **0.0317** | 10 / 2 |
| **Rule-based urgency** | 0.3713 | **0.3713** | **0.0000** | 0.0473 → **0.0473** | **0 / 0** |

The discarded budget falls from 26–29% to **~3%**, and the achievable ceiling rises from 0.6161 to
**0.6545**.

**The natural control is `Rule-based urgency`.** It is the one policy already wasting almost
nothing (idle 0.0473), and the fix changes its outcome by **exactly 0.0000** with 0 users
improved and 0 worsened. The fix therefore does what it claims and nothing else — it recovers
discarded budget, and there was none to recover there. It also re-confirms the P1 conclusion
that allocation efficiency is not achievement: this policy allocates the most and achieves the
least, because its problem is concentrating the whole budget on a single goal with no
investment.

**Not a free lunch, stated plainly:** 1–2 users per policy *worsen*, and `Rule-based urgency`
aside, 10–12 of 14 improve. Reallocating money to a goal the policy did not choose can front-load
a goal that would have been better left alone. The effect is net strongly positive but not
uniform, and a per-user regression is expected behaviour, not a bug.

### 1.3 Gating — no published behaviour changed

- `GoalPilotConfig.reallocate_capped_budget` defaults to **False**.
- **`archived()`, `corrected_accounting()`, `lp_parity()` and `recommended()` are all unchanged**
  (pinned by `test_reallocation_is_off_in_every_existing_preset`).
- The new behaviour is reachable only through the new preset
  `GoalPilotConfig.with_reallocation()`, pinned to differ from `recommended()` **only** in that
  one field.
- Every existing checkpoint, published result and archived CSV is therefore unaffected, and the
  archived-parity suite **verified this**: after the change the full RL suite reported
  **105 passed in 575.88s** and the LP suite **26 passed in 1.84s**, with
  `test_goalpilot_env_parity.py` (100 users x 5 policies x 142 months, reward to 1e-12) among
  them. Console: `outputs/reward_design/v3/pytest_full_after_reallocation.txt`,
  `pytest_lp_after_reallocation.txt`.

### 1.4 Regression tests — `tests/test_goalpilot_env_reallocation.py` (11, all passing)

Covers: the flag is off in every existing preset; only the dedicated preset enables it and it
differs in exactly one field; discarded budget falls and something is actually reallocated;
reallocation never reduces goal funding; and under the flag the budget identity, the
no-over-funding bound, the memo invariant and the net-worth identity all hold every month.

**Two of my own mistakes were caught by these tests, and both are worth recording:**

1. I asserted `released` would be *invariant*. It is not — reallocating funds goals sooner, so
   they saturate sooner and the cap releases **more** later (728,404 vs 717,967 accumulated).
   That trajectory feedback is correct; the invariant I actually needed was "discarded budget
   falls", which holds.
2. I asserted goals must never be credited beyond their target, and it failed — because the
   `market_weighted` gain is credited outside the cap, so the property never held. Rather than
   delete the assertion I made the property true, as change 2 above.

---

## 2. R-12 — status: **unchanged, decision still open**

`Investments only` and `Mixed (0.50/0.50)` remain **byte-identical** even with the R-13 fix
(0.6545 both, idle 0.0295 both). The degeneracy is orthogonal to R-13: whenever the investment
request meets or exceeds capacity, the overflow returns to savings, so both actions denote the
same policy.

Consequence: **the environment still cannot express an investment-light strategy**, so
"the mix matters" remains unanswerable in this environment. I have not altered it, as it was
excluded from this stage's scope.

---

## 3. P5 — the synthetic population is feasible-by-design, with a caveat

Measured over all 100 users (`outputs/reward_design/v3/population_feasibility_check.txt`):

| Quantity | Value |
|---|---|
| Free surplus `income − expenditure − EMI` | min **−16,409.26**, p25 1,200.81, median 7,147.90, p75 21,066.36, max 94,007.71 |
| Users with **zero or negative** surplus | **22 / 100 (22.0%)** |
| Users with `investment_capacity_ratio == 0` | **22** |
| Users with `EMI > free cashflow` | **22** |
| Users with `EMI > 0.35 × income` (outside the stated cap) | **1** |
| Users with `expenditure > income` | 4 |
| Correlation of `risk_score` with free surplus | **0.673** |

**Interpretation.** The three counts of 22 are the *same* 22 users, so the generator deliberately
marks cash-flow-constrained households with zero investment capacity — a coherent, intentional
stress cohort, not a data defect. And only **one** user violates the documented
`emi_income_ratio_cap = 0.35`, so the population largely respects its own stated affordability
rule; the deficit comes from **expenditure relative to income**, not from unaffordable EMI
(median EMI is 0; the 90th percentile of `EMI / (income − expenditure)` is 1.318).

**Two consequences that matter for reporting:**

1. **This fully explains the earlier cohort coincidence.** `risk_score` correlates 0.673 with
   free surplus, so binning users by `risk_score` largely re-measures cash-flow feasibility —
   which is exactly why the "low-risk" bin and the zero-surplus set were the same 6 users. Any
   *risk-group* analysis on this population is partly a feasibility analysis and must be labelled
   as such. `risk_score` cannot serve as an independent risk dimension here.
2. **Population-level means mix feasible and infeasible households.** 22% of users cannot fund
   any goal under any policy, which mechanically drags every reported mean down by roughly 22% of
   the achievable gap. This is why the feasibility-eligible population is reported alongside the
   full population in every comparison, with eligibility defined ex ante.

**This is not a recommendation to change the population.** A simulator for household financial
planning is a reasonable place for a cash-flow-constrained cohort; the requirement is that it be
declared, and it now is.

---

## 4. Status of the revised plan

| Item | Status |
|---|---|
| **P1a** R-13 fix | **Done** — opt-in, 11 tests, effect measured (+0.027 to +0.046 achievement; discarded budget 26–29% → ~3%) |
| **P5** population validation | **Done** — 22% structurally cash-flow-negative, feasible by design, `risk_score` confounded with surplus |
| **P1b** R-12 degeneracy | **Open** — unchanged; needs a decision (document, or make the capacity overflow non-degenerate) |
| **P4** rule-based baseline | **Open** — the P1a evidence sharpens the diagnosis: the rule's fault is *concentration with no investment* (it wastes nothing), so the fair replacement is a need-proportional, capacity-using rule |
| **P2** fresh-split confirmation | **Done** — `candidate_a` not reproducible |
| **P3** 50k/150k/300k budget comparison | **Deprioritised** — the effect it would chase (+0.007) is far below the R-13 effect just fixed (+0.038) |
| Full suites after the R-13 change | **Verified green** — RL `105 passed in 575.88s`, LP `26 passed in 1.84s`, archived parity included. The fix is gated and safe to keep |

## 5. Reproducing

```powershell
$py = "C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe"
Set-Location S:\fyp\GoalPilot_AI_Completed
& $py -m pytest tests\test_goalpilot_env_reallocation.py -q      # 11 passed in 18.53s
& $py audit_tools\51_reallocation_impact.py                     # the §1.2 table
& $py -m pytest -q                                              # full suite incl. archived parity
```
