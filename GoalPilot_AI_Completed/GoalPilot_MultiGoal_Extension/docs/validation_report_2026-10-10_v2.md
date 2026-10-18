# GoalPilot Multi-Goal Optimization Validation Report

Date: 2026-10-10

## Commands Executed

- `python -m pytest -q`
- `python run_demo.py`
- `python generate_multigoal_dataset.py --max-users 100`
- `python generate_multigoal_dataset.py --max-users 1000`

`pytest` was not installed globally. A local dependency folder `.local_pytest2/` was created with `python -m pip install --target .local_pytest2 pytest`, and tests were run with that folder on `PYTHONPATH`.

## Test Results

- Automated tests: 25 passed, 0 failed, 0 skipped.
- Coverage focus: goal validation, multi-goal constraints, no double counting of earmarks/assets/EMIs, discretionary expense handling, emergency reserve reporting, existing asset usability, loan EMI edge cases, provider fixture validation, offline provider selection, simulation adapter mapping, and malformed-data failures.

## Demo Run

- Command: `python run_demo.py`
- Solver status: `optimal`
- Goals processed: 3
- Outputs written:
  - `outputs/derived_goals.csv`
  - `outputs/multi_goal_allocations.csv`
  - `outputs/optimization_summary.json`
  - `outputs/strategy_comparison.csv`
  - `outputs/economic_scenario_comparison.csv`

## Synthetic Dataset Generation

- Users generated: 10,000
- Goal rows generated: 39,932
- Goals per user: min 3, max 5, mean 3.9932
- Synthetic generated goal rows: 29,932

## 100-User Optimization Smoke Run

- Command: `python generate_multigoal_dataset.py --max-users 100`
- Users attempted: 100
- Solver optimal: 100
- Failed: 0
- Goal allocation rows: 390
- Constraint summary: all recorded allocation constraints respected.

## 1,000-User Optimization Run

- Command: `python generate_multigoal_dataset.py --max-users 1000`
- Users attempted: 1,000
- Solver optimal: 1,000
- Failed: 0
- Goal allocation rows: 4,031
- Goal rows with shortfall: 1,340
- Goal rows fully funded: 2,691
- Users with all goals fully funded: 465
- Mean weighted goal achievement: 0.826830915980333
- Median weighted goal achievement: 0.9653088192098795
- Mean total shortfall: 3,568,137.674775989
- Total monthly contributions allocated: 21,572,505.518331796
- Total new monthly EMI: 6,963,621.312110587
- Recorded constraints respected: true
- Starting savings below emergency target: 173 users
- Emergency target met after allocation: 827 users

## Versioned Outputs

- `outputs/synthetic_multigoal_optimization_summary_sample1000_20261010_v2.json`
- `outputs/synthetic_multigoal_optimization_allocations_sample1000_20261010_v2.csv`
- `outputs/synthetic_multigoal_optimization_user_summary_sample1000_20261010_v2.csv`
- `outputs/synthetic_multigoal_optimization_failures_sample1000_20261010_v2.csv`

## Limitations

- The full 10,000-user optimization was not executed in this environment.
- The multi-goal dataset remains synthetic; it is suitable for deterministic project validation, not real user advice.
- Public data providers are documented and represented by offline fixtures; no live public API fetch was added to the test path.
- The LP is a static allocation model and does not yet reallocate monthly surplus after goals are completed.
- No taxes, fees beyond simple loan fixture fields, liquidity haircut, underwriting, insurance, or regulatory suitability assessment is modelled.
