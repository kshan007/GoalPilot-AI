# Modified files and reasons

**Working copy:** `S:\fyp\GoalPilot_AI_Completed`
**Authoritative original:** `S:\fyp\GoalPilot_AI` — **never modified**
**Date:** 2026-10-11

Rule applied throughout: **no archived behaviour was removed, only made optional.** Every
behavioural change is gated on a configuration switch that `GoalPilotConfig.archived()`
leaves at its historical value, so `test_goalpilot_env_parity.py` still reproduces the
2026-10-10 environment exactly (100 users x 5 policies x 142 months, reward to 1e-12).

---

## 1. Source files changed

| File | Change | Reason | Finding |
|---|---|---|---|
| `simulation/05_simulation_runs/rl_prototype/goalpilot_env.py` | Loan-repayment block: residual lien at tenure expiry is settled in cash (ledger) or carried and kept in service; `legacy` keeps the historical write-off | A residual principal vanished with no cash movement and no recorded event | **R-01** |
| " | Interest accounting split into `interest_accrued` / `interest_paid_cash` / `interest_shortfall`; unpaid accrued interest is capitalised in `ledger` mode | `interest_paid` reported accrued interest, and a non-binding cap could have forgiven interest silently | **R-04** |
| " | Budget-guard block: `guard_scale` (product of both re-scaling stages) is now tracked and exposed; `cash_floor_active` is exposed | A silent clamp would have been invisible in the audit trail | **R-05** |
| " | Reset: in `ledger` mode `cash` keeps the **full** initial savings, so the pre-existing goal earmark stays inside cash; `restricted_cash` is reported separately | Earmarking had been deducting money from cash while the memo doctrine forbade adding `goal_balances` back, so net worth understated the household position | **R-11** |
| " | Reset: the emergency reserve is restricted cash **inside** `cash` and therefore appears in `initial_net_worth` | The entire reserve had been off the balance sheet in `lp_parity`/`recommended`, making LP/RL net-worth comparison invalid | **R-02** |
| " | New `market_weighted` credit mode: the money earmarked to each goal is marked to market at the **realised** NIFTY monthly return; the realised revaluation is credited outside the per-goal cap | `growth_weighted` booked a *projected* return as realised goal funding | **R-03** |
| " | New reward versions `candidate_a` and `candidate_b`, selected by `config.reward_version`; the archived reward is untouched and remains the default | The historical reward must be preserved, but a redesign must be separately configurable | **R-07 / Phase D** |
| `simulation/05_simulation_runs/rl_prototype/goalpilot_config.py` | Added `GOAL_CREDIT_MARKET_WEIGHTED`; added reward-version constants and fields (`reward_version`, `shortfall_window_months`, `loan_cost_weight`, `downside_risk_weight`, `terminal_net_worth_weight`, `wealth_delta_weight`, `terminal_achievement_weight`); validation for `reward_version`; `recommended()` now uses `market_weighted` | One place to control every assumption; the recommended preset must not book projected returns | **R-03, R-07** |

## 2. Tests changed

| File | Change | Reason |
|---|---|---|
| `tests/test_goalpilot_env_ledger_integrity.py` | **New** — 11 tests | Regression cover for R-01, R-04, R-05, R-06 |
| `tests/test_goalpilot_env_semantics.py` | **New** — 14 tests | Phase C (share mode, credit semantics, degeneracy) plus R-02 and R-11 |
| `tests/test_goalpilot_config_paths.py` | `test_recommended_preset_uses_the_new_mechanisms` now asserts `GOAL_CREDIT_MARKET_WEIGHTED` and additionally asserts `growth_weighted` is still selectable | **Deliberate spec change, not a weakened test.** Booking a projected return as goal funding contradicts requirement C2, so the recommended preset changed. The assertion was made *stronger* (it now also pins the availability of the old mode) |

## 3. New tooling and outputs (nothing historical overwritten)

| Path | Purpose |
|---|---|
| `evaluation/final_validation_evaluation.py` | Phases D/E/H: reward decomposition, LP/RL comparability, 8-policy evaluation with CIs and paired comparisons |
| `audit_tools/30_final_validation_probe.py`, `31_probe_followup.py` | Phase A read-only defect probes |
| `audit_tools/32_ppo_smoke_test.py` | Phase G 7-step readiness smoke test + reproducible experiment config |
| `outputs/evaluation/final_validation_v1/**` | Phase B/C/F/H/I artefacts (new directory) |
| `outputs/reward_design/v1/**` | Phase D reward-design evidence |
| `training_logs/experiments/experiment_config_v1.json` | Reproducible experiment configuration |
| `training_logs/experiments/smoke/ppo_smoke.zip` | Smoke-test checkpoint (2,048 timesteps) |

## 4. Explicitly preserved unchanged

`models/**` (both checkpoints), `training_logs/tensorboard/**`, `training_logs/ppo_eval/**`,
every archived `rl_*.csv`, all ten `goalpilot_env.py.pre_*.bak` files,
`archive/goalpilot_env_archived_20261010.py`, `GoalPilot_MultiGoal_Extension/**` (including
the LP optimizer and its 26 tests), `optimization/**`, all `simulation/0*_*` datasets,
`datasets/**`, every pre-existing CSV under `outputs/evaluation/`, and both notebooks.
