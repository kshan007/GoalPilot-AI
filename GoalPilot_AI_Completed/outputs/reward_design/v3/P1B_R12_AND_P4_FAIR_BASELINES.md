# P1b (R-12 degeneracy) and P4 (fair baseline set)

**Date:** 2026-10-11 · **Version:** v3
**Scripts:** `audit_tools/52_fair_baselines.py`, `tests/test_goalpilot_env_semantics.py`
**Data:** `outputs/evaluation/final_validation_v3/fair_baselines_*.csv`

---

## 1. P1b — the R-12 degeneracy: documented and pinned, not redesigned

`Investments only` `(0, 1, 0)` and `Mixed (0.50/0.50)` `(0.5, 0.5, 0)` produce **identical**
allocations whenever the investment request meets or exceeds
`available x investment_capacity_ratio`, because the overflow returns to savings. So they denote
one policy, and the environment cannot express an investment-light strategy.

**Decision: document and pin; do not redesign the action semantics.** Reasons:

1. **No measured quantity is corrupted.** Every metric, invariant and comparison remains valid;
   what is lost is the ability to ask a specific question ("does the mix matter?").
2. **A redesign is not additive.** Making the capacity overflow non-degenerate changes what the
   action vector *means*, so it would invalidate every checkpoint and every published comparison
   and would need its own validation experiment. That is a research decision, not a bug fix.
3. The degeneracy is now **independently confirmed in two cohorts and both configs** (§2.2), so
   it is a stable, characterised property rather than a suspected defect.

**Pinned by two tests** in `tests/test_goalpilot_env_semantics.py`:

- `test_investment_capacity_overflow_makes_mixed_equivalent_to_investment_only` — asserts the two
  actions give identical savings/investment contributions and net worth every month, for several
  users with capacity. A future change to the overflow rule now fails **here** rather than
  silently invalidating the published tables.
- `test_investment_capacity_ratio_is_actually_respected` — asserts capacity still **binds**, so
  the pin above cannot become vacuous (if the cap stopped binding, both actions would also be
  equal, for the wrong reason).

Module result: **21 passed in 31.46s**.

---

## 2. P4 — fair baseline set on the uncontaminated cohort

Everything below runs on the **fresh** test users (the 16 from `fresh_split_v1`, of which 14 are
feasibility-eligible), over one market path, with the full metric list and a user-level bootstrap
CI on achievement. `affordability_violations = 0` for every arm in every config.

### 2.1 Ranking, `recommended()` (flag off — what the RL checkpoints were trained under)

| Policy | Achievement (eligible, n=14) | CI95 | % fully funded | % by deadline | Net worth | Interest paid |
|---|---:|---|---:|---:|---:|---:|
| **RL `archived_v1` seed7** | **0.6753** | [0.6026, 0.7450] | 0.4812 | 0.1146 | 2,748,925 | 8,716 |
| Rule: need-proportional investment | 0.6669 | [0.5831, 0.7540] | 0.4281 | 0.1271 | 2,840,803 | 0 |
| Rule: uniform 50/50 *(≡ uniform investment)* | 0.6628 | [0.5893, 0.7329] | 0.4656 | 0.1427 | 2,751,777 | 0 |
| Rule: uniform savings | 0.6382 | [0.5651, 0.7085] | 0.4531 | 0.1427 | 2,363,890 | 0 |
| RL `candidate_a` seed27 | 0.6384 | [0.5712, 0.6998] | 0.3771 | 0.1479 | 2,709,946 | 7,224 |
| RL `candidate_a` seed17 | 0.6056 | [0.5134, 0.6922] | 0.4073 | 0.0938 | 2,653,332 | 39,269 |
| RL `archived_v1` seed17 | 0.6017 | [0.5156, 0.6826] | 0.4198 | 0.1198 | 2,677,197 | 16,541 |
| LP optimizer plan | 0.5663 | [0.4590, 0.6698] | 0.3771 | **0.1687** | 2,688,699 | 7,424 |
| RL `candidate_a` seed7 | 0.5594 | [0.4648, 0.6591] | 0.3792 | 0.1510 | 2,669,111 | 15,711 |
| RL `archived_v1` seed27 | 0.5028 | [0.4083, 0.5960] | 0.3177 | 0.1115 | 2,661,715 | 19,860 |
| Rule: urgency **(known-defective, retained)** | 0.4630 | [0.3524, 0.5818] | 0.0625 | **0.0000** | 2,363,890 | 0 |
| Rule: need-proportional both | 0.4147 | [0.2866, 0.5600] | 0.0625 | 0.0000 | 2,840,539 | 0 |
| Rule: need-proportional savings | 0.3669 | [0.2429, 0.5112] | 0.0625 | 0.0000 | 2,363,890 | 0 |

