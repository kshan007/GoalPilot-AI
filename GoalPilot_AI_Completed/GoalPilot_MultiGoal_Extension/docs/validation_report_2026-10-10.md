# GoalPilot AI Multi-Goal Extension — Validation Report

Date: 2026-10-10

## What was executed in this environment

1. Inspected the original optimization ZIP (73 entries; ~238.5 MB uncompressed) and simulation ZIP (28 entries; ~1.286 GB uncompressed).
2. Inspected the separately attached optimization and simulation notebooks at source/cell level.
3. Ran the extension demo with SciPy HiGHS: solver status `optimal`.
4. Ran automated tests after adding the simulation adapter: **11 passed**.
5. Ran an integration smoke test using the first financial-profile row from `simulation/06_results/final_optimisation_input.csv` and the extension's explicitly synthetic three-goal example: solver status `optimal`.
6. Wrote `outputs/simulation_integration_smoke_allocations.csv` and `outputs/simulation_integration_smoke_summary.json`.

## What the smoke test proves

- The current simulation's final optimization input schema can be mapped to the optimizer's financial-state object for one user.
- The multi-goal solver accepts that mapped state and returns a feasible result for the sample three-goal dataset.
- Emergency reserve, shared monthly surplus, and configured EMI-cap checks reported as respected for this smoke test.

## What it does not prove

- It does not reproduce the original single-goal notebook's complete solve or independently verify its archived 10,000-user results.
- It does not run the complete 10,000-user simulation/optimization pipeline end-to-end.
- The simulation archive contains one legacy goal record per user, not actual multiple user-selected goals. The three goals in the smoke test are synthetic examples.
- The current LP stores `existing_investments` in the financial state but does not allocate/liquidate that portfolio. The optimizer only treats `liquid_savings` as initial cash and must not imply existing investments were included in the allocation.
- Risk capacity mapping from risk-profile labels is a configurable proxy (conservative=0.25, moderate=0.50, aggressive=0.75), not a validated suitability assessment.
- The current model does not yet use monthly-by-month cash-flow reallocation when a goal completes, product-level candidate investment data, portfolio covariance, tax/fees, or underwriting-based loan eligibility.

## Files changed/added

- `src/simulation_adapter.py`: maps the existing final optimization input row to `FinancialState`; maps legacy goal fields with explicit caveats.
- `tests/test_simulation_adapter.py`: four adapter tests.
- Regression test ensuring existing goal funding is not double-counted against the shared cash pool.
- `run_simulation_integration_smoke.py`: reproducible smoke test against the simulation ZIP and synthetic example goals.
- `outputs/simulation_integration_smoke_allocations.csv`
- `outputs/simulation_integration_smoke_summary.json`

## Important data handling decision

The legacy `goal_horizon_funding_actual` is an at-deadline/historical outcome, not necessarily current goal-specific funding. The adapter deliberately does **not** copy it into `existing_funding`, to avoid double-counting future/realized funding as current money. The optimizer now also subtracts goal funding already earmarked from the shared liquid-savings pool, assuming that earmarked amount is included in the reported liquid savings; a regression test covers this. Actual current goal funding, goal dates, priorities, criticalities, and multiple goals must be supplied by a real goal-input table before a real user plan can be generated.

## Verdict

**Prototype validated; integration smoke test passed; full phase is not complete.** The remaining blockers are real multi-goal input data and validation of the original pipeline, plus the listed model limitations. This is research/demo code, not a financial recommendation service.
