# Validation report — GoalPilot AI

**Date:** 2026-10-11 · **Working copy:** `S:\fyp\GoalPilot_AI_Completed` · **Original:** `S:\fyp\GoalPilot_AI` (untouched)

## 1. Scope and method

The brief's six stages were executed in order: inspect (A) -> fix accounting defects with regression tests (B) -> validate action and credit semantics and LP/RL comparability (C, E) -> analyse and redesign the reward (D) -> run tests and smoke experiments (F, G) -> prepare the controlled PPO experiment and the policy-evaluation pipeline (H, I).

Every claim below is backed by an executed command whose raw output is preserved. Diagnostics used read-only probes; no probe wrote to the project source.

## 2. Confirmed and fixed defects

| ID | Defect | Evidence | Fix | Regression test |
|---|---|---|---|---|
| R-01 | Residual loan principal silently written off at tenure expiry | 12 events / 560 episodes; largest Rs 2,534.52 (USER_00078 month 138) | Ledger mode settles it in cash, or carries it and keeps servicing it; legacy keeps the historical write-off | test_goalpilot_env_ledger_integrity.py (3 tests) |
| R-02 | Emergency reserve entirely off the balance sheet | restricted_cash = initial_savings for every sampled user; initial_net_worth excluded it (Rs 13.8k-133k per user) | Restricted cash inside `cash`, disclosed separately, included in net worth | test_goalpilot_env_semantics.py::test_reserve_is_on_the_balance_sheet_in_ledger_modes |
| R-03 | growth_weighted books projected returns as realised goal funding | a rupee contributed to a 10y goal credited as 1.63 rupees; USER_00084 credited +20.2% over contributions | New market_weighted mode: realised NIFTY revaluation only, credited outside the per-goal cap; recommended() switched to it | test_goalpilot_env_semantics.py::test_growth_weighted_books_a_projection_while_market_weighted_does_not, ::test_market_weighted_book_never_exceeds_real_assets |
| R-04 | interest_paid reported accrued interest; an unpaid-interest path could be silently forgiven | interest_due booked as paid regardless of actual_payment; shortfall measured zero in every reachable configuration | interest_accrued / interest_paid_cash / interest_shortfall split; shortfall capitalised in ledger mode | test_goalpilot_env_ledger_integrity.py::test_interest_paid_is_cash_interest_and_shortfall_is_zero |
| R-05 | Budget guard re-scaling and the cash floor were invisible | two-stage guard_scale and max(0.0, ...) cash floor were unreported | guard_scale and cash_floor_active exposed on budget_audit | test_goalpilot_env_ledger_integrity.py::test_budget_guard_and_cash_floor_are_exposed |
| R-06 | Per-month net-worth reconciliation not attributable | episode residual fully explained by R-01 (Rs 2,534.52 = the write-off); a probe 'aggregate residual' figure was a mis-derived metric and was withdrawn | Residual, guard, interest and settlement events exposed so the identity is assertable | test_goalpilot_env_ledger_integrity.py::test_net_worth_reconciliation_holds_every_month |
| R-11 | Pre-existing goal earmark deducted from cash, understating net worth | cash = initial_savings - earmarked while the memo doctrine forbade adding goal_balances back, so cash + portfolio could fall below sum(goal_balances) | Ledger mode keeps the full initial balance in cash; goal_balances is a pure memo label | test_goalpilot_env_semantics.py::test_earmarking_neither_creates_nor_destroys_cash |

## 3. Confirmed but unresolved

| ID | Item | Status |
|---|---|---|
| R-07 | Reward-design defects (wealth-scaled risk penalty, no terminal value, deadline-month-only shortfall, principal-based loan penalty) | Diagnosed and quantified; candidates implemented as separate opt-in reward versions. NOT trained, NOT selected |
| R-08 | Funds released by a per-goal cap are not reallocated to under-funded goals | Confirmed as a behavioural difference from the LP; documented, not changed (would alter archived behaviour) |
| R-09 | The emergency reserve changes earmark reconciliation independently of policy | Controlled for by holding the preset fixed within each comparison; not eliminated |
| R-01b | The residual_carried branch (cash insufficient to settle) | Covered by assertion but never exercised by real data; cash always covers the residual |