### 2.2 Three statements survive; the rankings do not

**(a) The orderings are NOT reliable, in either direction.** Every CI overlaps, and the RL arm's
own seed spread (0.5028 → 0.6753) spans almost the entire range of the table. With 14 eligible
users and CIs of roughly ±0.09, **no arm is separable from any other.**

**This corrects a conclusion I stated too strongly one stage earlier.** In
`P1_STRATEGY_SPACE_DIAGNOSIS.md` I reported that a constant `Investments only` action beat every
RL policy. That was true on the *original* 20-user cohort; on the fresh cohort the order reverses
and the **top entry is RL** (`archived_v1` seed7, 0.6753, above uniform investment's 0.6628).
Both the earlier negative result and the earlier positive result for `candidate_a` were
cohort-specific. Neither generalises. What generalises is that the differences are smaller than
the measurement uncertainty.

**(b) The R-13 mechanism is confirmed a third time.** Under `with_reallocation()` (flag on) every
budget-wasting arm improves — uniform 50/50 0.6628 → **0.6962**, need-proportional investment
0.6669 → **0.6857**, uniform savings 0.6382 → **0.6801**, LP 0.5663 → **0.5935** — while
`Rule: urgency` is **unchanged at 0.4630 in both configs**. That is exactly what the mechanism
predicts: it is the one arm that wastes nothing, so there is nothing to recover.

**(c) Two baselines are genuinely and reproducibly bad, and they share one cause.** `Rule:
urgency` and `Rule: need-proportional savings` both score **0.0000 deadline success** and 0.0625
fully funded, in both configs. Neither ever invests. With 142 months of inflation-inflated
targets, a savings-only stream cannot close the gap — a mechanistically explainable result, not
noise. Conversely `need-proportional investment` (invest in proportion to need) is among the
strongest. **The investment channel, not the allocation shape, is what matters here** — which also
explains why the R-12 degeneracy is so consequential: the environment's most important lever is
the one the action space cannot modulate.

### 2.3 Note on a column convention

In this table `downside_exposure` is the **sum of negative monthly investment gains**, so it is
negative (more negative = more downside), unlike the earlier harness tables which reported
magnitudes. Raw values are in `fair_baselines_metrics_v1.csv`; the two conventions are not
directly comparable across documents and the earlier tables should not be read as smaller.

---

## 3. Status

| Item | Status |
|---|---|
| **P1a** R-13 fix | Done, verified, opt-in, suite green |
| **P1b** R-12 degeneracy | **Done** — documented, pinned by 2 tests, redesign declined with reasons |
| **P4** fair baselines | **Done** — 8 rules + LP + 6 RL on the uncontaminated cohort, with CIs |
| **P5** population validation | Done — 22% structurally cash-flow-negative by design |
| **P2** fresh-split confirmation | Done — `candidate_a` not reproducible |
| **P3** 50k/150k/300k budget comparison | **Deprioritised** — and now additionally unjustified: nothing in the strategy space is separable at the current precision, so a budget study cannot resolve an ordering that the cohort cannot |
| Full suite | **Verified green** — `107 passed in 517.06s`, archived parity included (`outputs/reward_design/v3/pytest_full_final.txt`). Test inventory: 107 RL + 26 LP = **133 tests, 0 failures** |

## 4. Reproducing

```powershell
$py = "C:\Users\sudha\AppData\Local\Programs\Python\Python313\python.exe"
Set-Location S:\fyp\GoalPilot_AI_Completed
& $py -m pytest tests\test_goalpilot_env_semantics.py -q     # 21 passed
& $py audit_tools\52_fair_baselines.py                       # the section 2 tables
```
