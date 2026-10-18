# GoalPilot Multi-Goal Optimization Audit

Date: 2026-10-10

## Scope Inspected

- Handoff specification: `artifacts/input/GoalPilot_Complete_Optimization_Handoff(1).md`.
- Notebook: `artifacts/input/GoalPilot_MultiGoal_Optimization_FullRun.ipynb`.
- Existing extension package: `GoalPilot_MultiGoal_Extension/`.
- Dataset ZIP contents copied into `artifacts/extracted/dataset/`.
- Project reference sources under `sources/` were inspected as read-only inputs and were not edited.

The uploaded `/mnt/data/...` paths were not present in this Windows workspace. The same attachments were accessible through the referenced conversation preview paths and were copied into `artifacts/input/` before extraction.

## Current Repository Structure

- `src/multi_goal_optimizer.py`: LP optimizer, goal preparation, EMI and future-value helpers, strategy comparison.
- `src/simulation_adapter.py`: adapter from `final_optimisation_input.csv` to `FinancialState`.
- `src/providers.py`: added normalized offline-safe provider/data schemas for investments, loans, savings products, and scenarios.
- `generate_multigoal_dataset.py`: deterministic generator and sample optimization runner.
- `run_demo.py`: small three-goal demo and strategy/scenario output writer.
- `tests/`: optimizer, adapter, and provider regression tests.
- `data/`: compact copied simulation artifacts, synthetic multi-goal dataset, sample goals/state, and offline funding fixtures.
- `outputs/`: demo outputs and versioned sample optimization outputs.

## Existing LP Before This Update

The extension already used SciPy HiGHS through `scipy.optimize.linprog`. For each goal it had variables for initial cash, monthly savings contribution, monthly investment contribution, loan principal, and shortfall. It enforced a shared cash pool, shared monthly surplus, and EMI-cap constraint. It already avoided counting `existing_funding` twice by subtracting earmarked goal funding from available liquid savings.

The archived single-goal baseline documented in `data/lp_5r_formal_lp_specification.csv` used monthly goal funding variables and shortfall variables. It did not include product-level investments, borrowing decisions, or emergency-reserve constraints.

## Adapter and Field Mapping

- `final_monthly_income` maps to monthly net income.
- `final_monthly_expenditure` maps conservatively to `essential_expenses` because the simulation exposes one combined spending field, not separate essential/discretionary buckets.
- `final_monthly_emi` maps to existing EMI exactly once.
- `final_savings_balance` maps to liquid savings.
- `final_portfolio_value` maps to existing investments but not to usable assets unless an explicit usable amount is supplied.
- `risk_profile` maps to a configurable proxy: conservative `0.25`, moderate `0.50`, aggressive `0.75`.

## Goal Schema

Required goal columns are `goal_id`, `goal_name`, `current_cost`, `target_date`, `time_horizon_months`, `priority`, `criticality`, and `existing_funding`. The generated synthetic dataset also carries `user_id`, `goal_type`, `goal_data_origin`, and `synthetic_assumption_version` so legacy simulated goals are distinguishable from generated multi-goal assumptions.

## Issues Found and Corrected

- `existing_investments` was mapped but not allocatable. The optimizer now has `usable_existing_investments` and a separate existing-asset allocation variable. The adapter keeps this at `0.0` unless real liquidity/earmarking data exists.
- Monthly surplus now subtracts `essential_expenses`, optional `discretionary_expenses`, and `existing_emi` once.
- Existing EMI remains included once in both monthly surplus and EMI capacity.
- Existing goal earmarks are excluded from shared cash to avoid double counting.
- Goal costs are inflated once in `prepare_goals`; the LP uses the resulting funding gap.
- Annual returns are converted to monthly future-value factors for contributions; loan EMI uses nominal annual rate divided by 12.
- Provider options are normalized outside the solver and reported with provenance.

## Remaining Limitations

- The LP is static, not a month-by-month dynamic policy.
- The supplied data has synthetic multi-goals, not real user-entered multi-goal plans.
- Public source adapters are documented but not live-called in tests; offline fixtures are used for reproducibility.
- No underwriting, tax, transaction-cost, covariance, insurance, or legal suitability model is implemented.
- Full 10,000-user solve was not run in this environment; verified sample run was 1,000 users.