## 4. Deliberately preserved, not fixed

| ID | Item | Reason |
|---|---|---|
| R-10 | Legacy/archived double count (cash and goal_balances hold the same money; unallocated surplus unrecorded) | GoalPilotConfig.archived() must reproduce the 2026-10-10 environment exactly; test_goalpilot_env_parity.py enforces it to 1e-12 |
| - | The LP optimizer | No defect demonstrated, so per requirement 6 it was not modified - only called from the new evaluation pipeline |

## 5. Tests actually executed

Full console output is preserved verbatim in this directory (`pytest_*.txt`) and summarised in `TEST_EXECUTION_REPORT.md`. No test is reported as passing that was not executed, and no meaningful test was weakened or deleted.

## 6. Experiments actually completed

| Experiment | Scope | Result |
|---|---|---|
| Phase D/E/H evaluation pipeline | 20 held-out users x up to 8 policies x 4 presets x 142 months, plus 3 reward versions | components reconcile to 8.882e-16; 0 budget violations |
| Phase G smoke test (7 steps) | check_env, full episode, archived checkpoint load, 2,048-step PPO | all 7 steps passed; episode 142 months; archived reward -12.421 |

## 7. Proposed but NOT run

- Substantial PPO training under `GoalPilotConfig.recommended()` (e.g. 100k timesteps).
- Training under `candidate_a` / `candidate_b` so that reward versions can be compared on *trained* policies.
- Ablation of the terminal net-worth term and of the graduated shortfall window.
- Google Colab execution of any stage.
- A fair LP-vs-newly-trained-PPO comparison (requires the training above).

## 8. Synthetic assumptions still requiring validation

- `annual_savings_return = 0.0` and `investment_return_assumption = 0.05` are synthetic assumptions. Under `market_weighted` only the second still influences anything, and it no longer enters goal funding.
- `existing_funding` per goal is synthetic; it drives the reset earmark and `funding_scale`.
- `investment_capacity_ratio`, `risk_score` and `monthly_emi` are synthetic profile fields, not observed data.
- `walr_monthly` (RBI lending rate) drives both loan pricing and amortisation; the level EMI is fixed at origination while interest accrues at each month's rate, which is the mechanism behind R-01.
- Goal targets are inflated at 3% p.a. in `lp_parity`/`recommended`; the inflation series was not independently validated.

## 9. Acceptance criteria (§12 of the brief)

| Criterion | Status | Note |
|---|---|---|
| 1. Original project and archived results intact | MET | originals untouched; 64 pre-existing tests still pass |
| 2. Archived configuration reproduces historical behaviour | MET | parity suite: 100 users x 5 policies x 142 months, reward to 1e-12 |
| 3. Ledger passes cash-flow and net-worth invariants | MET | per-month identity asserted in ledger mode; cash-flow test includes the residual settlement |
| 4. Loan repayments cannot silently erase a residual liability | MET | R-01 fixed; legacy write-off is explicit and gated |
| 5. Recommended action and goal-credit semantics validated | MET | share mode equivalence, no-op zero action, correct credit horizon, realised-only crediting |
| 6. Reward components reconcile exactly | MET | max residual 8.882e-16 across all reward versions |
| 7. New reward design documented and separately configurable | MET | reward_version switch; archived_v1 remains the default |
| 8. LP/RL evaluation uses consistent assumptions or documents differences | MET | 4 presets, nominal and inflated funding both reported; mapping caveats stated |
| 9. RL and LP regression suites pass | SEE TEST_EXECUTION_REPORT.md | console output preserved |
| 10. Gymnasium compatibility and PPO smoke tests pass | MET | check_env passed; 7-step smoke test passed |
| 11. Training and evaluation configurations are reproducible | MET | training_logs/experiments/experiment_config_v1.json |
| 12. No claimed improvement rests on a higher reward or an unfair baseline | MET | no improvement is claimed; no reward was selected; no policy was excluded |
