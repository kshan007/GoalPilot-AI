# Remaining limitations

**Date:** 2026-10-11 · **Working copy:** `S:\fyp\GoalPilot_AI_Completed`

Status of the phases in §13 of the brief: A (inspection) complete, B (accounting) complete,
C (semantics) complete, D (reward design) designed and evaluated on fixed policies,
E (comparability) complete, F (regression) complete, G (PPO readiness) smoke-tested only,
H (policy evaluation) complete, I (documentation) complete.

---

## Confirmed and fixed

R-01 residual lien silently written off · R-02 emergency reserve off the balance sheet ·
R-03 projected returns booked as goal funding (new `market_weighted` mode) ·
R-04 accrued vs cash interest conflated · R-05 silent budget guard / cash floor ·
R-06 unattributed per-month reconciliation (mis-derived metric withdrawn; identity now
asserted) · R-11 pre-existing earmark deducted from cash.

Each has a regression test; see `MODIFIED_FILES.md` and `STAGE2_LEDGER_FIXES.md`.

## Confirmed but unresolved

| Item | Why unresolved |
|---|---|
| **Carried-residual branch (R-01)** | The `residual_carried` path (insufficient cash to settle) is covered by assertion but has **never been exercised by real data** — accumulated cash always covers the residual, so no observed case exists |
| **`growth_weighted` remains selectable** | It is still the LP-matching mode. It was *demoted* from `recommended()` but not removed, because removing it would break LP-parity experiments. A user of `lp_parity` should understand that its goal funding is a projection |
| **R-09 earmark divergence across configs** | The emergency reserve changes `funding_scale` in earmark reconciliation, so `goal_balances` at reset differ between `archived` and `recommended` independently of any policy. Controlled for in the comparison, not eliminated |

## Not fixed, by instruction

| Item | Reason |
|---|---|
| **R-10 legacy double count** | `GoalPilotConfig.archived()` must reproduce the 2026-10-10 environment exactly, so `legacy` mode keeps the double count deliberately. Any number produced under `archived` inherits it |
| **The LP optimizer** | Requirement 6: not modified. No defect was demonstrated, so it was left untouched — only *called* from the new evaluation pipeline |

## Not executed / not validated

| Item | Status |
|---|---|
| **Substantial PPO training** | **NOT STARTED.** Only a 2,048-step smoke run exists (`training_logs/experiments/smoke/ppo_smoke.zip`). No claim about PPO improvement is made or supported |
| **PPO under the recommended configuration** | Not trained. The archived checkpoint is valid **only** under `GoalPilotConfig.archived()`, and is reported only for the archived preset |
| **Google Colab execution** | **Never run.** Colab readiness is verified structurally (path resolver, guarded imports, documented commands), not by execution |
| **`monthly_financial_simulation_base.csv` (959 MB)** and **`portfolio_simulation_validated.csv` (169 MB)** | **Content not validated** — schema-inspected only. No claim is made about their contents |
| **`generate_multigoal_dataset.py`** | Read, not independently re-derived |
| **Candidate-reward coefficient tuning** | The weights are documented design choices, not fitted optima. Untested by training |
| **Ablation of the terminal net-worth term** | Not run |
| **Reward selection** | **No reward was selected.** Selection requires trained policies under each version on held-out users, which has not happened |

## Structural limits of the comparison

1. **LP vs RL is not an exact parity comparison.** The LP is deterministic and one-shot; the
   RL environment walks a monthly market path. The LP's plan is mapped onto the environment's
   monthly share weights, and the environment still enforces its own EMI cap,
   `max_new_loan` and affordability constraint, so the LP plan can be truncated. The mapping
   is a modelling choice, stated explicitly in `lp_rl_comparability_v1.csv`.
2. **Different loan rates.** The LP uses a fixed `loan_annual_rate = 0.12`; the environment
   uses the month's actual `walr_monthly`. This is an unavoidable difference and is stated
   rather than hidden.
3. **The LP has no monthly budget path.** It assumes a constant monthly surplus; the
   environment's is also constant per user, but the environment's *allocation* changes with
   goal caps and loan state.
4. **The LP enforces a 6-month reserve; `archived` and `corrected_accounting` do not.** After
   R-02 the reserve is at least on the balance sheet in ledger mode, but a comparison against
   `archived` still differs in reserve policy.
5. **Bootstrap CIs assume users are exchangeable.** They quantify dispersion across the 20
   held-out users, not sampling error in the underlying population of households.

## Reproducibility caveats

- Re-running `evaluation/run_all.py` (the pre-existing orchestrator) will regenerate the
  **pre-fix** CSVs in `outputs/evaluation/`; the new work deliberately writes to
  `final_validation_v1/` instead. Pre-fix outputs are preserved as the historical record and
  should not be read as post-fix numbers.
- `torch` is CPU-only on this host; timings are not comparable to a GPU run.
